"""Disposable PostgreSQL and fake provider/storage; no production reads or writes."""
import asyncio
from io import BytesIO
from unittest.mock import AsyncMock, Mock

from PIL import Image
import pytest
from sqlalchemy import text

from test_catalog_migration import database, local_server, row
from test_phase4_runtime import runtime_store
from test_music_jobs import store
from app.integrations.avatar_sources import AvatarCandidate, AvatarSourceError
from app.repositories import avatar_jobs as repo
from app.services import avatar_jobs as service
from app.services.music_jobs import db_call

CHANNEL = 'UC' + 'a' * 22


@pytest.fixture
def images(monkeypatch):
    raw = BytesIO()
    Image.new('RGB', (600, 600), 'red').save(raw, format='PNG')
    async def discover(account):
        return AvatarCandidate(account_id=account['id'], platform=account['platform'],
                               external_id=account['platform_id'], source_url=f"https://image.test/{account['platform']}.png")
    lookup = AsyncMock(side_effect=discover)
    upload = Mock(side_effect=lambda prefix, *args: 'https://storage.test/avatars/' + prefix + '/512.webp')
    monkeypatch.setattr(service, 'discover', lookup)
    monkeypatch.setattr(service.avatar_storage, 'download', lambda url: raw.getvalue())
    monkeypatch.setattr(service.avatar_storage, 'upload', upload)
    return lookup, upload


def seed(db, *, avatar=None, relationship='owner', both=True):
    artist = row(db, 'artists', slug='singer', name_native='Singer', entity_kind='solo', avatar_url=avatar)
    accounts = []
    # X is intentionally linked first; SQL must still prefer YouTube.
    for platform in (['x', 'youtube'] if both else ['youtube']):
        account = row(db, 'external_accounts', platform=platform, platform_id=CHANNEL if platform == 'youtube' else '123',
                      url='https://youtube.com/@singer' if platform == 'youtube' else 'https://x.com/singer',
                      collection_enabled=False)
        row(db, 'artist_external_accounts', artist_id=artist, account_id=account,
            relationship=relationship, is_primary=True)
        accounts.append(account)
    db.commit()
    return artist, accounts


def call(function, *args, **kwargs):
    return asyncio.run(db_call(function, *args, **kwargs))


def drain():
    results = []
    for _ in range(10):
        result = asyncio.run(service.run_once())
        if result['status'] in ('idle', 'retry'):
            return results + [result]
        results.append(result)
    raise AssertionError('Avatar queue did not drain')


def due(db):
    db.execute("UPDATE avatar_jobs SET next_attempt_at=clock_timestamp()-interval '1 second' WHERE status='retry'")
    db.commit()


def test_avatar_claim_respects_artist_scope(store):
    artist, _ = seed(store, both=False)
    assert call(repo.claim, owner='scope-test', artist_ids=[]) is None
    assert store.execute("SELECT count(*) FROM avatar_jobs WHERE status='pending'").fetchone()[0] == 1
    selected = call(repo.claim, owner='scope-test', artist_ids=[artist])
    assert selected['artist_id'] == artist


def test_registration_atomic_queue_and_priority_even_with_collection_disabled(store, images):
    artist, _ = seed(store)
    jobs = store.execute('SELECT id,sources FROM avatar_jobs ORDER BY id').fetchall()
    assert len(jobs) == 2 and jobs[-1][1][0]['platform'] == 'youtube'
    assert call(repo.enqueue, artist) == jobs[-1][0]
    assert [r['status'] for r in drain()] == ['conflict', 'succeeded', 'idle']
    assert images[0].await_count == 1 and images[0].await_args.args[0]['platform'] == 'youtube'
    assert store.execute('SELECT avatar_url FROM artists WHERE id=%s', (artist,)).fetchone()[0].startswith('https://storage.test/')
    assert store.execute("SELECT count(*) FROM catalog_changes WHERE entity_type='artists' AND action='update'").fetchone()[0] == 1
    assert store.execute('SELECT count(*) FROM worker_jobs').fetchone()[0] == 0


