"""Purging the KR-market Spotify collection, on a disposable local PostgreSQL."""
import importlib.util
from pathlib import Path

import pytest
from psycopg.rows import dict_row

from test_catalog_migration import local_server, database, apply as apply_schema, row  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("purge_spotify_collection", ROOT / "scripts/purge_spotify_collection.py")
purge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(purge)


def cur(db):
    return db.cursor(row_factory=dict_row)


def test_purge_deletes_spotify_rows_keeps_others_and_records_history(database):
    apply_schema(database)
    artist = row(database, "artists", slug="s", name_native="S", entity_kind="solo")
    album = row(database, "albums", title_native="A", album_type="single", spotify_album_id="a" * 22)
    keep_album = row(database, "albums", title_native="Manual", album_type="album")
    rec = row(database, "recordings", title_native="T")
    keep_rec = row(database, "recordings", title_native="Manual T")
    row(database, "recording_external_ids", recording_id=rec, platform="spotify", external_id="t" * 22)
    row(database, "recording_external_ids", recording_id=rec, platform="isrc", external_id="JPU902602729")
    row(database, "recording_artists", recording_id=rec, artist_id=artist, role="primary")
    row(database, "album_artists", album_id=album, artist_id=artist)
    row(database, "album_tracks", album_id=album, recording_id=rec, disc_number=1, track_number=1)
    row(database, "album_tracks", album_id=keep_album, recording_id=keep_rec, disc_number=1, track_number=1)
    database.commit()
    preview = purge.run(cur(database), write=False)
    database.rollback()
    assert (preview["albums"], preview["recordings"], preview["recording_external_ids"]) == (1, 1, 2)
    result = purge.run(cur(database), write=True)
    database.commit()
    assert result["status"] == "committed"
    assert [r[0] for r in database.execute("SELECT id FROM albums")] == [keep_album]
    assert [r[0] for r in database.execute("SELECT id FROM recordings")] == [keep_rec]
    assert database.execute("SELECT count(*) FROM recording_external_ids").fetchone()[0] == 0
    history = database.execute("SELECT entity_type, before_data->>'title_native' FROM catalog_changes WHERE action='delete' ORDER BY 1").fetchall()
    assert history == [("albums", "A"), ("recordings", "T")]
    again = purge.run(cur(database), write=True)
    database.commit()
    assert (again["albums"], again["recordings"]) == (0, 0)


def test_purge_refuses_rows_with_later_work(database):
    apply_schema(database)
    rec = row(database, "recordings", title_native="T", title_ko="티")
    row(database, "recording_external_ids", recording_id=rec, platform="spotify", external_id="t" * 22)
    database.commit()
    with pytest.raises(RuntimeError, match="edited_recordings"):
        purge.run(cur(database), write=True)
    database.rollback()
    assert database.execute("SELECT count(*) FROM recordings").fetchone()[0] == 1

