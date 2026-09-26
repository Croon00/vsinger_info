"""Read-only song-master readiness audit on the unified catalog DB (song-master plan step 1).

Opens one READ ONLY transaction, never writes to the database, and stores the full
report under the git-ignored db-migration/reports/song-master-audit directory.
Only aggregate counts are printed; raw setlist text stays in the report file.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.core.song_keys import normalize_text, song_key  # noqa: E402

REPORT_DIR = ROOT / "db-migration" / "reports" / "song-master-audit"
COVERAGE_TOPS = (50, 100, 300, 500, 1000, 2000)

_spec = importlib.util.spec_from_file_location("migrate_catalog", ROOT / "scripts" / "migrate_catalog.py")
migrate_catalog = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migrate_catalog)


def one(conn, query: str) -> dict:
    return dict(conn.execute(query).fetchone())


def artist_accounts(conn) -> dict:
    rows = conn.execute("""
        WITH singers AS (
          SELECT DISTINCT aa.artist_id FROM archive_artists aa
          JOIN live_archives la ON la.id=aa.archive_id AND la.archived_at IS NULL
        ), accounts AS (
          SELECT ae.artist_id, e.platform, bool_or(e.collection_enabled) AS enabled
          FROM artist_external_accounts ae JOIN external_accounts e ON e.id=ae.account_id
          WHERE ae.relationship='owner' AND e.archived_at IS NULL AND e.platform IN ('youtube','spotify')
          GROUP BY ae.artist_id, e.platform
        )
        SELECT a.id, a.show_in_catalog, a.name_ko IS NOT NULL AS has_ko, a.name_latin IS NOT NULL AS has_latin,
               a.id IN (SELECT artist_id FROM singers) AS is_singer,
               EXISTS (SELECT 1 FROM accounts x WHERE x.artist_id=a.id AND x.platform='spotify') AS spotify,
               EXISTS (SELECT 1 FROM accounts x WHERE x.artist_id=a.id AND x.platform='spotify' AND x.enabled) AS spotify_enabled,
               EXISTS (SELECT 1 FROM accounts x WHERE x.artist_id=a.id AND x.platform='youtube') AS youtube,
               EXISTS (SELECT 1 FROM song_artists sa WHERE sa.artist_id=a.id) AS original_artist
        FROM artists a WHERE a.archived_at IS NULL
    """).fetchall()

    def summary(subset: list[dict]) -> dict:
        return {"total": len(subset), **{key: sum(r[key] for r in subset) for key in
                ("spotify", "spotify_enabled", "youtube", "has_ko", "has_latin")}}

    return {
        "all": summary(rows),
        "archive_hosts": summary([r for r in rows if r["is_singer"]]),
        "shown_in_catalog": summary([r for r in rows if r["show_in_catalog"]]),
        "linked_as_original_artist": summary([r for r in rows if r["original_artist"]]),
    }


def performance_keys(conn) -> dict:
    groups = conn.execute("""
        SELECT p.raw_title, p.raw_artist, count(*) AS n, count(p.song_id) AS linked,
               count(DISTINCT p.archive_id) AS archives
        FROM performances p JOIN live_archives la ON la.id=p.archive_id AND la.archived_at IS NULL
        WHERE p.archived_at IS NULL GROUP BY p.raw_title, p.raw_artist
    """).fetchall()
    keys: dict[tuple[str, str], dict] = defaultdict(lambda: {"n": 0, "linked": 0, "spellings": 0, "sample": None})
    titles: Counter = Counter()
    for g in groups:
        key = song_key(g["raw_title"], g["raw_artist"])
        entry = keys[key]
        entry["n"] += g["n"]
        entry["linked"] += g["linked"]
        entry["spellings"] += 1
        if entry["sample"] is None or g["n"] > entry["sample"][2]:
            entry["sample"] = (g["raw_title"], g["raw_artist"], g["n"])
        titles[key[0]] += g["n"]
    total = sum(g["n"] for g in groups)
    ranked = sorted(keys.items(), key=lambda item: -item[1]["n"])
    counts = [entry["n"] for _, entry in ranked]
    coverage = {str(top): round(sum(counts[:top]) / total, 4) if total else 0 for top in COVERAGE_TOPS}
    no_artist = sum(entry["n"] for (title, artist), entry in ranked if not artist)
    # Remaining work: performances still without song_id, ranked by their own key frequency.
    open_counts = sorted((e["n"] - e["linked"] for _, e in ranked if e["n"] > e["linked"]), reverse=True)
    open_total = sum(open_counts)
    open_coverage = {str(top): round(sum(open_counts[:top]) / open_total, 4) if open_total else 0
                     for top in COVERAGE_TOPS}
    return {
        "summary": {
            "performances": total,
            "linked_song_id": sum(g["linked"] for g in groups),
            "raw_pairs": len(groups),
            "normalized_keys": len(keys),
            "normalized_titles_only": len(titles),
            "keys_seen_once": sum(1 for c in counts if c == 1),
            "performances_without_raw_artist": no_artist,
            "top_key_coverage": coverage,
            "unlinked_performances": open_total,
            "keys_with_unlinked": len(open_counts),
            "partially_linked_keys": sum(1 for _, e in ranked if 0 < e["linked"] < e["n"]),
            "top_unlinked_key_coverage": open_coverage,
        },
        "top_keys": [
            {"title_key": k[0], "artist_key": k[1], "performances": e["n"], "linked": e["linked"],
             "spellings": e["spellings"], "sample_raw_title": e["sample"][0], "sample_raw_artist": e["sample"][1]}
            for k, e in ranked[:500]
        ],
    }


def songs(conn) -> dict:
    summary = one(conn, """
        SELECT count(*) AS total,
               count(title_ko) AS title_ko, count(title_latin) AS title_latin, count(language_code) AS language_code,
               count(*) FILTER (WHERE EXISTS (SELECT 1 FROM song_artists x WHERE x.song_id=s.id)) AS with_artists,
               count(*) FILTER (WHERE EXISTS (SELECT 1 FROM recordings x WHERE x.song_id=s.id)) AS with_recordings,
               count(*) FILTER (WHERE EXISTS (SELECT 1 FROM performances x WHERE x.song_id=s.id)) AS with_performances,
               count(*) FILTER (WHERE EXISTS (SELECT 1 FROM karaoke_numbers x WHERE x.song_id=s.id)) AS with_karaoke
        FROM songs s WHERE archived_at IS NULL
    """)
    origin = {r["source_kind"] or "unrecorded": r["n"] for r in conn.execute("""
        SELECT i.source_kind, count(DISTINCT s.id) AS n FROM songs s
        LEFT JOIN catalog_changes c ON c.entity_type='songs' AND c.entity_id=s.id AND c.action='create'
        LEFT JOIN catalog_imports i ON i.id=c.import_id
        WHERE s.archived_at IS NULL GROUP BY i.source_kind
    """)}
    rows = conn.execute("""
        SELECT s.id, s.title_native,
               COALESCE(array_agg(sa.artist_id ORDER BY sa.artist_id) FILTER (WHERE sa.artist_id IS NOT NULL), '{}') AS artists
        FROM songs s LEFT JOIN song_artists sa ON sa.song_id=s.id
        WHERE s.archived_at IS NULL GROUP BY s.id
    """).fetchall()
    by_title: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_title[normalize_text(r["title_native"])].append(r)
    same_title = {t: g for t, g in by_title.items() if len(g) > 1}
    same_title_artists = [g for g in same_title.values()
                          if len({tuple(r["artists"]) for r in g}) < len(g)]
    return {
        "summary": {**summary, "origin_by_import_kind": origin,
                    "same_title_groups": len(same_title),
                    "same_title_and_artists_groups": len(same_title_artists)},
        "same_title_samples": [
            {"title": t, "songs": [{"id": r["id"], "artists": list(r["artists"])} for r in g]}
            for t, g in list(same_title.items())[:100]
        ],
    }


def recordings(conn) -> dict:
    return one(conn, """
        SELECT count(*) AS total, count(song_id) AS with_song_id,
               count(*) FILTER (WHERE EXISTS (SELECT 1 FROM recording_external_ids x
                                              WHERE x.recording_id=r.id AND x.platform='spotify')) AS with_spotify_id
        FROM recordings r WHERE archived_at IS NULL
    """)


def audit(conn) -> dict:
    migrate_catalog.configure_transaction(conn, read_only=True)
    keys = performance_keys(conn)
    song_report = songs(conn)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "revisions": [r["version"] for r in conn.execute(
            "SELECT version FROM catalog_schema_migrations ORDER BY version")],
        "artists": artist_accounts(conn),
        "performances": keys["summary"],
        "songs": song_report["summary"],
        "recordings": recordings(conn),
        "top_keys": keys["top_keys"],
        "same_title_samples": song_report["same_title_samples"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=REPORT_DIR)
    args = parser.parse_args()
    try:
        uri = migrate_catalog.load_connection()
    except migrate_catalog.MigrationError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    with psycopg.connect(uri, connect_timeout=20, row_factory=dict_row) as conn:
        report = audit(conn)
        conn.rollback()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    path = args.output_dir / f"audit-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    summary = {k: report[k] for k in ("revisions", "artists", "performances", "songs", "recordings")}
    print(json.dumps({"report": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
                      **summary}, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
