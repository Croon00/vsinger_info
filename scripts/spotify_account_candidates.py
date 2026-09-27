"""Find, review and register Spotify artist accounts for catalog-visible artists.

``research`` (READ ONLY on the catalog) takes every active ``show_in_catalog`` artist
without an active Spotify link, looks up
  * Wikidata: Spotify artist ID (P1902) of the item that holds the artist's YouTube
    channel ID (P2397) — an ID-to-ID match, never a name search,
  * Spotify search (artist type) for each name variant (native, latin, aliases),
and for every candidate whose name equals a variant, fetches its album titles and top
tracks and compares them with the artist's credited songs and the titles of videos on
the artist's own YouTube channels. Provider responses are cached in the git-ignored
db-migration/reports/spotify-accounts/cache/. It writes candidates.json there.

``export`` turns candidates.json (+ optional research-*.json from web verification and
the manual file) into migrations/catalog/spotify-account-decisions-1.json and review.md:
``accept`` needs Wikidata or a title overlap on a single name-exact candidate;
everything else is ``review`` (a person decides) or ``skip`` (no candidate).

``review-import`` records the user's edits of review.md (the Spotify ID column; '-'
drops the artist) and the approval of every listed row in the manual file.

``apply`` dry-runs the decision file; ``apply --apply`` creates the external_accounts
rows (``collection_enabled=false``; collection is enabled separately) and one owner
link per artist in ONE transaction with a catalog_imports receipt and catalog_changes
rows. An account ID that already exists is linked instead of duplicated. Artists whose
links changed since export abort the whole run and a second apply is a no-op.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import httpx
import psycopg
from dotenv import dotenv_values
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.core.song_keys import normalize_text  # noqa: E402

POLICY = "spotify-account-candidates-v1"
NAMESPACE = uuid.UUID("5d0c7e42-1a9b-4f63-8e27-b94f0a6d13c8")
REPORT_DIR = ROOT / "db-migration" / "reports" / "spotify-accounts"
DECISIONS = ROOT / "migrations" / "catalog" / "spotify-account-decisions-1.json"
MANUAL = ROOT / "migrations" / "catalog" / "spotify-account-manual-1.json"
SPOTIFY_ID = re.compile(r"^[0-9A-Za-z]{22}$")
DECISION_VALUES = {"accept", "review", "skip"}
RELATIONSHIPS = {"owner", "member"}
USER_AGENT = "schedule_music-catalog/1.0 (spotify account research)"

_spec = importlib.util.spec_from_file_location("migrate_catalog", ROOT / "scripts" / "migrate_catalog.py")
migrate_catalog = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migrate_catalog)


def rows(conn, query, params=None):
    return conn.cursor(row_factory=dict_row).execute(query, params)


def squash(value: str | None) -> str:
    """Comparison form: NFKC/casefold, and no spaces or middle dots (松田 聖子 == 松田聖子)."""
    return re.sub(r"[\s・･·]", "", normalize_text(value))


# --- catalog reads -----------------------------------------------------------------

def load_artists(conn) -> list[dict]:
    artists = rows(conn, """SELECT a.id, a.version, a.name_native, a.name_ko, a.name_latin, a.entity_kind, a.is_virtual
        FROM artists a WHERE a.show_in_catalog AND a.archived_at IS NULL
          AND NOT EXISTS (SELECT 1 FROM artist_external_accounts ae JOIN external_accounts e ON e.id=ae.account_id
                          WHERE ae.artist_id=a.id AND e.platform='spotify' AND e.archived_at IS NULL)
        ORDER BY a.id""").fetchall()
    ids = [a["id"] for a in artists]
    aliases, songs, channels, videos = {}, {}, {}, {}
    for r in rows(conn, "SELECT artist_id, alias FROM artist_aliases WHERE artist_id=ANY(%s)", (ids,)):
        aliases.setdefault(r["artist_id"], []).append(r["alias"])
    for r in rows(conn, """SELECT sa.artist_id, s.title_native FROM song_artists sa JOIN songs s ON s.id=sa.song_id
        WHERE sa.artist_id=ANY(%s) AND s.archived_at IS NULL""", (ids,)):
        songs.setdefault(r["artist_id"], []).append(r["title_native"])
    for r in rows(conn, """SELECT ae.artist_id, e.id, e.platform_id FROM artist_external_accounts ae
        JOIN external_accounts e ON e.id=ae.account_id
        WHERE ae.artist_id=ANY(%s) AND ae.relationship='owner' AND e.platform='youtube' AND e.archived_at IS NULL
          AND e.platform_id ~ '^UC[A-Za-z0-9_-]{22}$'""", (ids,)):
        channels.setdefault(r["artist_id"], []).append(r["platform_id"])
        for v in rows(conn, "SELECT title FROM videos WHERE source_account_id=%s AND title IS NOT NULL", (r["id"],)):
            videos.setdefault(r["artist_id"], []).append(v["title"])
    for a in artists:
        a.update(aliases=aliases.get(a["id"], []), songs=songs.get(a["id"], []),
                 youtube_channels=channels.get(a["id"], []), video_titles=videos.get(a["id"], []))
    return artists


def variants(artist: dict) -> list[str]:
    seen, out = set(), []
    for value in [artist["name_native"], artist["name_latin"], *artist["aliases"]]:
        if value and squash(value) not in seen:
            seen.add(squash(value))
            out.append(value)
    return out


# --- providers (cached) ------------------------------------------------------------

class Cache:
    def __init__(self, path: Path):
        self.path = path
        self.data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        self.requests = 0

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False) + "\n", encoding="utf-8")


class Spotify:
    def __init__(self, cache: Cache, interval: float = 0.5):
        env = dotenv_values(ROOT / ".env")
        self.client = httpx.Client(timeout=30, headers={"User-Agent": USER_AGENT})
        self.auth = (env.get("SPOTIFY_CLIENT_ID") or "", env.get("SPOTIFY_CLIENT_SECRET") or "")
        self.token, self.cache, self.interval, self.last = None, cache, interval, 0.0

    def get(self, path: str, params: dict) -> dict:
        key = "spotify:" + path + "?" + json.dumps(params, sort_keys=True, ensure_ascii=False)
        if key in self.cache.data:
            return self.cache.data[key]
        for attempt in range(4):
            if not self.token:
                if not all(self.auth):
                    raise RuntimeError("SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET are not configured")
                self.token = self.client.post("https://accounts.spotify.com/api/token", auth=self.auth,
                                              data={"grant_type": "client_credentials"}).raise_for_status().json()["access_token"]
            time.sleep(max(0.0, self.last + self.interval - time.monotonic()))
            self.last = time.monotonic()
            response = self.client.get("https://api.spotify.com/v1" + path, params=params,
                                       headers={"Authorization": "Bearer " + self.token})
            self.cache.requests += 1
            if response.status_code == 401:
                self.token = None
                continue
            if response.status_code == 429 or response.status_code >= 500:
                time.sleep(min(30.0, float(response.headers.get("Retry-After") or 2 ** attempt)))
                continue
            if response.status_code == 404:
                value = {}
            else:
                value = response.raise_for_status().json()
            self.cache.data[key] = value
            return value
        raise RuntimeError(f"Spotify request kept failing: {path}")


def wikidata_spotify(cache: Cache, channels: list[str]) -> dict[str, list[dict]]:
    """YouTube channel ID -> [{qid, spotify_id, label}] via P2397 -> P1902."""
    key = "wikidata:" + ",".join(sorted(channels))
    if key not in cache.data:
        values = " ".join(f'"{c}"' for c in sorted(channels))
        query = f"""SELECT ?channel ?item ?spotify ?label WHERE {{ VALUES ?channel {{ {values} }}
          ?item wdt:P2397 ?channel ; wdt:P1902 ?spotify .
          OPTIONAL {{ ?item rdfs:label ?label FILTER(lang(?label)='ja') }} }}"""
        response = httpx.get("https://query.wikidata.org/sparql", params={"query": query, "format": "json"},
                             headers={"User-Agent": USER_AGENT, "Accept": "application/sparql-results+json"}, timeout=60)
        cache.requests += 1
        cache.data[key] = response.raise_for_status().json()["results"]["bindings"]
    found = {}
    for b in cache.data[key]:
        found.setdefault(b["channel"]["value"], []).append({
            "qid": b["item"]["value"].rsplit("/", 1)[-1], "spotify_id": b["spotify"]["value"],
            "label": b.get("label", {}).get("value")})
    return found


def title_overlap(names: list[str], titles: list[str], haystack: list[str]) -> list[str]:
    """Candidate track/album names that equal a credited song title or appear in an own-channel video title."""
    songs = {squash(t) for t in titles}
    videos = [squash(t) for t in haystack]
    hits = []
    for name in dict.fromkeys(names):
        key = squash(re.sub(r"\s*[\(（\[【].*?[\)）\]】]\s*|\s+-\s+.*$", "", name))  # drop "(feat. …)", " - Remix"
        if len(key) >= 2 and (key in songs or any(key in v for v in videos)):
            hits.append(name)
    return hits


def profile(spotify: Spotify, artist_id: str, artist: dict) -> dict:
    info = spotify.get(f"/artists/{artist_id}", {})
    albums = []
    for offset in range(0, 50, 10):
        page = spotify.get(f"/artists/{artist_id}/albums", {"include_groups": "album,single", "market": "JP",
                                                             "limit": 10, "offset": offset})
        albums += [a["name"] for a in page.get("items", [])]
        if not page.get("next"):
            break
    top = [t["name"] for t in spotify.get(f"/artists/{artist_id}/top-tracks", {"market": "JP"}).get("tracks", [])]
    return {"spotify_id": artist_id, "name": info.get("name"), "followers": (info.get("followers") or {}).get("total"),
            "genres": info.get("genres") or [], "albums": albums[:50], "top_tracks": top,
            "overlap": title_overlap(albums + top, artist["songs"], artist["video_titles"])}


def research(artists: list[dict], cache: Cache) -> list[dict]:
    spotify = Spotify(cache)
    wikidata = wikidata_spotify(cache, [c for a in artists for c in a["youtube_channels"]])
    out = []
    for n, artist in enumerate(artists, 1):
        names = {squash(v) for v in variants(artist)}
        search, exact = [], {}
        for query in variants(artist):
            for item in spotify.get("/search", {"q": query, "type": "artist", "limit": 10, "market": "JP"}
                                    ).get("artists", {}).get("items", []):
                search.append({"spotify_id": item["id"], "name": item["name"]})
                if squash(item["name"]) in names:
                    exact[item["id"]] = item["name"]
        wd = [w for c in artist["youtube_channels"] for w in wikidata.get(c, [])]
        for w in wd:
            exact.setdefault(w["spotify_id"], None)
        candidates = [{**profile(spotify, sid, artist), "wikidata": [w["qid"] for w in wd if w["spotify_id"] == sid]}
                      for sid in exact if SPOTIFY_ID.match(sid)]
        out.append({"artist_id": artist["id"], "version": artist["version"], "name_native": artist["name_native"],
                    "name_latin": artist["name_latin"], "name_ko": artist["name_ko"], "is_virtual": artist["is_virtual"],
                    "variants": variants(artist), "songs": artist["songs"][:20], "video_titles": len(artist["video_titles"]),
                    "candidates": candidates,
                    "search_other": [s for s in {s["spotify_id"]: s for s in search}.values() if s["spotify_id"] not in exact][:5]})
        if n % 10 == 0:
            cache.save()
    cache.save()
    return out


# --- decisions -----------------------------------------------------------------------

def decide(item: dict) -> dict:
    """Pre-fill one decision. accept only with ID-level (Wikidata) or content (title overlap) evidence."""
    names = {squash(v) for v in item["variants"]}
    exact = [c for c in item["candidates"] if squash(c["name"]) in names]
    wikidata = {c["spotify_id"] for c in item["candidates"] if c["wikidata"]}
    strong = [c for c in exact if c["wikidata"]]
    overlap = [c for c in exact if c["overlap"]]
    pick, decision, basis = None, "skip", "no_candidate"
    # Wikidata sometimes holds a member's or a second profile (supercell -> "ryo (supercell)"),
    # so it decides alone only when its profile also carries the artist's name.
    if len(wikidata) == 1 and len(strong) == 1 and (strong[0]["overlap"] or not overlap):
        pick, decision, basis = strong[0], "accept", "wikidata"
    elif len(overlap) == 1 and not wikidata:
        pick, decision, basis = overlap[0], "accept", "title_overlap"
    elif item["candidates"]:
        pick = max(exact or item["candidates"], key=lambda c: (bool(c["wikidata"]), len(c["overlap"]), c["followers"] or 0))
        decision, basis = "review", "name_only" if not overlap else "several_overlap"
    return {"decision": decision, "basis": basis, "pick": pick}


def export(research_rows: list[dict], web: list[dict], manual: dict) -> dict:
    web_by = {w["artist_id"]: w for w in web}
    forced = {m["artist_id"]: m for m in manual.get("accounts", [])}
    items = []
    for r in research_rows:
        d = decide(r)
        pick = d["pick"]
        item = {"artist_id": r["artist_id"], "version": r["version"], "name_native": r["name_native"],
                "decision": d["decision"], "basis": d["basis"], "relationship": "owner",
                "spotify_id": pick["spotify_id"] if pick else None, "spotify_name": pick["name"] if pick else None,
                "evidence": ({"wikidata": pick["wikidata"], "overlap": pick["overlap"][:5],
                              "followers": pick["followers"]} if pick else {}),
                "alternatives": [{"spotify_id": c["spotify_id"], "name": c["name"], "overlap": c["overlap"][:3]}
                                 for c in r["candidates"] if not pick or c["spotify_id"] != pick["spotify_id"]],
                "note": None}
        w = web_by.get(r["artist_id"])
        if w and d["decision"] != "accept":
            # Web verification (official site / profile links) for rows without automatic evidence.
            if w.get("spotify_id") and SPOTIFY_ID.match(w["spotify_id"]) and w.get("confidence") == "high":
                item.update(decision="accept", basis="web_verified", spotify_id=w["spotify_id"],
                            spotify_name=w.get("spotify_name"), relationship=w.get("relationship") or "owner")
            elif w.get("spotify_id") and SPOTIFY_ID.match(w["spotify_id"]):
                item.update(decision="review", basis="web_candidate", spotify_id=w["spotify_id"],
                            spotify_name=w.get("spotify_name"), relationship=w.get("relationship") or "owner")
            else:
                item.update(decision="skip", basis="web_not_found", spotify_id=None, spotify_name=None)
            item["evidence"] = {**item["evidence"], "web": w.get("sources", []), "web_note": w.get("note")}
        m = forced.get(r["artist_id"])
        if m:
            item.update(decision=m.get("decision", "accept" if m.get("spotify_id") else "skip"),
                        spotify_id=m.get("spotify_id"), spotify_name=m.get("spotify_name", item["spotify_name"]),
                        relationship=m.get("relationship", item["relationship"]), basis=m.get("basis", "user_review"),
                        note=m.get("note"))
            if not item["spotify_id"]:
                item["decision"] = "skip"
        items.append(item)
    approval = manual.get("user_review", {})
    if approval.get("approved") == "all":
        listed = set(approval.get("listed", []))
        for item in items:
            if item["artist_id"] in listed and item["spotify_id"] and item["decision"] == "review":
                item.update(decision="accept", note=item["note"] or "approved in user review")
    summary = {k: sum(i["decision"] == k for i in items) for k in sorted(DECISION_VALUES)}
    return {"policy": POLICY, "items": items, "summary": summary}


BASIS = {"wikidata": "Wikidata(YouTube 채널 ID)", "title_overlap": "곡·영상 제목 일치", "name_only": "이름만 일치",
         "several_overlap": "여러 후보가 제목 일치", "no_candidate": "후보 없음", "web_verified": "웹 확인(공식 링크)",
         "web_candidate": "웹 후보(확인 약함)", "web_not_found": "웹에서도 못 찾음", "user_review": "사용자 수정"}


def render_review(decisions: dict) -> str:
    lines = ["# Spotify 계정 후보 검수", "",
             f"결정 파일: `{DECISIONS.relative_to(ROOT).as_posix()}`. **Spotify ID** 칸을 고치면 그 ID로, `-`로 바꾸면 등록하지 않는다. "
             "나머지 행은 그대로 두면 승인으로 본다. 링크는 확인용이다.", "",
             "| # | artist_id | 아티스트 | 판정 | Spotify ID | Spotify 이름 | 근거 | 일치한 제목 | 다른 후보 |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    order = {"accept": 0, "review": 1, "skip": 2}
    for n, i in enumerate(sorted(decisions["items"], key=lambda i: (order[i["decision"]], i["artist_id"])), 1):
        sid = i["spotify_id"] or "-"
        link = f"[{i['spotify_name'] or '열기'}](https://open.spotify.com/artist/{sid})" if i["spotify_id"] else "-"
        ev = i["evidence"]
        matched = ", ".join(ev.get("overlap", [])[:3]) or "-"
        alts = ", ".join(f"{a['name']} `{a['spotify_id']}`" for a in i["alternatives"][:2]) or "-"
        basis = BASIS.get(i["basis"], i["basis"]) + (f" ({i['relationship']})" if i["relationship"] != "owner" else "")
        lines.append(f"| {n} | {i['artist_id']} | {i['name_native']} | {i['decision']} | {sid} | {link} | {basis} | "
                     f"{matched} | {alts} |")
    return "\n".join(lines) + "\n"


def read_review(path: Path) -> dict[int, str | None]:
    ids = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 9 and cells[1].isdigit():
            value = cells[4].strip("` ")
            ids[int(cells[1])] = None if value in ("", "-") else value
    return ids


def review_edits(decisions: dict, ids: dict[int, str | None]) -> list[dict]:
    edits = []
    for item in decisions["items"]:
        if item["artist_id"] in ids and ids[item["artist_id"]] != item["spotify_id"]:
            value = ids[item["artist_id"]]
            if value is not None and not SPOTIFY_ID.match(value):
                raise RuntimeError(f"Artist {item['artist_id']}: '{value}' is not a 22-character Spotify artist ID")
            edits.append({"artist_id": item["artist_id"], "spotify_id": value, "was": item["spotify_id"]})
    return edits


# --- apply ---------------------------------------------------------------------------

def manifest(decisions: dict) -> str:
    body = {"policy": decisions["policy"], "catalog_instance_id": decisions["catalog_instance_id"],
            "accept": [{k: i[k] for k in ("artist_id", "version", "spotify_id", "relationship")}
                       for i in decisions["items"] if i["decision"] == "accept"]}
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def apply(conn, decisions: dict, *, write: bool) -> dict:
    identity = rows(conn, "SELECT id::text AS id, schema_version FROM catalog_instance").fetchone()
    if identity["schema_version"] != "catalog-v2" or identity["id"] != decisions.get("catalog_instance_id"):
        raise RuntimeError("Decision file was exported from a different catalog")
    if decisions.get("policy") != POLICY:
        raise RuntimeError("Unexpected decision file policy")
    accepted = [i for i in decisions["items"] if i["decision"] == "accept"]
    bad = [i["artist_id"] for i in decisions["items"] if i["decision"] not in DECISION_VALUES or
           (i["decision"] == "accept" and (not SPOTIFY_ID.match(i.get("spotify_id") or "")
                                           or i["relationship"] not in RELATIONSHIPS))]
    if bad:
        raise RuntimeError(f"Invalid decisions for artists {bad}")
    digest = manifest(decisions)
    operation_id = uuid.uuid5(NAMESPACE, identity["id"] + ":" + digest)
    if write:
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (731064924,))
    if conn.execute("SELECT 1 FROM catalog_imports WHERE operation_id=%s", (operation_id,)).fetchone():
        return {"status": "already_committed", "manifest_hash": digest}
    lock = " FOR UPDATE" if write else ""
    artists = {r["id"]: r for r in rows(conn, "SELECT id, version, archived_at FROM artists WHERE id=ANY(%s)" + lock,
                                        ([i["artist_id"] for i in accepted],))}
    existing = {r["platform_id"]: r for r in rows(conn, """SELECT id, platform_id, archived_at FROM external_accounts
        WHERE platform='spotify' AND platform_id=ANY(%s)""" + lock, ([i["spotify_id"] for i in accepted],))}
    plan = []
    for i in accepted:
        a = artists.get(i["artist_id"])
        if a is None or a["archived_at"] or a["version"] != i["version"]:
            raise RuntimeError(f"Artist {i['artist_id']} changed since export; re-export")
        links = rows(conn, """SELECT e.platform, e.platform_id, e.archived_at, ae.position FROM artist_external_accounts ae
            JOIN external_accounts e ON e.id=ae.account_id WHERE ae.artist_id=%s""" + lock, (i["artist_id"],)).fetchall()
        if any(l["platform"] == "spotify" and l["archived_at"] is None for l in links):
            raise RuntimeError(f"Artist {i['artist_id']} already has a Spotify link; re-export")
        acct = existing.get(i["spotify_id"])
        if acct and acct["archived_at"]:
            raise RuntimeError(f"Spotify account {i['spotify_id']} is archived; decide manually")
        plan.append({**i, "account_id": acct["id"] if acct else None,
                     "position": max([l["position"] for l in links], default=-1) + 1})
    summary = {"accept": len(accepted), "review": sum(i["decision"] == "review" for i in decisions["items"]),
               "skip": sum(i["decision"] == "skip" for i in decisions["items"]),
               "accounts_created": sum(p["account_id"] is None for p in plan),
               "existing_accounts_linked": sum(p["account_id"] is not None for p in plan)}
    if not write:
        return {"status": "would_commit", "manifest_hash": digest, **summary}
    changes, mapping = [], []
    for p in plan:
        if p["account_id"] is None:
            account = conn.execute("""INSERT INTO external_accounts(platform, platform_id, url, collection_enabled)
                VALUES ('spotify', %s, %s, false) RETURNING id, to_jsonb(external_accounts)""",
                (p["spotify_id"], f"https://open.spotify.com/artist/{p['spotify_id']}")).fetchone()
            p["account_id"] = account[0]
            changes.append(("external_accounts", account[0], "create", None, account[1],
                            {"policy": POLICY, "spotify_name": p["spotify_name"]}))
            mapping.append({"entity_type": "external_accounts", "id": account[0]})
        link = conn.execute("""INSERT INTO artist_external_accounts(artist_id, account_id, relationship, is_primary, position)
            VALUES (%s, %s, %s, true, %s) RETURNING id, to_jsonb(artist_external_accounts)""",
            (p["artist_id"], p["account_id"], p["relationship"], p["position"])).fetchone()
        changes.append(("artist_external_accounts", link[0], "create", None, link[1],
                        {"policy": POLICY, "basis": p["basis"], "evidence": p["evidence"], "reviewed": True}))
        mapping.append({"entity_type": "artist_external_accounts", "id": link[0]})
    import_id = conn.execute("""INSERT INTO catalog_imports(operation_id, catalog_instance_id, manifest_hash, source_kind,
            result_mapping, result_summary) VALUES (%s, %s, %s, 'manual', %s, %s) RETURNING id""",
        (operation_id, identity["id"], digest, Jsonb(mapping), Jsonb({"kind": POLICY, **summary}))).fetchone()[0]
    for entity_type, entity_id, action, before, after, provenance in changes:
        conn.execute("""INSERT INTO catalog_changes(import_id, entity_type, entity_id, action, before_data, after_data, provenance)
            VALUES (%s, %s, %s, %s, %s, %s, %s)""", (import_id, entity_type, entity_id, action,
                                                     None if before is None else Jsonb(before), Jsonb(after), Jsonb(provenance)))
    return {"status": "committed", "manifest_hash": digest, "import_id": import_id, **summary}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("research", help="Query Wikidata/Spotify for candidates (read-only DB access)")
    sub.add_parser("export", help="Write the decision file and review.md (no DB access)")
    sub.add_parser("review-import", help="Record the user's edits of review.md and the approval")
    run = sub.add_parser("apply", help="Dry-run the decision file; --apply writes the accepted accounts")
    run.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    manual = json.loads(MANUAL.read_text(encoding="utf-8")) if MANUAL.exists() else {}
    if args.command == "export":
        research_rows = json.loads((REPORT_DIR / "candidates.json").read_text(encoding="utf-8"))
        web = [x for p in sorted(REPORT_DIR.glob("research-*.json")) for x in json.loads(p.read_text(encoding="utf-8-sig"))]
        meta = json.loads((REPORT_DIR / "meta.json").read_text(encoding="utf-8"))
        decisions = {**export(research_rows, web, manual), "catalog_instance_id": meta["catalog_instance_id"],
                     "exported_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")}
        DECISIONS.write_text(json.dumps(decisions, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        (REPORT_DIR / "review.md").write_text(render_review(decisions), encoding="utf-8")
        print(json.dumps({"file": str(DECISIONS.relative_to(ROOT)), **decisions["summary"]}, ensure_ascii=False))
        return 0
    if args.command == "review-import":
        edited = REPORT_DIR / "review.md"
        (REPORT_DIR / "review.user-edited.md").write_text(edited.read_text(encoding="utf-8-sig"), encoding="utf-8")
        decisions = json.loads(DECISIONS.read_text(encoding="utf-8"))
        ids = read_review(edited)
        edits = review_edits(decisions, ids)
        accounts = {m["artist_id"]: m for m in manual.get("accounts", [])}
        for e in edits:
            accounts[e["artist_id"]] = {"artist_id": e["artist_id"], "spotify_id": e["spotify_id"],
                                        "spotify_name": None, "basis": "user_review",
                                        "decision": "accept" if e["spotify_id"] else "skip"}
        manual["accounts"] = sorted(accounts.values(), key=lambda m: m["artist_id"])
        manual["user_review"] = {"date": datetime.now(UTC).strftime("%Y-%m-%d"), "approved": "all",
                                 "listed": sorted(ids), "note": "The user edited review.md and approved every listed row."}
        MANUAL.write_text(json.dumps(manual, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"edits": edits}, ensure_ascii=False, indent=2))
        return 0
    writing = args.command == "apply" and args.apply
    with psycopg.connect(migrate_catalog.load_connection(), connect_timeout=20) as conn:
        migrate_catalog.configure_transaction(conn, read_only=not writing)
        if args.command == "research":
            artists = load_artists(conn)
            catalog_id = rows(conn, "SELECT id::text AS id FROM catalog_instance").fetchone()["id"]
            conn.rollback()
            cache = Cache(REPORT_DIR / "cache" / "responses.json")
            out = research(artists, cache)
            (REPORT_DIR / "candidates.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            (REPORT_DIR / "meta.json").write_text(json.dumps({"catalog_instance_id": catalog_id}) + "\n", encoding="utf-8")
            print(json.dumps({"artists": len(out), "with_candidates": sum(bool(r["candidates"]) for r in out),
                              "requests": cache.requests}, ensure_ascii=False))
            return 0
        result = apply(conn, json.loads(DECISIONS.read_text(encoding="utf-8")), write=writing)
        if writing:
            conn.commit()
        else:
            conn.rollback()
            result["mode"] = "dry-run"
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
