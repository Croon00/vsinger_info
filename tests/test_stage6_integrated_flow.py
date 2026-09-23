"""A migrated runtime job reaches the catalog API through a fake provider."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from test_catalog_migration import database, local_server, row
from test_phase4_runtime import runtime_store
from test_runtime_state_migration import fixture_plan, runtime
from test_youtube_catalog_collection import CHANNEL, comment, video

from app.api.main import app
from app.core.config import settings
from app.db.catalog_session import get_catalog_session
from app.schemas.worker_jobs import JobRequest
from app.services import music_jobs, notification_delivery, youtube_collection


def test_migrated_youtube_job_reaches_real_api_without_resending_x(runtime_store, monkeypatch):
    db = runtime_store
    artist = row(db, 'artists', entity_kind='group', slug='stage-six',
                 name_native='Stage Six', show_in_catalog=True)
    account = row(db, 'external_accounts', platform='youtube', platform_id=CHANNEL,
                  url=f'https://www.youtube.com/channel/{CHANNEL}', collection_enabled=True)
    row(db, 'artist_external_accounts', artist_id=artist, account_id=account,
        relationship='owner')
    db.commit()

    plan = fixture_plan(db)
    request = JobRequest(job_type='youtube_collect', external_account_id=account,
                         payload={'channel_id': CHANNEL, 'youtube_video_id': 'abcdefghijk',
                                  'purpose': 'archive'})
    migrated_job = plan['worker_jobs'][0]
    migrated_job['external_account_id'] = account
    migrated_job['idempotency_key'] = request.key()
    migrated_job['payload'] = request.parsed_payload().model_dump()
    plan['account_versions'][str(account)] = 1
    manifest = runtime.public_manifest(plan)
    manifest['approved_for_apply'] = True
    assert runtime.apply_plan(db, plan, manifest)['applied']
    db.commit()

    assert db.execute("SELECT count(*) AS n FROM notification_deliveries WHERE status='sent'").fetchone()['n'] == 1
    assert db.execute("SELECT count(*) AS n FROM notification_deliveries WHERE status='pending'").fetchone()['n'] == 0
    assert db.execute("SELECT count(*) AS n FROM worker_jobs WHERE job_type='youtube_collect'").fetchone()['n'] == 1

    fake = SimpleNamespace(videos=AsyncMock(return_value=[video(channel_id=CHANNEL)]),
                           comments=AsyncMock(return_value=([comment()], False)))
    monkeypatch.setattr(youtube_collection, 'client', lambda: fake)
    monkeypatch.setattr(youtube_collection, 'extract_youtube_setlist', AsyncMock(return_value=None))
    monkeypatch.setattr(music_jobs, 'catalog_runtime_session',
                        notification_delivery.catalog_runtime_session)
    assert asyncio.run(music_jobs.run_once(
        handlers=youtube_collection.handlers(), min_interval_seconds=0))['status'] == 'succeeded'

    def session():
        with notification_delivery.catalog_runtime_session() as current:
            yield current

    app.dependency_overrides[get_catalog_session] = session
    monkeypatch.setattr(settings, 'api_key', 'stage-six-fixture')
    try:
        with TestClient(app, headers={'X-API-Key': 'stage-six-fixture'}) as api:
            listing = api.get(f'/api/artists/{artist}/lives')
            assert listing.status_code == 200, listing.text
            assert listing.json()['total'] == 1
            archive = listing.json()['items'][0]['id']
            detail = api.get(f'/api/lives/{archive}')
            assert detail.status_code == 200, detail.text
            assert len(detail.json()['performances']) == 2
            assert api.get(f'/api/v2/lives/{archive}').json() == detail.json()
    finally:
        app.dependency_overrides.pop(get_catalog_session, None)

    assert fake.videos.await_count == 1
    assert fake.comments.await_count == 1
    assert db.execute("SELECT count(*) AS n FROM notification_deliveries WHERE status='pending'").fetchone()['n'] == 0
    assert db.execute("SELECT count(*) AS n FROM performances").fetchone()['n'] == 2
