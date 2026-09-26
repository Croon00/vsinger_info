"""Seed the song master from reviewed external candidates (plan step 5).

``export`` (read-only DB) merges four inputs into
migrations/catalog/song-master-decisions.json:

  * the latest pilot report of scripts/match_song_candidates.py (git-ignored),
  * artist research and the first-pass review written next to that report,
  * migrations/catalog/song-master-manual.json (user decisions and overrides).

``apply`` dry-runs the decision file; ``apply --apply`` writes it in ONE transaction:
new artists (+aliases), new songs (+song_artists, external IDs), external IDs and
missing ``title_latin`` for existing songs, and confirmed song_match_keys. Every row is
recorded in catalog_changes under one catalog_imports receipt, rows changed since export
abort the whole run, and a second apply of the same file is a no-op. Performances are
not touched; link them afterwards with scripts/link_performances_from_match_keys.py.

Rules: one external work maps to one song. When keys of different artists resolve to
the same work (an original and a well-known version), each artist keeps its own song and
the work ID goes to the song whose artist is credited on the work, else the most sung.
Existing songs only get ``title_latin`` when it is empty. New artists are hidden from the
catalog (show_in_catalog=false) and have no Korean name when the native name is Latin.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
import unicodedata
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.core.song_keys import ascii_latin, normalize_text  # noqa: E402
from app.services.song_candidates import existing_matches, loose  # noqa: E402

REPORT_DIR = ROOT / "db-migration" / "reports" / "song-master-candidates"
DECISIONS = ROOT / "migrations" / "catalog" / "song-master-decisions.json"
MANUAL = ROOT / "migrations" / "catalog" / "song-master-manual.json"
POLICY = "song-master-seed-v1"
NAMESPACE = uuid.UUID("5b0f6c1e-93a4-4d7e-b2c8-0a61f3d94e27")
LOCK_ID = 731064923  # shared with the other song_match_keys writers
KEY_VERSION = 1
SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
LANGUAGES = {"japanese": "ja", "jpn": "ja", "english": "en", "eng": "en", "korean": "ko", "kor": "ko"}
DECIDED_BY = {"vocadb": "vocadb", "utaitedb": "utaitedb", "musicbrainz_work": "musicbrainz"}
WORK_CREDIT_ROLES = {"producer", "circle", "band", "composer", "lyricist", "writer"}

_spec = importlib.util.spec_from_file_location("migrate_catalog", ROOT / "scripts" / "migrate_catalog.py")
migrate_catalog = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migrate_catalog)


def rows(conn, query: str, params=None):
    return conn.cursor(row_factory=dict_row).execute(query, params)


def alias_key(value: str) -> str:
    """artist_aliases.normalized_alias, as the admin schema generates it."""
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def is_latin(value: str | None) -> bool:
    return bool(value) and ascii_latin(value) is not None


# --------------------------------------------------------------------------- export

def load_state(conn) -> dict:
    """Everything export needs from the catalog. Read-only."""
    artists = {r["id"]: r for r in rows(conn, """
        SELECT id, slug, name_native, name_ko, name_latin FROM artists WHERE archived_at IS NULL""")}
    spellings = defaultdict(set)
    for a in artists.values():
        for value in (a["name_native"], a["name_ko"], a["name_latin"]):
            if value:
                spellings[a["id"]].add(normalize_text(value))
    for r in rows(conn, "SELECT artist_id, alias FROM artist_aliases"):
        spellings[r["artist_id"]].add(normalize_text(r["alias"]))
    songs = {}
    for r in rows(conn, """
        SELECT s.id, s.version, s.title_native, s.title_latin,
               coalesce(array_agg(sa.artist_id ORDER BY sa.position, sa.id) FILTER (WHERE sa.id IS NOT NULL), '{}') AS artist_ids
        FROM songs s LEFT JOIN song_artists sa ON sa.song_id=s.id
        WHERE s.archived_at IS NULL AND NOT EXISTS (SELECT 1 FROM song_merges m WHERE m.source_song_id=s.id)
        GROUP BY s.id"""):
        songs[r["id"]] = {**r, "artist_ids": list(r["artist_ids"])}
    keys = {r["id"]: r for r in rows(conn, """
        SELECT id, version, status, title_key, artist_key, sample_raw_title, sample_raw_artist, occurrence_count
        FROM song_match_keys WHERE key_version=%s""", (KEY_VERSION,))}
    external = {(r["provider"], r["external_id"]): r["song_id"]
                for r in rows(conn, "SELECT provider, external_id, song_id FROM song_external_ids")}
    identity = rows(conn, "SELECT id::text AS id FROM catalog_instance").fetchone()["id"]
    return {"catalog_instance_id": identity, "artists": artists,
            "spellings": {k: set(v) for k, v in spellings.items()},
            "songs": songs, "keys": keys, "external": external}


def load_inputs(report_dir: Path) -> dict:
    report_path = sorted(report_dir.glob("candidates-*.json"))[-1]
    research = []
    for path in sorted(report_dir.glob("artist-research-output-*.json")):
        research += json.loads(path.read_text(encoding="utf-8-sig"))
    refs = json.loads((report_dir / "artist-research-refs.json").read_text(encoding="utf-8"))
    review = json.loads((report_dir / "review-output.json").read_text(encoding="utf-8-sig"))["items"]
    return {"report_name": report_path.name, "report": json.loads(report_path.read_text(encoding="utf-8")),
            "research": research, "research_refs": refs, "review": review,
            "manual": json.loads(MANUAL.read_text(encoding="utf-8"))}


def strong(item: dict) -> dict:
    return next(c for c in item["candidates"] if c["title_exact"] and c["artist_exact"])


def clean_artist(record: dict, extra_aliases, *, taken_slugs: set[str]) -> dict:
    """Validate one researched artist and apply the catalog rules."""
    native = (record.get("name_native") or "").strip()
    if not native:
        raise ValueError(f"{record.get('ref')}: name_native missing")
    latin = ascii_latin(record.get("name_latin")) if record.get("name_latin") else None
    if latin is None and is_latin(native) and ascii_latin(native) != native:
        latin = ascii_latin(native)  # Cö shu Nie -> Co shu Nie
    if latin == native:
        latin = None
    korean = None if is_latin(native) else ((record.get("name_ko") or "").strip() or None)
    kind = record.get("entity_kind")
    if kind not in ("solo", "group"):
        raise ValueError(f"{record.get('ref')}: entity_kind must be solo or group")
    slug = (record.get("slug") or "").strip()
    if not SLUG.fullmatch(slug) or slug in taken_slugs:
        raise ValueError(f"{record.get('ref')}: slug {slug!r} invalid or already used")
    taken_slugs.add(slug)
    names = {alias_key(v) for v in (native, korean, latin) if v}
    aliases, seen = [], set(names)
    for value in [*(record.get("aliases") or []), *extra_aliases]:
        value = (value or "").strip()
        if value and alias_key(value) not in seen:
            seen.add(alias_key(value))
            aliases.append(value)
    return {"ref": record["ref"], "slug": slug, "name_native": native, "name_ko": korean, "name_latin": latin,
            "entity_kind": kind, "is_virtual": record.get("is_virtual") is True, "show_in_catalog": False,
            "aliases": aliases, "confidence": record.get("confidence"), "sources": record.get("sources") or []}


def plan(state: dict, inputs: dict) -> dict:
    """Pure: turn report + research + review + manual decisions into a decision file."""
    report, manual = inputs["report"], inputs["manual"]
    songs, keys, spellings = state["songs"], state["keys"], state["spellings"]
    skipped: list[dict] = []
    claims = dict(state["external"])  # (provider, id) -> existing song id, grows as we attach

    def song_spellings(song_id: int) -> set[str]:
        return set().union(*(spellings.get(a, set()) for a in songs[song_id]["artist_ids"])) if songs[song_id]["artist_ids"] else set()

    # ---- existing songs: external IDs and empty title_latin
    existing: dict[int, dict] = {}

    def attach(song_id: int, candidate: dict, basis: str) -> bool:
        ext = (candidate["provider"], candidate["external_id"])
        song = songs.get(song_id)
        if song is None:
            skipped.append({"song_id": song_id, "reason": "song missing or archived"})
            return False
        if ext in claims and claims[ext] != song_id:
            skipped.append({"song_id": song_id, "external": list(ext), "reason": f"work already belongs to song {claims[ext]}"})
            return False
        entry = existing.setdefault(song_id, {"song_id": song_id, "version": song["version"], "external_ids": [],
                                             "title_latin": None, "basis": basis})
        if any(e["provider"] == ext[0] for e in entry["external_ids"]) or claims.get(ext) == song_id:
            return True
        entry["external_ids"].append({"provider": ext[0], "external_id": ext[1], "url": candidate.get("url")})
        claims[ext] = song_id
        latin = candidate.get("title_latin")
        # Same as the native title (e.g. "Lemon") means no separate Latin form.
        if (song["title_latin"] is None and entry["title_latin"] is None and latin and ascii_latin(latin) == latin
                and latin != song["title_native"]):
            entry["title_latin"] = latin
        return True

    forced = {m["song_id"]: m for m in manual.get("existing_song_external", [])}
    for song_id, m in forced.items():
        if m.get("provider"):
            attach(song_id, {"provider": m["provider"], "external_id": m["external_id"], "url": None,
                             "title_latin": None}, "user")
    review = {r["item"]: r for r in inputs["review"]}
    for override in manual.get("review_overrides", []):
        review[override["item"]] = {**review.get(override["item"], {}), **override, "override": True}
    items = sorted(report["items"], key=lambda i: (-i["count"], i["kind"], i["ref"]))
    for item in (i for i in items if i["kind"] == "song"):
        if item["ref"] in forced:
            continue
        if item["status"] == "auto":
            attach(item["ref"], strong(item), "auto")
        elif item["status"] == "review":
            decision = review.get(f"song:{item['ref']}")
            if decision and decision["decision"] == "attach":
                candidate = next((c for c in item["candidates"] if c["provider"] == decision["provider"]
                                  and c["external_id"] == str(decision["external_id"])), None)
                if candidate is None:
                    skipped.append({"item": f"song:{item['ref']}", "reason": "reviewed ID not among candidates"})
                else:
                    attach(item["ref"], candidate, "agent_review")

    # ---- artists for new songs
    research = {r["ref"]: r for r in inputs["research"]}
    for override in manual.get("artist_overrides", []):
        if override["ref"] in research:
            research[override["ref"]] = {**research[override["ref"]],
                                         **{k: v for k, v in override.items() if k not in ("ref", "reason")}}
    ref_by_spelling = {}
    for ref in inputs["research_refs"]:
        for value in ref["setlist_spellings"]:
            ref_by_spelling[loose(value)] = ref["ref"]
    taken = {a["slug"] for a in state["artists"].values()}
    new_artists: dict[str, dict] = {}
    raw_by_ref = defaultdict(set)

    def artist_for(raw: str | None, reviewer_artist: dict | None = None):
        """('id', artist_id) | ('ref', new artist ref) | None."""
        if reviewer_artist:
            native = reviewer_artist.get("name_native")
            for artist in new_artists.values():
                if loose(artist["name_native"]) == loose(native):
                    raw_by_ref[artist["ref"]].add(raw)
                    return ("ref", artist["ref"])
            ref = "R" + hashlib.sha1(native.encode()).hexdigest()[:8]
            new_artists[ref] = clean_artist({**reviewer_artist, "ref": ref}, [raw] if raw else [], taken_slugs=taken)
            return ("ref", ref)
        ref = ref_by_spelling.get(loose(raw))
        record = research.get(ref)
        if record is None:
            return None
        if record.get("existing_artist_id") in state["artists"]:
            return ("id", record["existing_artist_id"])
        raw_by_ref[ref].add(raw)
        if ref not in new_artists:
            new_artists[ref] = clean_artist(record, [], taken_slugs=taken)
        return ("ref", ref)

    # ---- keys
    key_plans: list[dict] = []
    new_song_plans: list[dict] = []
    song_index = [{"id": s["id"], "title_key": normalize_text(s["title_native"]), "artist_spellings": song_spellings(s["id"])}
                  for s in songs.values()]

    def key_row(key_id: int):
        key = keys.get(key_id)
        if key is None or key["status"] != "pending":
            skipped.append({"key_id": key_id, "reason": "key missing or no longer pending"})
            return None
        return key

    def link(key, song_id, basis, decided_by, candidate=None):
        key_plans.append({"key_id": key["id"], "key_version": key["version"], "title_key": key["title_key"],
                          "artist_key": key["artist_key"], "song_id": song_id, "song_ref": None, "basis": basis,
                          "decided_by": decided_by, "external": [candidate["provider"], candidate["external_id"]] if candidate else None})

    def propose_new(key, candidate, artists, basis, decided_by, count):
        new_song_plans.append({"key": key, "candidate": candidate, "artists": artists, "basis": basis,
                               "decided_by": decided_by, "count": count})

    manual_keys = {m["key_id"]: m for m in manual.get("keys", [])}
    for item in (i for i in items if i["kind"] == "key" and i["ref"] not in manual_keys):
        if item["status"] not in ("auto", "review"):
            continue
        key = key_row(item["ref"])
        if key is None:
            continue
        target = {normalize_text(item["artist"])} | set().union(*(spellings.get(a, set()) for a in item["our_artist_ids"]))
        if item["status"] == "auto":
            candidate, basis, decided_by = strong(item), "auto", DECIDED_BY[strong(item)["provider"]]
            reviewer_artist, artist_ids = None, item["our_artist_ids"]
        else:
            decision = review.get(f"key:{item['ref']}")
            if not decision or decision["decision"] not in ("create", "link_existing"):
                skipped.append({"key_id": item["ref"], "reason": f"review: {decision['decision'] if decision else 'none'}"})
                continue
            if decision["decision"] == "link_existing":
                if decision.get("song_id") in songs:
                    link(key, decision["song_id"], "agent_review", "manual")
                else:
                    skipped.append({"key_id": item["ref"], "reason": "reviewed song id not found"})
                continue
            candidate = next((c for c in item["candidates"] if c["provider"] == decision["provider"]
                              and c["external_id"] == str(decision["external_id"])), None)
            if candidate is None:
                skipped.append({"key_id": item["ref"], "reason": "reviewed ID not among candidates"})
                continue
            basis, decided_by = "agent_review", "manual"
            reviewer_artist = decision.get("new_artist")
            artist_ids = [a for a in decision.get("artist_ids") or [] if a in state["artists"]]
        external_map = {**claims}
        matches = existing_matches(candidate, song_index, external_map, target_spellings=target)
        if len(matches) == 1:
            link(key, matches[0], basis, decided_by, candidate)
            attach(matches[0], candidate, "key_" + basis)
            continue
        if len(matches) > 1:
            skipped.append({"key_id": item["ref"], "reason": f"several existing songs match: {matches}"})
            continue
        if artist_ids:
            artists = [("id", a) for a in artist_ids]
        else:
            found = artist_for(item["artist"], reviewer_artist)
            if found is None:
                skipped.append({"key_id": item["ref"], "reason": "no researched artist"})
                continue
            artists = [found]
        propose_new(key, candidate, artists, basis, decided_by, item["count"])
    for key_id, m in manual_keys.items():
        key = key_row(key_id)
        if key is None:
            continue
        if m.get("song_id"):
            if m["song_id"] in songs:
                link(key, m["song_id"], "user", "manual")
            else:
                skipped.append({"key_id": key_id, "reason": "manual song id not found"})
        else:
            spec = m["new_song"]
            candidate = {"provider": None, "external_id": None, "title": spec["title_native"], "title_latin": None,
                         "title_ko": None, "language": None, "url": None, "artists": [], "performers": []}
            propose_new(key, candidate, [("id", a) for a in spec["artist_ids"]], "user", "manual", key["occurrence_count"])

    # ---- new songs: one per (work, artist set); the work ID goes to one artist's song
    groups: dict = defaultdict(lambda: defaultdict(list))
    for p in new_song_plans:
        work = (p["candidate"]["provider"], p["candidate"]["external_id"]) if p["candidate"]["provider"] else ("manual", p["key"]["id"])
        groups[work][tuple(sorted(p["artists"]))].append(p)
    new_songs = []
    for work, by_artists in groups.items():
        credited = None
        if work[0] != "manual" and len(by_artists) > 1:
            def work_credit(plans):
                c = plans[0]["candidate"]
                names = {loose(a["name"]) for a in c["artists"] if a["role"] in WORK_CREDIT_ROLES}
                return any(loose(v) in names for p in plans for v in [p["key"]["artist_key"]])
            ranked = sorted(by_artists.items(), key=lambda kv: (not work_credit(kv[1]), -sum(p["count"] for p in kv[1])))
            credited = ranked[0][0]
        for artists, plans in by_artists.items():
            c = plans[0]["candidate"]
            ref = f"S{len(new_songs) + 1:03d}"
            owns_work = work[0] != "manual" and (credited is None or artists == credited) and work not in claims
            if owns_work:
                claims[work] = ref
            latin = c.get("title_latin")
            new_songs.append({
                "ref": ref, "title_native": c["title"],
                "title_latin": latin if latin and ascii_latin(latin) == latin and latin != c["title"] else None,
                "title_ko": c.get("title_ko"),
                "language_code": LANGUAGES.get(str(c.get("language") or "").lower()),
                "artists": [{"artist_id": v} if k == "id" else {"artist_ref": v} for k, v in artists],
                "external_ids": [{"provider": work[0], "external_id": work[1], "url": c.get("url")}] if owns_work else [],
                "same_work_as_other_artist": list(work) if work[0] != "manual" and not owns_work else None,
                "basis": plans[0]["basis"], "keys": [p["key"]["id"] for p in plans]})
            for p in plans:
                key = p["key"]
                key_plans.append({"key_id": key["id"], "key_version": key["version"], "title_key": key["title_key"],
                                  "artist_key": key["artist_key"], "song_id": None, "song_ref": ref, "basis": p["basis"],
                                  "decided_by": p["decided_by"],
                                  "external": [c["provider"], c["external_id"]] if c["provider"] else None})
    used_refs = {a["artist_ref"] for s in new_songs for a in s["artists"] if "artist_ref" in a}
    artists_out = []
    for ref in sorted(used_refs):
        artist = dict(new_artists[ref])
        extra = [r for r in raw_by_ref[ref] if r and alias_key(r) not in
                 {alias_key(v) for v in (artist["name_native"], artist["name_ko"], artist["name_latin"], *artist["aliases"]) if v}]
        artist["aliases"] = artist["aliases"] + sorted(extra)
        artists_out.append(artist)
    existing_out = [e for e in existing.values() if e["external_ids"] or e["title_latin"]]
    summary = {
        "existing_songs": len(existing_out),
        "existing_external_ids": sum(len(e["external_ids"]) for e in existing_out),
        "existing_title_latin": sum(1 for e in existing_out if e["title_latin"]),
        "new_artists": len(artists_out), "new_songs": len(new_songs),
        "new_song_external_ids": sum(len(s["external_ids"]) for s in new_songs),
        "keys": len(key_plans), "keys_to_existing_songs": sum(1 for k in key_plans if k["song_id"]),
        "key_occurrences": sum(keys[k["key_id"]]["occurrence_count"] for k in key_plans),
        "skipped": len(skipped)}
    return {"policy": POLICY, "catalog_instance_id": state["catalog_instance_id"], "report": inputs["report_name"],
            "summary": summary, "existing_songs": sorted(existing_out, key=lambda e: e["song_id"]),
            "new_artists": artists_out, "new_songs": new_songs,
            "keys": sorted(key_plans, key=lambda k: k["key_id"]), "skipped": skipped}


# --------------------------------------------------------------------------- apply

def manifest(decisions: dict) -> str:
    body = {k: decisions[k] for k in ("policy", "catalog_instance_id", "existing_songs", "new_artists", "new_songs", "keys")}
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def preallocate(conn, table: str, count: int) -> list[int]:
    if not count:
        return []
    return [r[0] for r in conn.execute(
        "SELECT nextval(pg_get_serial_sequence(%s,'id')) FROM generate_series(1,%s)", (f"public.{table}", count))]


def check(conn, decisions: dict) -> str:
    identity = rows(conn, "SELECT id::text AS id, schema_version FROM catalog_instance").fetchone()
    revisions = [r["version"] for r in rows(conn, "SELECT version FROM catalog_schema_migrations ORDER BY version")]
    if identity["schema_version"] != "catalog-v2" or "004" not in revisions:
        raise RuntimeError("Catalog must be catalog-v2 with revision 004 applied")
    if identity["id"] != decisions["catalog_instance_id"]:
        raise RuntimeError("Decision file was exported from a different catalog")
    return identity["id"]


def verify(conn, decisions: dict, *, lock: bool) -> None:
    """Abort unless every row the file relies on is exactly as exported."""
    suffix = " FOR UPDATE" if lock else ""
    song_ids = [e["song_id"] for e in decisions["existing_songs"]]
    found = {r["id"]: r for r in rows(conn, "SELECT id, version, title_latin, archived_at FROM songs WHERE id=ANY(%s)" + suffix,
                                      (song_ids,))}
    for e in decisions["existing_songs"]:
        row = found.get(e["song_id"])
        if row is None or row["archived_at"] or row["version"] != e["version"] or (e["title_latin"] and row["title_latin"]):
            raise RuntimeError(f"Song {e['song_id']} changed since export; re-export")
    key_ids = [k["key_id"] for k in decisions["keys"]]
    found = {r["id"]: r for r in rows(conn, "SELECT id, version, status FROM song_match_keys WHERE id=ANY(%s)" + suffix,
                                      (key_ids,))}
    for k in decisions["keys"]:
        row = found.get(k["key_id"])
        if row is None or row["version"] != k["key_version"] or row["status"] != "pending":
            raise RuntimeError(f"Key {k['key_id']} changed since export; re-export")
    externals = [(x["provider"], x["external_id"]) for e in decisions["existing_songs"] for x in e["external_ids"]] + \
                [(x["provider"], x["external_id"]) for s in decisions["new_songs"] for x in s["external_ids"]]
    if len(set(externals)) != len(externals):
        raise RuntimeError("Decision file assigns one external ID twice")
    if externals and conn.execute("""SELECT count(*) FROM song_external_ids e
            JOIN jsonb_to_recordset(%s::jsonb) x(provider text, external_id text)
              ON e.provider=x.provider AND e.external_id=x.external_id""",
            (Jsonb([{"provider": p, "external_id": i} for p, i in externals]),)).fetchone()[0]:
        raise RuntimeError("An external ID is already stored; re-export")
    slugs = [a["slug"] for a in decisions["new_artists"]]
    if len(set(slugs)) != len(slugs) or conn.execute("SELECT count(*) FROM artists WHERE slug=ANY(%s)", (slugs,)).fetchone()[0]:
        raise RuntimeError("An artist slug is already used; re-export")
    artist_ids = sorted({a["artist_id"] for s in decisions["new_songs"] for a in s["artists"] if "artist_id" in a})
    live = {r[0] for r in conn.execute("SELECT id FROM artists WHERE id=ANY(%s) AND archived_at IS NULL", (artist_ids,))}
    if live != set(artist_ids):
        raise RuntimeError(f"Artists missing or archived: {sorted(set(artist_ids) - live)}")


def apply(conn, decisions: dict, *, write: bool) -> dict:
    catalog_id = check(conn, decisions)
    digest = manifest(decisions)
    operation_id = uuid.uuid5(NAMESPACE, catalog_id + ":" + digest)
    if write:
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_ID,))
    if conn.execute("SELECT 1 FROM catalog_imports WHERE operation_id=%s", (operation_id,)).fetchone():
        return {"status": "already_committed", "manifest_hash": digest}
    verify(conn, decisions, lock=write)
    summary = decisions["summary"]
    if not write:
        return {"status": "would_commit", "manifest_hash": digest, **summary}

    artist_ids = dict(zip([a["ref"] for a in decisions["new_artists"]],
                          preallocate(conn, "artists", len(decisions["new_artists"]))))
    artist_rows = [{**a, "id": artist_ids[a["ref"]]} for a in decisions["new_artists"]]
    if artist_rows:
        inserted = conn.execute("""INSERT INTO artists(id,slug,name_native,name_ko,name_latin,entity_kind,is_virtual,show_in_catalog)
            OVERRIDING SYSTEM VALUE
            SELECT x.id,x.slug,x.name_native,x.name_ko,x.name_latin,x.entity_kind,x.is_virtual,x.show_in_catalog
            FROM jsonb_to_recordset(%s::jsonb) x(id integer,slug text,name_native text,name_ko text,name_latin text,
                 entity_kind text,is_virtual boolean,show_in_catalog boolean)""", (Jsonb(artist_rows),)).rowcount
        if inserted != len(artist_rows):
            raise RuntimeError("artist insert count mismatch")
    aliases = [{"artist_id": artist_ids[a["ref"]], "alias": v, "normalized_alias": alias_key(v)}
               for a in decisions["new_artists"] for v in a["aliases"]]
    if aliases:
        conn.execute("""INSERT INTO artist_aliases(artist_id,alias,normalized_alias)
            SELECT x.artist_id,x.alias,x.normalized_alias
            FROM jsonb_to_recordset(%s::jsonb) x(artist_id integer,alias text,normalized_alias text)""", (Jsonb(aliases),))

    song_ids = dict(zip([s["ref"] for s in decisions["new_songs"]], preallocate(conn, "songs", len(decisions["new_songs"]))))
    song_rows = [{**s, "id": song_ids[s["ref"]]} for s in decisions["new_songs"]]
    if song_rows:
        inserted = conn.execute("""INSERT INTO songs(id,title_native,title_latin,title_ko,language_code)
            OVERRIDING SYSTEM VALUE
            SELECT x.id,x.title_native,x.title_latin,x.title_ko,x.language_code
            FROM jsonb_to_recordset(%s::jsonb) x(id integer,title_native text,title_latin text,title_ko text,
                 language_code text)""", (Jsonb(song_rows),)).rowcount
        if inserted != len(song_rows):
            raise RuntimeError("song insert count mismatch")
    credits = [{"song_id": song_ids[s["ref"]], "artist_id": a.get("artist_id") or artist_ids[a["artist_ref"]], "position": n}
               for s in decisions["new_songs"] for n, a in enumerate(s["artists"])]
    if credits:
        conn.execute("""INSERT INTO song_artists(song_id,artist_id,position)
            SELECT x.song_id,x.artist_id,x.position FROM jsonb_to_recordset(%s::jsonb) x(song_id integer,artist_id integer,position integer)""",
            (Jsonb(credits),))

    latin = [{"id": e["song_id"], "version": e["version"], "title_latin": e["title_latin"]}
             for e in decisions["existing_songs"] if e["title_latin"]]
    if latin:
        changed = conn.execute("""UPDATE songs s SET title_latin=x.title_latin
            FROM jsonb_to_recordset(%s::jsonb) x(id integer,version integer,title_latin text)
            WHERE s.id=x.id AND s.version=x.version AND s.title_latin IS NULL""", (Jsonb(latin),)).rowcount
        if changed != len(latin):
            raise RuntimeError("Existing songs changed during apply")
    external = [{"song_id": e["song_id"], "provider": x["provider"], "external_id": x["external_id"]}
                for e in decisions["existing_songs"] for x in e["external_ids"]] + \
               [{"song_id": song_ids[s["ref"]], "provider": x["provider"], "external_id": x["external_id"]}
                for s in decisions["new_songs"] for x in s["external_ids"]]
    if external:
        conn.execute("""INSERT INTO song_external_ids(song_id,provider,external_id)
            SELECT x.song_id,x.provider,x.external_id FROM jsonb_to_recordset(%s::jsonb) x(song_id integer,provider text,external_id text)""",
            (Jsonb(external),))

    key_rows = [{"id": k["key_id"], "version": k["key_version"],
                 "song_id": k["song_id"] or song_ids[k["song_ref"]], "decided_by": k["decided_by"],
                 "evidence": {"review": POLICY, "basis": k["basis"],
                              **({"provider": k["external"][0], "external_id": k["external"][1]} if k["external"] else {})}}
                for k in decisions["keys"]]
    if key_rows:
        changed = conn.execute("""UPDATE song_match_keys k SET status='confirmed', song_id=x.song_id,
                decided_by=x.decided_by, decided_at=clock_timestamp(), evidence=k.evidence || x.evidence
            FROM jsonb_to_recordset(%s::jsonb) x(id integer,version integer,song_id integer,decided_by text,evidence jsonb)
            WHERE k.id=x.id AND k.version=x.version AND k.status='pending'""", (Jsonb(key_rows),)).rowcount
        if changed != len(key_rows):
            raise RuntimeError("Keys changed during apply")

    mapping = [{"entity_type": "artists", "ref": r, "id": i} for r, i in artist_ids.items()] + \
              [{"entity_type": "songs", "ref": r, "id": i} for r, i in song_ids.items()]
    import_id = conn.execute("""INSERT INTO catalog_imports(operation_id,catalog_instance_id,manifest_hash,source_kind,
            result_mapping,result_summary) VALUES (%s,%s,%s,'batch_import',%s,%s) RETURNING id""",
        (operation_id, catalog_id, digest, Jsonb(mapping), Jsonb({"kind": POLICY, **summary}))).fetchone()[0]
    changes = []
    for a in decisions["new_artists"]:
        changes.append({"entity_type": "artists", "entity_id": artist_ids[a["ref"]], "action": "create", "before_data": None,
                        "after_data": {k: a[k] for k in ("slug", "name_native", "name_ko", "name_latin", "entity_kind",
                                                          "is_virtual", "show_in_catalog", "aliases")},
                        "provenance": {"policy": POLICY, "ref": a["ref"], "sources": a["sources"], "confidence": a["confidence"]}})
    for s in decisions["new_songs"]:
        changes.append({"entity_type": "songs", "entity_id": song_ids[s["ref"]], "action": "create", "before_data": None,
                        "after_data": {"title_native": s["title_native"], "title_latin": s["title_latin"],
                                       "title_ko": s["title_ko"], "language_code": s["language_code"],
                                       "artist_ids": [c["artist_id"] for c in credits if c["song_id"] == song_ids[s["ref"]]],
                                       "external_ids": s["external_ids"]},
                        "provenance": {"policy": POLICY, "ref": s["ref"], "basis": s["basis"], "keys": s["keys"],
                                       "same_work_as_other_artist": s["same_work_as_other_artist"]}})
    for e in decisions["existing_songs"]:
        changes.append({"entity_type": "songs", "entity_id": e["song_id"], "action": "update",
                        "before_data": {"title_latin": None} if e["title_latin"] else {"external_ids": []},
                        "after_data": {**({"title_latin": e["title_latin"]} if e["title_latin"] else {}),
                                       "external_ids": e["external_ids"]},
                        "provenance": {"policy": POLICY, "basis": e["basis"]}})
    for k in key_rows:
        changes.append({"entity_type": "song_match_keys", "entity_id": k["id"], "action": "update",
                        "before_data": {"status": "pending", "song_id": None},
                        "after_data": {"status": "confirmed", "song_id": k["song_id"], "decided_by": k["decided_by"]},
                        "provenance": {"policy": POLICY, **k["evidence"]}})
    conn.execute("""INSERT INTO catalog_changes(import_id,entity_type,entity_id,action,before_data,after_data,provenance)
        SELECT %s,x.entity_type,x.entity_id,x.action,x.before_data,x.after_data,x.provenance
        FROM jsonb_to_recordset(%s::jsonb) x(entity_type text,entity_id integer,action text,before_data jsonb,
             after_data jsonb,provenance jsonb)""", (import_id, Jsonb(changes)))
    return {"status": "committed", "manifest_hash": digest, "import_id": import_id, **summary}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("export", help="Write the decision file (read-only DB access)")
    run = sub.add_parser("apply", help="Dry-run the decision file; --apply writes it")
    run.add_argument("--apply", action="store_true")
    parser.add_argument("--file", type=Path, default=DECISIONS)
    parser.add_argument("--report-dir", type=Path, default=REPORT_DIR)
    args = parser.parse_args()
    writing = args.command == "apply" and args.apply
    with psycopg.connect(migrate_catalog.load_connection(), connect_timeout=20) as conn:
        migrate_catalog.configure_transaction(conn, read_only=not writing)
        if args.command == "export":
            decisions = plan(load_state(conn), load_inputs(args.report_dir))
            conn.rollback()
            decisions["exported_at"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            args.file.write_text(json.dumps(decisions, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            print(json.dumps({"file": str(args.file), **decisions["summary"]}, ensure_ascii=False, indent=2))
            return 0
        decisions = json.loads(args.file.read_text(encoding="utf-8"))
        if decisions.get("policy") != POLICY:
            raise SystemExit("Unexpected decision file policy")
        result = apply(conn, decisions, write=writing)
        if writing:
            conn.commit()
        else:
            conn.rollback()
            result["mode"] = "dry-run"
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