def test_registration_rollback_removes_avatar_work(store, images):
    artist = row(store, 'artists', slug='rollback', name_native='Rollback', entity_kind='solo')
    account = row(store, 'external_accounts', platform='x', url='https://x.com/rollback')
    row(store, 'artist_external_accounts', artist_id=artist, account_id=account, relationship='owner')
    assert store.execute('SELECT count(*) FROM avatar_jobs').fetchone()[0] == 1
    store.rollback()
    assert store.execute('SELECT count(*) FROM avatar_jobs').fetchone()[0] == 0


@pytest.mark.parametrize('kwargs', [{'avatar': 'https://manual.test/image'}, {'relationship': 'member'}])
def test_manual_image_and_shared_member_channels_are_not_queued(store, images, kwargs):
    seed(store, **kwargs)
    assert store.execute('SELECT count(*) FROM avatar_jobs').fetchone()[0] == 0
    assert asyncio.run(service.run_once())['status'] == 'idle'
    images[0].assert_not_awaited()


def test_missing_youtube_falls_back_to_x(store, images):
    seed(store)
    original = images[0].side_effect
    async def lookup(account):
        if account['platform'] == 'youtube':
            raise AvatarSourceError('image_missing')
        return await original(account)
    images[0].side_effect = lookup
    drain()
    assert [c.args[0]['platform'] for c in images[0].await_args_list] == ['youtube', 'x']
    result = store.execute("SELECT result FROM avatar_jobs WHERE status='succeeded'").fetchone()[0]
    assert result['platform'] == 'x' and result['source_url'] == 'https://image.test/x.png'


def test_invalid_youtube_bitmap_falls_back_to_x(store, images, monkeypatch):
    seed(store)
    download = service.avatar_storage.download
    monkeypatch.setattr(service.avatar_storage, 'download', lambda url: b'invalid' if 'youtube' in url else download(url))
    drain()
    assert store.execute("SELECT result->>'platform' FROM avatar_jobs WHERE status='succeeded'").fetchone()[0] == 'x'


def test_retry_after_then_bounded_provider_fallback(store, images):
    seed(store)
    original = images[0].side_effect
    async def lookup(account):
        if account['platform'] == 'youtube':
            raise AvatarSourceError('quotaExceeded', retry=True, retry_after=900)
        return await original(account)
    images[0].side_effect = lookup
    assert drain()[-1]['status'] == 'retry'
    assert store.execute("SELECT next_attempt_at>clock_timestamp()+interval '14 minutes' FROM avatar_jobs WHERE status='retry'").fetchone()[0]
    due(store)
    assert drain()[-1]['status'] == 'retry'
    due(store)
    assert 'succeeded' in [r['status'] for r in drain()]
    assert images[0].await_args.args[0]['platform'] == 'x'


def test_both_sources_fail_without_removing_artist(store, images):
    artist, _ = seed(store)
    images[0].side_effect = AvatarSourceError('image_missing')
    assert 'no_source' in [r['status'] for r in drain()]
    assert store.execute('SELECT avatar_url FROM artists WHERE id=%s', (artist,)).fetchone() == (None,)
    images[1].assert_not_called()


def test_upload_retry_preserves_provider_selection(store, images, caplog):
    seed(store, both=False)
    images[1].side_effect = RuntimeError('storage credential secret')
    assert drain()[-1]['status'] == 'retry'
    result = store.execute("SELECT result FROM avatar_jobs WHERE status='retry'").fetchone()[0]
    assert result['source_url'] == 'https://image.test/youtube.png'
    assert result['storage_error'] == {'stage': 'storage', 'code': 'storage_exception', 'error_type': 'RuntimeError'}
    assert 'Avatar storage failed' in caplog.text and 'storage_exception' in caplog.text
    assert 'storage credential secret' not in str(result) + caplog.text
    due(store)
    images[1].side_effect = lambda prefix, *args: 'https://storage.test/' + prefix + '/512.webp'
    images[0].side_effect = AssertionError('Provider should not be called again')
    assert 'succeeded' in [r['status'] for r in drain()]
    assert images[0].await_count == 1
    assert 'storage_error' not in store.execute("SELECT result FROM avatar_jobs WHERE status='succeeded'").fetchone()[0]


