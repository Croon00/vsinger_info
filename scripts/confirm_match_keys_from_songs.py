"""Confirm pending setlist match keys that name an existing song exactly (plan step 7).

``export`` (READ ONLY) compares every pending ``song_match_keys`` row with active songs:

  * the key title equals a song title or alias, AND
  * the key's original-artist text equals a spelling of one of that song's artists.
    Both are compared in ``loose`` form (normalize_text plus spaces and tilde/dash
    variants folded: ``松永 依織`` meets ``松永依織``); the stored key is never changed.
    Native names and aliases decide first; Korean/Latin names are used only when no
    artist carries the text as a native name or alias (``Hachi`` is HACHI, not ハチ).
  * a key without artist text is tried as ``title / artist`` or ``title - artist`` splits
    (same split rule as the YouTube collection path); all matching splits must name one song.

Exactly one song -> ``song:<id>`` (``exact`` or ``split``). Several songs -> review, not
confirmed by default. Keys without any artist text that cannot be split are left alone.
``--import-id N`` limits the candidate songs to the ones created by that catalog import
(for example the songs made from Spotify recordings, import 1017).

The export also simulates ``link_performances_from_match_keys.py`` with the planned keys
added, so the decision file carries the number of performances each key would link.

``review-import`` folds the edited review file back (rows missing from it are dropped);
``apply`` dry-runs; ``apply --apply`` confirms the keys in ONE transaction with a
catalog_imports receipt and one catalog_changes row per key. Keys changed since export
abort the run; a second apply is ``already_committed``. Performances are linked
afterwards with ``link_performances_from_match_keys.py``.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
import uuid
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.core.song_keys import KEY_VERSION, lookup_keys, resolve_key  # noqa: E402
from app.services.song_candidates import loose  # noqa: E402

POLICY = "match-key-song-confirm-v1"
NAMESPACE = uuid.UUID("2b7e5d90-3f41-4c8a-b6d2-9e0a1c7f4d35")
LOCK_ID = 731064923  # shared with the other match-key writers
DECISIONS = ROOT / "migrations" / "catalog" / "match-key-confirmations-{n}.json"
REPORTS = ROOT / "db-migration" / "reports" / "match-key-confirmations"

_spec = importlib.util.spec_from_file_location("migrate_catalog", ROOT / "scripts" / "migrate_catalog.py")
migrate_catalog = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migrate_catalog)


def rows(conn, query, params=None):
    return conn.cursor(row_factory=dict_row).execute(query, params)


def load_state(conn, import_id: int | None = None) -> dict:
    identity = rows(conn, "SELECT id::text AS id FROM catalog_instance").fetchone()["id"]
    songs = {r["id"]: {**r, "titles": {loose(r["title_native"])}, "artists": []} for r in rows(conn, """
        SELECT s.id, s.title_native FROM songs s WHERE s.archived_at IS NULL
          AND NOT EXISTS (SELECT 1 FROM song_merges m WHERE m.source_song_id=s.id)""")}
    for r in rows(conn, "SELECT song_id, alias FROM song_aliases"):
        if r["song_id"] in songs:
            songs[r["song_id"]]["titles"].add(loose(r["alias"]))
    for r in rows(conn, "SELECT song_id, artist_id FROM song_artists ORDER BY song_id, position, id"):
        if r["song_id"] in songs:
            songs[r["song_id"]]["artists"].append(r["artist_id"])
    artists = {r["id"]: {**r, "primary": {loose(r["name_native"])},
                         "secondary": {loose(v) for v in (r["name_ko"], r["name_latin"]) if v}}
               for r in rows(conn, "SELECT id, name_native, name_ko, name_latin FROM artists WHERE archived_at IS NULL")}
    for r in rows(conn, "SELECT artist_id, alias FROM artist_aliases"):
        if r["artist_id"] in artists:
            artists[r["artist_id"]]["primary"].add(loose(r["alias"]))
    candidates = None
    if import_id is not None:
        candidates = {r["entity_id"] for r in rows(conn, """SELECT entity_id FROM catalog_changes
            WHERE import_id=%s AND entity_type='songs' AND action='create'""", (import_id,))}
    keys = rows(conn, """SELECT id, version, title_key, artist_key, sample_raw_title, sample_raw_artist, occurrence_count
        FROM song_match_keys WHERE key_version=%s AND status='pending' ORDER BY occurrence_count DESC, id""",
                (KEY_VERSION,)).fetchall()
    confirmed = {(r["title_key"], r["artist_key"]): r["song_id"] for r in rows(conn, """
        SELECT k.title_key, k.artist_key, k.song_id FROM song_match_keys k JOIN songs s ON s.id=k.song_id
        WHERE k.key_version=%s AND k.status='confirmed' AND s.archived_at IS NULL
          AND NOT EXISTS (SELECT 1 FROM song_merges m WHERE m.source_song_id=k.song_id)""", (KEY_VERSION,))}
    performances = rows(conn, """SELECT p.raw_title, p.raw_artist FROM performances p
        JOIN live_archives la ON la.id=p.archive_id AND la.archived_at IS NULL
        WHERE p.archived_at IS NULL AND p.song_id IS NULL""").fetchall()
    return {"catalog_instance_id": identity, "songs": songs, "artists": artists, "candidates": candidates,
            "keys": keys, "confirmed": confirmed, "performances": performances}


def plan(state: dict) -> dict:
    """Pure: pending keys -> exactly-matching songs, with the performances they would link."""
    songs, artists = state["songs"], state["artists"]
    allowed = state["candidates"]
    primary, secondary = defaultdict(set), defaultdict(set)
    for artist_id, a in artists.items():
        for s in a["primary"]:
            primary[s].add(artist_id)
        for s in a["secondary"]:
            secondary[s].add(artist_id)
    by_title = defaultdict(set)
    for song_id, song in songs.items():
        for t in song["titles"]:
            by_title[t].add(song_id)

    def matches(title: str, artist: str) -> set[int]:
        title, artist = loose(title), loose(artist)
        if not title or not artist:
            return set()
        who = primary.get(artist) or secondary.get(artist) or set()
        return {s for s in by_title.get(title, set()) if who & set(songs[s]["artists"])}

    def brief(song_id):
        return {"song_id": song_id, "title": songs[song_id]["title_native"],
                "artists": [artists[a]["name_native"] for a in songs[song_id]["artists"] if a in artists]}

    confirm, review = [], []
    for key in state["keys"]:
        found, basis = matches(key["title_key"], key["artist_key"]), "exact"
        if not found and not key["artist_key"]:
            splits = [matches(t, a) for t, a in lookup_keys(key["sample_raw_title"], None)[1:]]
            found = set().union(*splits) if splits else set()
            basis = "split"
        if not found:
            continue
        # With --import-id, a key is taken only when every matching song is from that import;
        # a key that also names an older song goes to review instead.
        if allowed is not None and not found & allowed:
            continue
        entry = {"key_id": key["id"], "key_version": key["version"], "title_key": key["title_key"],
                 "artist_key": key["artist_key"], "raw_title": key["sample_raw_title"],
                 "raw_artist": key["sample_raw_artist"], "occurrences": key["occurrence_count"], "basis": basis}
        if len(found) == 1:
            confirm.append({**entry, "song_id": next(iter(found)), "song": brief(next(iter(found)))})
        else:
            review.append({**entry, "candidates": [brief(s) for s in sorted(found)]})

    # Simulate the performance link step with the planned keys added.
    planned = {(c["title_key"], c["artist_key"]): c["song_id"] for c in confirm}
    merged = {**state["confirmed"], **planned}
    per_key = Counter()
    for p in state["performances"]:
        resolved = resolve_key(lookup_keys(p["raw_title"], p["raw_artist"]), merged)
        if resolved in planned:
            per_key[resolved] += 1
    for c in confirm:
        c["would_link"] = per_key[(c["title_key"], c["artist_key"])]
    summary = {"pending_keys": len(state["keys"]), "confirm": len(confirm), "review": len(review),
               "confirm_by_basis": dict(Counter(c["basis"] for c in confirm)),
               "songs": len({c["song_id"] for c in confirm}),
               "would_link_performances": sum(per_key.values()),
               "candidate_songs": len(allowed) if allowed is not None else len(songs)}
    return {"policy": POLICY, "catalog_instance_id": state["catalog_instance_id"], "summary": summary,
            "confirm": confirm, "review": review}


# --------------------------------------------------------------------------- review file

def _cell(value) -> str:
    return str(value).replace("|", "／").replace("\n", " ") if value not in (None, "") else "-"


def _song(brief) -> str:
    return f"{brief['song_id']} {brief['title']} / {'·'.join(brief['artists']) or '-'}"


def render_review(decisions: dict, path: str) -> str:
    s = decisions["summary"]
    lines = ["# 원문 키 → 곡 확정 검수", "",
             f"결정 파일: `{path}`. pending 키 {s['pending_keys']}개 중 곡과 정확히 맞는 키 {s['confirm'] + s['review']}개. "
             f"확정하면 미연결 가창 {s['would_link_performances']}건이 연결된다(가창 연결은 확정 뒤 별도 단계).", "",
             "- `결정` 칸: `song:<곡 id>`는 그 곡으로 확정, `-`는 확정하지 않음. 나머지 행은 그대로 두면 승인으로 본다.",
             "- 근거: `exact` 원문 곡명·원곡자가 곡 제목·명의와 같음, `split` 원곡자 칸이 비어 있어 `곡명 / 원곡자`를 나눠 맞춤.", "",
             f"## 1. 확정 ({s['confirm']}개 키)", "",
             "| 키 id | 원문 곡명 | 원문 원곡자 | 가창 | 결정 | 곡 | 근거 |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for c in decisions["confirm"]:
        lines.append(f"| {c['key_id']} | {_cell(c['raw_title'])} | {_cell(c['raw_artist'])} | {c['would_link']} | "
                     f"song:{c['song_id']} | {_cell(_song(c['song']))} | {c['basis']} |")
    lines += ["", f"## 2. 검수 필요: 후보 곡 여러 개 ({s['review']}개 키)", "",
              "| 키 id | 원문 곡명 | 원문 원곡자 | 가창 | 결정 | 후보 곡 | 근거 |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for r in decisions["review"]:
        lines.append(f"| {r['key_id']} | {_cell(r['raw_title'])} | {_cell(r['raw_artist'])} | {r['occurrences']} | - | "
                     f"{_cell('; '.join(_song(c) for c in r['candidates']))} | {r['basis']} |")
    return "\n".join(lines) + "\n"


def read_review(path: Path) -> dict[str, dict[int, str]]:
    sections, current = {}, None
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if line.startswith("## "):
            current = line[3:4]
            sections[current] = {}
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if current in ("1", "2") and len(cells) == 7 and cells[0].isdigit():
            sections[current][int(cells[0])] = cells[4]
    return sections


def apply_review(decisions: dict, sections: dict[str, dict[int, str]], song_ids: set[int] | None = None):
    changes, confirm = [], []
    entries = [(c, "1") for c in decisions["confirm"]] + [(r, "2") for r in decisions["review"]]
    for entry, section in entries:
        decision = sections.get(section, {}).get(entry["key_id"])
        if decision is None:
            if section == "1":
                changes.append({"key_id": entry["key_id"], "change": "drop", "reason": "not in review"})
            continue
        if decision in ("-", ""):
            if section == "1":
                changes.append({"key_id": entry["key_id"], "change": "drop"})
            continue
        match = re.fullmatch(r"song:(\d+)", decision)
        if not match:
            raise ValueError(f"key {entry['key_id']}: unknown decision {decision!r}")
        song_id = int(match.group(1))
        if song_ids is not None and song_id not in song_ids:
            raise ValueError(f"key {entry['key_id']}: song {song_id} does not exist")
        manual = section == "2" or song_id != entry.get("song_id")
        if manual:
            changes.append({"key_id": entry["key_id"], "change": decision})
        confirm.append({k: v for k, v in entry.items() if k != "candidates"} |
                       {"song_id": song_id, "basis": "user_review" if manual else entry["basis"]})
    return {**decisions, "confirm": confirm, "user_review": changes, "reviewed": True}, changes


# --------------------------------------------------------------------------- apply

def manifest(decisions: dict) -> str:
    body = {"policy": decisions["policy"], "catalog_instance_id": decisions["catalog_instance_id"],
            "confirm": [{k: c[k] for k in ("key_id", "key_version", "song_id", "basis")} for c in decisions["confirm"]]}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def apply(conn, decisions: dict, *, write: bool) -> dict:
    identity = rows(conn, "SELECT id::text AS id FROM catalog_instance").fetchone()["id"]
    if identity != decisions["catalog_instance_id"] or decisions.get("policy") != POLICY:
        raise RuntimeError("Decision file was exported from a different catalog or policy")
    digest = manifest(decisions)
    operation_id = uuid.uuid5(NAMESPACE, identity + ":" + digest)
    if write:
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_ID,))
    if conn.execute("SELECT 1 FROM catalog_imports WHERE operation_id=%s", (operation_id,)).fetchone():
        return {"status": "already_committed", "manifest_hash": digest}
    payload = [{"id": c["key_id"], "version": c["key_version"], "song_id": c["song_id"],
                "decided_by": "manual" if c["basis"] == "user_review" else "existing_link",
                "evidence": {"review": POLICY, "basis": c["basis"]}} for c in decisions["confirm"]]
    if len({p["id"] for p in payload}) != len(payload):
        raise RuntimeError("A key is planned twice; re-export")
    matching = """FROM jsonb_to_recordset(%s::jsonb) x(id integer,version integer,song_id integer,decided_by text,evidence jsonb)
        JOIN songs s ON s.id=x.song_id AND s.archived_at IS NULL
          AND NOT EXISTS (SELECT 1 FROM song_merges m WHERE m.source_song_id=s.id)
        WHERE k.id=x.id AND k.version=x.version AND k.status='pending'"""
    summary = {"keys": len(payload), "songs": len({p["song_id"] for p in payload}),
               "by_basis": dict(Counter(c["basis"] for c in decisions["confirm"]))}
    if not write:
        matched = conn.execute("SELECT count(*) FROM song_match_keys k, " + matching.removeprefix("FROM "),
                               (Jsonb(payload),)).fetchone()[0]
        if matched != len(payload):
            raise RuntimeError("Keys or songs changed since export; re-export")
        return {"status": "would_commit", "manifest_hash": digest, **summary}
    changed = conn.execute("""UPDATE song_match_keys k SET status='confirmed', song_id=x.song_id,
            decided_by=x.decided_by, decided_at=clock_timestamp(), evidence=k.evidence || x.evidence """ + matching,
                           (Jsonb(payload),)).rowcount
    if changed != len(payload):
        raise RuntimeError("Keys or songs changed since export; re-export")
    import_id = conn.execute("""INSERT INTO catalog_imports(operation_id,catalog_instance_id,manifest_hash,source_kind,
            result_summary) VALUES (%s,%s,%s,'batch_import',%s) RETURNING id""",
        (operation_id, identity, digest, Jsonb({"kind": POLICY, **summary}))).fetchone()[0]
    changes = [{"entity_id": p["id"], "before_data": {"status": "pending", "song_id": None},
                "after_data": {"status": "confirmed", "song_id": p["song_id"], "decided_by": p["decided_by"]},
                "provenance": {"policy": POLICY, **p["evidence"]}} for p in payload]
    conn.execute("""INSERT INTO catalog_changes(import_id,entity_type,entity_id,action,before_data,after_data,provenance)
        SELECT %s,'song_match_keys',x.entity_id,'update',x.before_data,x.after_data,x.provenance
        FROM jsonb_to_recordset(%s::jsonb) x(entity_id integer,before_data jsonb,after_data jsonb,provenance jsonb)""",
                 (import_id, Jsonb(changes)))
    return {"status": "committed", "manifest_hash": digest, "import_id": import_id, **summary}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--round", type=int, default=1)
    sub = parser.add_subparsers(dest="command", required=True)
    exp = sub.add_parser("export", help="Write the decision + review files (read-only DB access)")
    exp.add_argument("--import-id", type=int, help="Only songs created by this catalog import")
    sub.add_parser("review-import", help="Fold the edited review file into the decision file (no DB access)")
    run = sub.add_parser("apply", help="Dry-run the decision file; --apply writes it")
    run.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    path = Path(str(DECISIONS).format(n=args.round))
    review_path = REPORTS / f"review-{args.round}.md"
    if args.command == "review-import":
        (REPORTS / f"review-{args.round}.user-edited.md").write_text(review_path.read_text(encoding="utf-8"),
                                                                    encoding="utf-8")
        decisions, changes = apply_review(json.loads(path.read_text(encoding="utf-8")), read_review(review_path))
        path.write_text(json.dumps(decisions, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(json.dumps({"file": str(path.relative_to(ROOT)), "changes": changes, "confirm": len(decisions["confirm"])},
                         ensure_ascii=False, indent=2))
        return 0
    writing = args.command == "apply" and args.apply
    with psycopg.connect(migrate_catalog.load_connection(), connect_timeout=20) as conn:
        migrate_catalog.configure_transaction(conn, read_only=not writing)
        if args.command == "export":
            state = load_state(conn, args.import_id)
            conn.rollback()
            decisions = plan(state)
            decisions["import_id"] = args.import_id
            decisions["exported_at"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            path.write_text(json.dumps(decisions, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            REPORTS.mkdir(parents=True, exist_ok=True)
            review_path.write_text(render_review(decisions, str(path.relative_to(ROOT))), encoding="utf-8")
            print(json.dumps({"file": str(path.relative_to(ROOT)), "review_file": str(review_path.relative_to(ROOT)),
                              **decisions["summary"]}, ensure_ascii=False, indent=2))
            return 0
        result = apply(conn, json.loads(path.read_text(encoding="utf-8")), write=writing)
        if writing:
            conn.commit()
        else:
            conn.rollback()
            result["mode"] = "dry-run"
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
