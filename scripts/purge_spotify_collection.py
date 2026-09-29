"""Delete the Spotify collection made with market=KR so it can be re-collected in JP.

Scope: every album with a ``spotify_album_id`` and every recording that has a Spotify track
ID, together with their tracks, credits, provider credits and external IDs (cascade). The preview (default)
only reads. ``--apply`` refuses if anything in scope carries work a person or a later step
added — a song link, a Korean title, an official video, lyrics, or a catalog_changes
history row — or if a recording in scope sits on a non-Spotify album. It deletes in ONE
transaction and keeps the evidence: a catalog_imports receipt plus one catalog_changes
``delete`` row per album and recording with its full previous row. The collection
receipts (catalog_imports) and worker_jobs history are append-only and stay.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
import uuid
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[1]
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

POLICY = "spotify-collection-purge-v1"
NAMESPACE = uuid.UUID("6f2c1a8e-93d4-4b7a-a5e0-2d8c47b19f63")

_spec = importlib.util.spec_from_file_location("migrate_catalog", ROOT / "scripts" / "migrate_catalog.py")
migrate_catalog = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migrate_catalog)



def run(conn, *, write: bool) -> dict:
    identity = conn.execute("SELECT id::text AS id FROM catalog_instance").fetchone()["id"]
    if write:
        conn.execute("SELECT pg_advisory_xact_lock(731064926)")
        conn.execute("LOCK TABLE albums, recordings, album_tracks IN SHARE ROW EXCLUSIVE MODE")
    counts = conn.execute("""SELECT
        (SELECT count(*) FROM albums WHERE spotify_album_id IS NOT NULL) AS albums,
        (SELECT count(DISTINCT recording_id) FROM recording_external_ids WHERE platform='spotify') AS recordings,
        (SELECT count(*) FROM album_tracks WHERE album_id IN (SELECT id FROM albums WHERE spotify_album_id IS NOT NULL)) AS album_tracks,
        (SELECT count(*) FROM album_artists WHERE album_id IN (SELECT id FROM albums WHERE spotify_album_id IS NOT NULL)) AS album_artists,
        (SELECT count(*) FROM recording_artists WHERE recording_id IN (SELECT recording_id FROM recording_external_ids WHERE platform='spotify')) AS recording_artists,
        (SELECT count(*) FROM recording_external_ids WHERE recording_id IN (SELECT recording_id FROM recording_external_ids WHERE platform='spotify')) AS recording_external_ids
        """).fetchone()
    blockers = conn.execute("""SELECT
        (SELECT count(*) FROM recordings WHERE id IN (SELECT recording_id FROM recording_external_ids WHERE platform='spotify')
           AND (song_id IS NOT NULL OR title_ko IS NOT NULL OR official_video_id IS NOT NULL)) AS edited_recordings,
        (SELECT count(*) FROM albums WHERE id IN (SELECT id FROM albums WHERE spotify_album_id IS NOT NULL) AND title_ko IS NOT NULL) AS edited_albums,
        (SELECT count(*) FROM recording_lyrics WHERE recording_id IN (SELECT recording_id FROM recording_external_ids WHERE platform='spotify')) AS lyrics,
        (SELECT count(*) FROM catalog_changes WHERE (entity_type='albums' AND entity_id IN (SELECT id FROM albums WHERE spotify_album_id IS NOT NULL))
           OR (entity_type='recordings' AND entity_id IN (SELECT recording_id FROM recording_external_ids WHERE platform='spotify'))) AS history_rows,
        (SELECT count(*) FROM album_tracks WHERE recording_id IN (SELECT recording_id FROM recording_external_ids WHERE platform='spotify')
           AND album_id NOT IN (SELECT id FROM albums WHERE spotify_album_id IS NOT NULL)) AS tracks_on_other_albums
        """).fetchone()
    summary = {**counts, "blockers": blockers}
    if not write:
        return {"status": "preview", **summary}
    if any(blockers.values()):
        raise RuntimeError(f"Refusing to delete rows that carry later work: {blockers}")
    # Revision 006 credits cascade with their Spotify track IDs; keep them in the history row.
    credits = ("" if conn.execute("SELECT to_regclass('public.recording_provider_credits') AS t").fetchone()["t"] is None
               else """ || jsonb_build_object('provider_credits',
            (SELECT jsonb_agg(to_jsonb(c) - 'id' ORDER BY c.track_id, c.position) FROM recording_provider_credits c
             JOIN recording_external_ids x ON x.platform=c.platform AND x.external_id=c.track_id WHERE x.recording_id=r.id))""")
    before = conn.execute("""SELECT 'albums' AS entity_type, a.id AS entity_id, to_jsonb(a) AS data FROM albums a
            WHERE a.id IN (SELECT id FROM albums WHERE spotify_album_id IS NOT NULL)
        UNION ALL SELECT 'recordings', r.id, to_jsonb(r) || jsonb_build_object('external_ids',
            (SELECT jsonb_agg(jsonb_build_object('platform', x.platform, 'external_id', x.external_id))
             FROM recording_external_ids x WHERE x.recording_id=r.id))""" + credits + """ FROM recordings r
            WHERE r.id IN (SELECT recording_id FROM recording_external_ids WHERE platform='spotify')""").fetchall()
    digest = hashlib.sha256(json.dumps({"policy": POLICY, "counts": counts}, sort_keys=True).encode()).hexdigest()
    deleted_albums = conn.execute("DELETE FROM albums WHERE id IN (SELECT id FROM albums WHERE spotify_album_id IS NOT NULL)").rowcount
    deleted_recordings = conn.execute("DELETE FROM recordings WHERE id IN (SELECT recording_id FROM recording_external_ids WHERE platform='spotify')").rowcount
    if (deleted_albums, deleted_recordings) != (counts["albums"], counts["recordings"]):
        raise RuntimeError("Row counts changed during the purge")
    import_id = conn.execute("""INSERT INTO catalog_imports(operation_id,catalog_instance_id,manifest_hash,source_kind,
            result_mapping,result_summary) VALUES (%s,%s,%s,'correction','[]'::jsonb,%s) RETURNING id""",
        (uuid.uuid5(NAMESPACE, identity + ":" + digest), identity, digest,
         Jsonb({"kind": POLICY, "reason": "re-collect in the JP market with credited tracks only", **counts}))).fetchone()["id"]
    conn.execute("""INSERT INTO catalog_changes(import_id,entity_type,entity_id,action,before_data,after_data,provenance)
        SELECT %s, x.entity_type, x.entity_id, 'delete', x.data, NULL, %s
        FROM jsonb_to_recordset(%s::jsonb) x(entity_type text, entity_id integer, data jsonb)""",
                 (import_id, Jsonb({"policy": POLICY}), Jsonb([dict(r) for r in before])))
    return {"status": "committed", "import_id": import_id, **summary}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    with psycopg.connect(migrate_catalog.load_connection(), connect_timeout=20, row_factory=dict_row) as conn:
        migrate_catalog.configure_transaction(conn, read_only=not args.apply)
        result = run(conn, write=args.apply)
        if args.apply:
            conn.commit()
        else:
            conn.rollback()
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