def test_detailed_storage_error_is_persisted_through_retry_exhaustion(store, images, caplog):
    artist, _ = seed(store, both=False)
    details = {'stage': 'upload_original', 'object_name': 'original', 'code': 's3_error',
               'error_type': 'ClientError', 'provider_code': 'SignatureDoesNotMatch', 'http_status': 403}
    images[1].side_effect = service.avatar_storage.AvatarStorageError(details)
    assert drain()[-1]['status'] == 'retry'
    store.execute("UPDATE avatar_jobs SET attempt_count=max_attempts-1 WHERE status='retry'")
    store.commit()
    due(store)
    assert 'failed' in [r['status'] for r in drain()]
    status, error, result = store.execute('SELECT status,last_error,result FROM avatar_jobs').fetchone()
    assert status == 'failed' and error == 'avatar_storage_failed'
    assert result['storage_error'] == details
    assert 'SignatureDoesNotMatch' in caplog.text and 'upload_original' in caplog.text
    assert images[0].await_count == 1
    assert store.execute('SELECT avatar_url FROM artists WHERE id=%s', (artist,)).fetchone() == (None,)


def test_manual_change_during_upload_is_preserved(store, images):
    artist, _ = seed(store, both=False)
    def upload(prefix, *args):
        call(lambda session: session.execute(text("UPDATE artists SET avatar_url='https://manual.test/new' WHERE id=:id"), {'id': artist}))
        return 'https://storage.test/' + prefix + '/512.webp'
    images[1].side_effect = upload
    assert 'skipped_existing' in [r['status'] for r in drain()]
    assert store.execute('SELECT avatar_url FROM artists WHERE id=%s', (artist,)).fetchone()[0] == 'https://manual.test/new'
    assert store.execute('SELECT count(*) FROM catalog_changes').fetchone()[0] == 0


def test_account_change_invalidates_pending_snapshot_and_enqueues_replacement(store, images):
    seed(store, both=False)
    store.execute("UPDATE external_accounts SET url='https://youtube.com/@renamed'")
    store.commit()
    assert store.execute('SELECT count(*) FROM avatar_jobs').fetchone()[0] == 2
    assert [r['status'] for r in drain()] == ['conflict', 'succeeded', 'idle']


def test_expired_lease_recovered_and_last_attempt_exhausted(store, images):
    seed(store, both=False)
    first = call(repo.claim, owner='dead-worker')
    assert call(repo.claim, owner='second') is None
    store.execute("UPDATE avatar_jobs SET lease_expires_at=clock_timestamp()-interval '1 second'")
    store.commit()
    second = call(repo.claim, owner='second')
    assert second['attempt_count'] == 2 and second['id'] == first['id']
    assert call(repo.finish, first, 'no_source') == 'lease_lost'
    store.execute("UPDATE avatar_jobs SET attempt_count=max_attempts,lease_expires_at=clock_timestamp()-interval '1 second'")
    store.commit()
    assert call(repo.claim, owner='third') is None
    assert store.execute('SELECT status,last_error FROM avatar_jobs').fetchone() == ('failed', 'lease_exhausted')


def test_account_ownership_removed_during_upload_does_not_publish(store, images):
    seed(store, both=False)
    def upload(prefix, *args):
        call(lambda session: session.execute(text("UPDATE artist_external_accounts SET relationship='member'")))
        return 'https://storage.test/' + prefix + '/512.webp'
    images[1].side_effect = upload
    assert 'conflict' in [r['status'] for r in drain()]
    assert store.execute('SELECT avatar_url FROM artists').fetchone() == (None,)


