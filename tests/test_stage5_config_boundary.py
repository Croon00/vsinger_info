"""The unified runtime cannot accidentally open a legacy SQL connection."""
import pytest

from app.core import db as legacy_db
from app.core.config import Settings
from app.db import catalog_session, session as legacy_session
from app.services import avatar_assets


def test_single_database_setting_and_retired_alias(monkeypatch):
    monkeypatch.delenv('NEW_DATABASE_URL', raising=False)
    selected = Settings(_env_file=None, database_url='postgresql://fixture/new')
    assert selected.database_url == 'postgresql://fixture/new'
    assert not hasattr(selected, 'new_database_url')
    monkeypatch.setenv('NEW_DATABASE_URL', 'postgresql://fixture/old-name')
    with pytest.raises(ValueError, match='NEW_DATABASE_URL is retired'):
        Settings(_env_file=None, database_url='postgresql://fixture/new')


def test_legacy_database_paths_stop_before_connect(monkeypatch):
    monkeypatch.setattr(legacy_db.psycopg, 'connect', lambda *_a, **_k: pytest.fail('legacy connection opened'))
    monkeypatch.setattr(legacy_session, 'create_engine', lambda *_a, **_k: pytest.fail('legacy engine opened'))
    with pytest.raises(RuntimeError, match='Legacy SQL access is disabled'):
        legacy_db.get_connection()
    with pytest.raises(RuntimeError, match='Legacy SQL access is disabled'):
        legacy_session.get_engine()
    with pytest.raises(RuntimeError, match='Legacy SQL access is disabled'):
        legacy_session._engine_for_url('postgresql://fixture/legacy')


def test_image_urls_do_not_use_upload_credentials(monkeypatch):
    monkeypatch.setattr(avatar_assets, 'public_storage_settings', lambda: {
        'AWS_ENDPOINT_URL_S3': 'https://images.example', 'AVATAR_BUCKET': 'artists'})
    monkeypatch.setattr(avatar_assets, 'storage_settings', lambda: pytest.fail('upload settings read'))
    assert avatar_assets.public_base() == 'https://images.example/artists/'
