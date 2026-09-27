"""Read-only audit of the Spotify collection started by start_spotify_collection.py.

Reports job outcomes, what each account brought in, the receipt actions that need a
person (conflicts, ISRC conflicts), recordings without ISRC or credits, and — as a
wrong-account signal — accounts whose collected titles match none of the artist's own
YouTube video titles or credited songs. Writes nothing; the detail goes to the
git-ignored db-migration/reports/spotify-collection/audit.json.
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from collections import Counter
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.core.song_keys import normalize_text  # noqa: E402

REPORT = ROOT / "db-migration" / "reports" / "spotify-collection" / "audit.json"
REVIEW_ACTIONS = {"version_conflict", "recording_version_conflict", "slot_conflict", "isrc_conflict",
                  "existing_video_conflict", "review_candidate"}

_spec = importlib.util.spec_from_file_location("migrate_catalog", ROOT / "scripts" / "migrate_catalog.py")
migrate_catalog = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migrate_catalog)


def squash(value: str | None) -> str:
    return re.sub(r"[\s・･·]", "", normalize_text(value))


def core(title: str) -> str:
    return squash(re.sub(r"\s*[\(（\[【].*?[\)）\]】]\s*|\s+-\s+.*$", "", title))


def main() -> int:
    with psycopg.connect(migrate_catalog.load_connection(), connect_timeout=20, row_factory=dict_row) as conn:
        migrate_catalog.configure_transaction(conn, read_only=True)
        jobs = conn.execute("""SELECT j.id, j.external_account_id, j.status, j.attempt_count, j.last_error,
                (j.payload->>'album_offset')::int AS album_offset
            FROM worker_jobs j WHERE j.job_type='spotify_collect' ORDER BY j.id""").fetchall()
        accounts = conn.execute("""SELECT e.id, e.platform_id, a.id AS artist_id, a.name_native
            FROM external_accounts e JOIN artist_external_accounts ae ON ae.account_id=e.id AND ae.relationship='owner'
            JOIN artists a ON a.id=ae.artist_id
            WHERE e.platform='spotify' AND e.collection_enabled AND e.archived_at IS NULL ORDER BY e.id""").fetchall()
        receipts = conn.execute("""SELECT result_summary FROM catalog_imports
            WHERE source_kind='batch_import' AND result_summary->>'provider'='spotify'""").fetchall()
        per_artist = {r["artist_id"]: r for r in conn.execute("""SELECT ra.artist_id, count(DISTINCT ra.recording_id) AS recordings,
                array_agg(DISTINCT r.title_native) AS titles
            FROM recording_artists ra JOIN recordings r ON r.id=ra.recording_id GROUP BY ra.artist_id""")}
        albums_per_artist = {r["artist_id"]: r["n"] for r in conn.execute(
            "SELECT artist_id, count(*) AS n FROM album_artists GROUP BY 1")}
        videos, songs = {}, {}
        for r in conn.execute("""SELECT ae.artist_id, v.title FROM artist_external_accounts ae
                JOIN external_accounts e ON e.id=ae.account_id AND e.platform='youtube' AND ae.relationship='owner'
                JOIN videos v ON v.source_account_id=e.id WHERE v.title IS NOT NULL"""):
            videos.setdefault(r["artist_id"], []).append(squash(r["title"]))
        for r in conn.execute("SELECT sa.artist_id, s.title_native FROM song_artists sa JOIN songs s ON s.id=sa.song_id"):
            songs.setdefault(r["artist_id"], set()).add(squash(r["title_native"]))
        totals = conn.execute("""SELECT (SELECT count(*) FROM albums) AS albums, (SELECT count(*) FROM recordings) AS recordings,
            (SELECT count(*) FROM recording_external_ids WHERE platform='isrc') AS isrc,
            (SELECT count(*) FROM recording_external_ids WHERE platform='spotify') AS spotify_tracks,
            (SELECT count(*) FROM recordings r WHERE NOT EXISTS (SELECT 1 FROM recording_external_ids x
                 WHERE x.recording_id=r.id AND x.platform='isrc')) AS without_isrc,
            (SELECT count(*) FROM recordings r WHERE NOT EXISTS (SELECT 1 FROM recording_artists x
                 WHERE x.recording_id=r.id)) AS without_credit,
            (SELECT count(*) FROM albums a WHERE NOT EXISTS (SELECT 1 FROM album_artists x WHERE x.album_id=a.id)) AS albums_without_credit,
            (SELECT count(*) FROM recordings WHERE song_id IS NOT NULL) AS with_song""").fetchone()
        joined = conn.execute("""SELECT count(*) AS n FROM (SELECT recording_id FROM recording_external_ids
            WHERE platform='spotify' GROUP BY 1 HAVING count(*) > 1) x""").fetchone()["n"]
    actions = Counter()
    review = []
    for r in receipts:
        for a in r["result_summary"].get("actions", []):
            actions[a["status"]] += 1
            if a["status"] in REVIEW_ACTIONS:
                review.append(a)
    by_account = {a["id"]: a for a in accounts}
    states = Counter(j["status"] for j in jobs)
    failed = [dict(j, artist=by_account.get(j["external_account_id"], {}).get("name_native")) for j in jobs
              if j["status"] in ("failed", "cancelled")]
    rows = []
    for a in accounts:
        mine = per_artist.get(a["artist_id"])
        titles = mine["titles"] if mine else []
        own = [t for t in titles if len(core(t)) >= 2 and (core(t) in songs.get(a["artist_id"], set())
                                                            or any(core(t) in v for v in videos.get(a["artist_id"], [])))]
        rows.append({"artist_id": a["artist_id"], "artist": a["name_native"], "spotify_id": a["platform_id"],
                     "albums": albums_per_artist.get(a["artist_id"], 0), "recordings": mine["recordings"] if mine else 0,
                     "own_title_matches": len(own), "sample_matches": own[:3],
                     "has_video_titles": bool(videos.get(a["artist_id"])), "sample_titles": titles[:5]})
    unmatched = [r for r in rows if r["recordings"] and not r["own_title_matches"] and r["has_video_titles"]]
    empty = [r for r in rows if not r["recordings"]]
    result = {"jobs": dict(states), "finished": not (states["pending"] or states["running"] or states["retry"]),
              "failed_jobs": failed, "totals": dict(totals), "recordings_joined_by_isrc": joined,
              "actions": dict(actions), "review_actions": len(review),
              "accounts_without_recordings": [r["artist"] for r in empty],
              "accounts_with_no_own_title_match": [{k: r[k] for k in ("artist", "spotify_id", "recordings", "sample_titles")}
                                                   for r in unmatched]}
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps({**result, "accounts": rows, "review": review}, ensure_ascii=False, indent=1, default=str) + "\n",
                      encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