def test_later_link_is_queued_and_artist_archive_prevents_network(store, images):
    artist = row(store, 'artists', slug='later', name_native='Later', entity_kind='solo')
    store.commit()
    assert store.execute('SELECT count(*) FROM avatar_jobs').fetchone()[0] == 0
    account = row(store, 'external_accounts', platform='youtube', platform_id=CHANNEL, url='https://youtube.com/@later')
    row(store, 'artist_external_accounts', artist_id=artist, account_id=account, relationship='owner')
    store.execute('UPDATE artists SET archived_at=clock_timestamp() WHERE id=%s', (artist,))
    store.commit()
    assert 'conflict' in [r['status'] for r in drain()]
    images[0].assert_not_awaited()


def test_indie_seed_dry_run_apply_and_rerun(store, images):
    import json
    from scripts.register_indie_utawaku import register, SEED
    items = json.loads(SEED.read_text(encoding='utf-8'))
    assert register(store, items, write=False)['status'] == 'dry_run'
    assert store.execute('SELECT count(*) FROM artists').fetchone()[0] == 0
    result = register(store, items, write=True)
    store.commit()
    assert result['status'] == 'committed'
    assert all(plan['avatar_job_id'] for plan in result['plans'])
    assert store.execute('SELECT count(*) FROM avatar_jobs').fetchone()[0] == 3
    assert register(store, items, write=True)['status'] == 'already_registered'
    store.commit()
    assert store.execute('SELECT count(*) FROM avatar_jobs').fetchone()[0] == 3
    assert store.execute('SELECT count(*) FROM worker_jobs').fetchone()[0] == 3


def test_migration_guard_rejects_missing_avatar_trigger(store):
    from test_catalog_migration import migration
    store.execute('DROP TRIGGER avatar_link_enqueue ON artist_external_accounts')
    with pytest.raises(migration.MigrationError, match='triggers are missing'):
        migration.verify(store)


def test_concurrent_claims_serialize_different_snapshots_of_same_artist(store):
    from concurrent.futures import ThreadPoolExecutor
    seed(store)
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = list(pool.map(lambda owner: call(repo.claim, owner=owner), ['one', 'two']))
    assert sum(job is not None for job in jobs) == 1


def test_provider_cooldown_does_not_spend_other_artists_attempts(store, images):
    seed(store, both=False)
    other = row(store, 'artists', slug='other', name_native='Other', entity_kind='solo')
    account = row(store, 'external_accounts', platform='youtube', platform_id='UC'+'b'*22, url='https://youtube.com/@other')
    row(store, 'artist_external_accounts', artist_id=other, account_id=account, relationship='owner')
    store.commit()
    images[0].side_effect = AvatarSourceError('quotaExceeded', retry=True, retry_after=900)
    assert asyncio.run(service.run_once())['status'] == 'retry'
    assert asyncio.run(service.run_once())['status'] == 'idle'
    assert store.execute('SELECT attempt_count FROM avatar_jobs WHERE artist_id=%s', (other,)).fetchone() == (0,)


def test_upgrade_from_006_does_not_enqueue_existing_artists(database):
    from test_catalog_migration import migration
    database.execute('''CREATE TABLE catalog_schema_migrations(version text PRIMARY KEY,
        checksum text NOT NULL CHECK(checksum ~ '^[0-9a-f]{64}$'),
        applied_at timestamptz NOT NULL DEFAULT clock_timestamp())''')
    for version, path in migration.migration_files():
        if version == '007':
            break
        database.execute(path.read_text(encoding='utf-8'), prepare=False)
        database.execute('INSERT INTO catalog_schema_migrations(version,checksum) VALUES (%s,%s)',
                         (version, migration.migration_checksums()[version]))
    artist = row(database, 'artists', slug='old', name_native='Old', entity_kind='solo')
    account = row(database, 'external_accounts', platform='x', url='https://x.com/old')
    row(database, 'artist_external_accounts', artist_id=artist, account_id=account, relationship='owner')
    database.commit()
    report = migration.migrate(database)
    database.commit()
    assert report['applied_versions'] == ['007']
    assert database.execute('SELECT count(*) FROM avatar_jobs').fetchone() == (0,)
    assert database.execute('SELECT avatar_enqueue(%s)', (artist,)).fetchone()[0] is not None
