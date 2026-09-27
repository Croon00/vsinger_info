"""Song-master pilot: propose external works for top pending match keys (plan step 5).

READ ONLY on the catalog. For existing songs (``--songs``) and the most frequent pending
``song_match_keys`` (``--keys N``) it queries VocaDB -> UtaiteDB -> MusicBrainz by exact
title, keeps candidates whose name and credited artist match, and classifies each target:

  auto       exactly one candidate matches title AND artist
  review     title matches but the artist does not, or several strong candidates
  none       no candidate with the same title
  no_artist  the setlist text has no original artist; not looked up
  error      a provider failed and nothing was found

Existing songs run first, so a key whose candidate is already an existing song is shown
as a link to that song rather than a new one. Provider responses are cached in the output
directory; a rerun reuses them. The report and cache stay in git-ignored
db-migration/reports/song-master-candidates. Nothing is written to the database.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.song_keys import normalize_text  # noqa: E402
from app.integrations.song_catalogs import MusicBrainzClient, VocaDbClient  # noqa: E402
from app.services.song_candidates import ArtistIndex, Target, existing_matches, lookup  # noqa: E402

REPORT_DIR = ROOT / "db-migration" / "reports" / "song-master-candidates"
KEY_VERSION = 1

_spec = importlib.util.spec_from_file_location("migrate_catalog", ROOT / "scripts" / "migrate_catalog.py")
migrate_catalog = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migrate_catalog)


def load(conn, *, keys: int, songs: bool) -> dict:
    q = lambda sql, params=None: conn.cursor(row_factory=dict_row).execute(sql, params).fetchall()  # noqa: E731
    # A spelling that is some artist's native name or alias resolves to that artist only;
    # romanized/Korean names are a fallback. Otherwise "HACHI" (VTuber) also hits
    # ハチ (name_latin "Hachi"), a different artist.
    primary, fallback, spellings = defaultdict(set), defaultdict(set), defaultdict(set)
    for r in q("""SELECT a.id, v.value, v.tier FROM artists a
                  CROSS JOIN LATERAL (VALUES (a.name_native, 1),(a.name_latin, 2),(a.name_ko, 2)) v(value, tier)
                  WHERE a.archived_at IS NULL AND v.value IS NOT NULL
                  UNION ALL SELECT aa.artist_id, aa.alias, 1 FROM artist_aliases aa
                  JOIN artists a ON a.id=aa.artist_id AND a.archived_at IS NULL"""):
        key = normalize_text(r["value"])
        if key:
            (primary if r["tier"] == 1 else fallback)[key].add(r["id"])
            spellings[r["id"]].add(key)
    by_spelling = {key: primary.get(key) or fallback[key] for key in primary.keys() | fallback.keys()}
    index = ArtistIndex(by_spelling, dict(spellings))
    names = {r["id"]: r["name_native"] for r in q("SELECT id, name_native FROM artists")}
    song_rows = q("""SELECT s.id, s.title_native,
                       coalesce(array_agg(sa.artist_id ORDER BY sa.position, sa.id) FILTER (WHERE sa.id IS NOT NULL), '{}') AS artist_ids,
                       (SELECT count(*) FROM performances p WHERE p.song_id=s.id AND p.archived_at IS NULL) AS n
                     FROM songs s LEFT JOIN song_artists sa ON sa.song_id=s.id
                     WHERE s.archived_at IS NULL
                       AND NOT EXISTS (SELECT 1 FROM song_merges m WHERE m.source_song_id=s.id)
                     GROUP BY s.id ORDER BY n DESC, s.id""")
    existing = []
    for r in song_rows:
        found = set().union(*(spellings.get(a, set()) for a in r["artist_ids"])) if r["artist_ids"] else set()
        existing.append({"id": r["id"], "title": r["title_native"], "title_key": normalize_text(r["title_native"]),
                         "artist_ids": list(r["artist_ids"]), "artist_spellings": found, "count": r["n"],
                         "artist": names.get(r["artist_ids"][0]) if r["artist_ids"] else None})
    key_rows = q("""SELECT id, title_key, artist_key, sample_raw_title, sample_raw_artist, occurrence_count
                    FROM song_match_keys WHERE status='pending' AND key_version=%s
                    ORDER BY occurrence_count DESC, id LIMIT %s""", (KEY_VERSION, keys)) if keys else []
    targets = []
    if songs:
        targets += [Target("song", s["id"], s["title"], s["artist"], s["title_key"], s["artist_spellings"],
                           s["count"], s["artist_ids"]) for s in existing]
    for r in key_rows:
        found, ids = index.expand(r["artist_key"])
        targets.append(Target("key", r["id"], r["sample_raw_title"], r["sample_raw_artist"], r["title_key"],
                              found, r["occurrence_count"], ids))
    external = {(r["provider"], r["external_id"]): r["song_id"]
                for r in q("SELECT provider, external_id, song_id FROM song_external_ids")}
    return {"targets": targets, "songs": existing, "external": external}


def trim(candidates: list[dict], limit: int = 8) -> list[dict]:
    ranked = sorted(candidates, key=lambda c: (not (c["title_exact"] and c["artist_exact"]), not c["title_exact"]))
    return ranked[:limit]


def save_cache(path: Path, cache: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def run(data: dict, clients: dict, *, progress=None) -> dict:
    external = dict(data["external"])
    items = []
    for n, target in enumerate(data["targets"], 1):
        result = lookup(target, **clients)
        strong = [c for c in result["candidates"] if c["title_exact"] and c["artist_exact"]]
        for c in strong:
            c["existing_song_ids"] = existing_matches(c, data["songs"], external,
                                                      target_spellings=target.artist_spellings)
        if target.kind == "song" and result["status"] == "auto":
            # Later keys should resolve to this song, not to a new one.
            external.setdefault((strong[0]["provider"], strong[0]["external_id"]), target.ref)
        items.append({"kind": target.kind, "ref": target.ref, "title": target.title, "artist": target.artist,
                      "title_key": target.title_key, "count": target.count, "our_artist_ids": target.our_artist_ids,
                      "status": result["status"], "providers": result["providers"], "errors": result["errors"],
                      "candidates": trim(result["candidates"])})
        if progress:
            progress(n, len(data["targets"]))
    return {"items": items, "summary": summarize(items)}


def summarize(items: list[dict]) -> dict:
    summary = {}
    for kind in ("song", "key"):
        rows = [i for i in items if i["kind"] == kind]
        if not rows:
            continue
        status, weight, provider, target_kind = Counter(), Counter(), Counter(), Counter()
        for item in rows:
            status[item["status"]] += 1
            weight[item["status"]] += item["count"]
            if item["status"] == "auto":
                best = next(c for c in item["candidates"] if c["title_exact"] and c["artist_exact"])
                provider[best["provider"]] += 1
                ids = best.get("existing_song_ids") or []
                target_kind["same_song" if kind == "song" and ids == [item["ref"]] else
                            "existing_song" if ids else "new_song"] += 1
        summary[kind] = {"targets": len(rows), "status": dict(status), "performances": dict(weight),
                         "auto_by_provider": dict(provider), "auto_target": dict(target_kind),
                         "errors": sum(1 for i in rows if i["errors"])}
    shared = defaultdict(set)
    for item in items:
        if item["kind"] == "song" and item["status"] == "auto":
            best = next(c for c in item["candidates"] if c["title_exact"] and c["artist_exact"])
            shared[(best["provider"], best["external_id"])].add(item["ref"])
    summary["existing_songs_sharing_a_work"] = [
        {"provider": p, "external_id": e, "song_ids": sorted(ids)} for (p, e), ids in sorted(shared.items()) if len(ids) > 1]
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--keys", type=int, default=300, help="Most frequent pending keys to look up (default 300)")
    parser.add_argument("--songs", action="store_true", help="Also look up every existing song first")
    parser.add_argument("--no-musicbrainz", action="store_true", help="Skip the MusicBrainz fallback")
    parser.add_argument("--output-dir", type=Path, default=REPORT_DIR)
    args = parser.parse_args()
    if not 0 <= args.keys <= 5000:
        parser.error("--keys must be between 0 and 5000")
    try:
        uri = migrate_catalog.load_connection()
    except migrate_catalog.MigrationError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    with psycopg.connect(uri, connect_timeout=20, row_factory=dict_row) as conn:
        migrate_catalog.configure_transaction(conn, read_only=True)
        data = load(conn, keys=args.keys, songs=args.songs)
        conn.rollback()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    cache_path = args.output_dir / "provider-cache.json"
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    # VocaDB/UtaiteDB publish no hard limit; two requests a second stays polite.
    clients = {"vocadb": VocaDbClient("vocadb", cache=cache, interval=0.5),
               "utaitedb": VocaDbClient("utaitedb", cache=cache, interval=0.5),
               "musicbrainz": None if args.no_musicbrainz else MusicBrainzClient(cache=cache)}
    started = time.monotonic()

    def progress(n, total):
        if n % 20 == 0 or n == total:
            save_cache(cache_path, cache)
            print(f"{n}/{total} targets, {time.monotonic() - started:.0f}s", file=sys.stderr, flush=True)

    try:
        report = run(data, clients, progress=progress)
    finally:
        save_cache(cache_path, cache)
        for client in clients.values():
            if client:
                client.close()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    report_path = args.output_dir / f"candidates-{stamp}.json"
    report["generated_at"] = stamp
    report["requests"] = {name: c.http.requests for name, c in clients.items() if c}
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=1, default=list), encoding="utf-8")
    print(json.dumps({"report": str(report_path.relative_to(ROOT)), "requests": report["requests"],
                      **report["summary"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
