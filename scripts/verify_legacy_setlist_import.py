"""Read-only production checks for the 2026-09-21 legacy setlist import."""
from __future__ import annotations

import json

import psycopg

from import_legacy_setlists import connection_url


def main() -> None:
    with psycopg.connect(connection_url(), connect_timeout=10) as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        tables = ("videos", "live_archives", "archive_artists", "performances",
                  "source_documents", "archive_sources", "performance_artists")
        counts = {table: conn.execute("SELECT count(*) FROM " + table).fetchone()[0]
                  for table in tables}
        source_accounts = conn.execute("""SELECT count(*) FILTER (WHERE source_account_id IS NOT NULL),
            count(*) FILTER (WHERE source_account_id IS NULL) FROM videos""").fetchone()
        invalid = conn.execute("""SELECT
          (SELECT count(*) FROM live_archives l WHERE NOT EXISTS
            (SELECT 1 FROM archive_artists a WHERE a.archive_id=l.id AND a.artist_id=l.primary_artist_id)),
          (SELECT count(*) FROM performances p JOIN live_archives l ON l.id=p.archive_id
            JOIN videos v ON v.id=l.video_id WHERE p.start_seconds > v.duration_seconds),
          (SELECT count(*) FROM (SELECT platform_video_id FROM videos WHERE platform='youtube'
            GROUP BY platform_video_id HAVING count(*) > 1) x),
          (SELECT count(*) FROM performances p WHERE p.source_document_id IS NOT NULL
            AND NOT EXISTS (SELECT 1 FROM archive_sources s WHERE s.document_id=p.source_document_id
              AND s.archive_id=p.archive_id))""").fetchone()
        excluded = dict(conn.execute("""SELECT platform_video_id,count(*) FROM videos
            WHERE platform_video_id IN ('tR4jmnavtDk','cyRZGtNx_a4')
            GROUP BY platform_video_id""").fetchall())
        reviewed = {}
        for video_key in ("xF44iE-Sok0", "FHoFxjx8QGU"):
            rows = conn.execute("""SELECT a.slug,p.ordinal,p.start_seconds,p.raw_title,p.raw_artist,
                d.source_kind FROM videos v JOIN live_archives l ON l.video_id=v.id
                JOIN artists a ON a.id=l.primary_artist_id
                JOIN performances p ON p.archive_id=l.id
                LEFT JOIN source_documents d ON d.id=p.source_document_id
                WHERE v.platform='youtube' AND v.platform_video_id=%s ORDER BY p.ordinal""",
                (video_key,)).fetchall()
            reviewed[video_key] = rows
        group_corrections = conn.execute("""SELECT result_summary->>'group_host_corrections'
            FROM catalog_imports WHERE source_kind='correction'
              AND result_summary ? 'group_host_corrections'""").fetchall()
        provisional = conn.execute("""SELECT
            (SELECT count(*) FROM performances p WHERE p.archived_at IS NULL AND NOT EXISTS
              (SELECT 1 FROM performance_artists pa WHERE pa.performance_id=p.id)),
            (SELECT count(*) FROM performance_artists pa JOIN performances p ON p.id=pa.performance_id
              JOIN live_archives l ON l.id=p.archive_id
              WHERE pa.artist_id<>l.primary_artist_id OR pa.role<>'lead'),
            (SELECT count(*) FROM catalog_imports WHERE result_summary->>'kind'='provisional-host-singer-v1'),
            (SELECT count(*) FROM catalog_changes WHERE entity_type='performance_artists'
              AND provenance->>'review_status'='provisional')""").fetchone()
        sample_statistic = conn.execute("""SELECT count(*) FROM performances p
            JOIN performance_artists pa ON pa.performance_id=p.id
            WHERE pa.artist_id=(SELECT id FROM artists WHERE slug='kmnz-tina')""").fetchone()[0]
        result = {"counts": counts, "source_account_counts": source_accounts,
                  "invalid_graph_duration_duplicate_and_source_counts": invalid,
                  "excluded_present": excluded, "reviewed": reviewed,
                  "group_correction_receipts": group_corrections,
                  "provisional_singer_check": provisional,
                  "kmnz_tina_statistic_entries": sample_statistic}
        if counts["videos"] != 5783 or counts["live_archives"] != 5783 or counts["performances"] != 73841:
            raise ValueError("Unexpected imported row totals: " + json.dumps(result, ensure_ascii=False))
        if any(invalid) or excluded or len(reviewed["xF44iE-Sok0"]) != 10:
            raise ValueError("Import validation failed: " + json.dumps(result, ensure_ascii=False))
        fho = reviewed["FHoFxjx8QGU"]
        if (len(fho) != 8 or [r[2] for r in fho] != [738, 1014, 2188, 2455, 2793, 3091, 3961, 4232]
                or any(r[0] != "kmnz-tina" or r[5] != "manual_note" for r in fho)):
            raise ValueError("Curated FHo setlist differs: " + json.dumps(fho, ensure_ascii=False))
        if group_corrections != [("203",)]:
            raise ValueError("Group host corrections missing")
        if (counts["performance_artists"] != counts["performances"] or
                provisional != (0, 0, 37, 73841) or sample_statistic == 0):
            raise ValueError("Provisional singer backfill differs: " + json.dumps(result, ensure_ascii=True))
        result["reviewed"] = {key: {"count": len(rows), "starts": [row[2] for row in rows]}
                              for key, rows in reviewed.items()}
        print(json.dumps(result, ensure_ascii=True, default=str))


if __name__ == "__main__":
    main()
