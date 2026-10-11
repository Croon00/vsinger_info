import asyncio
from unittest.mock import AsyncMock
import pytest
from app.integrations.spotify_catalog import SpotifyCatalogClient, SpotifyFailure
from app.services.spotify_discovery import decide
from scripts import discover_spotify_accounts as tool

ID = 'a' * 22
ARTIST = dict(id=1, version=2, name_native='AZKi', name_latin=None, name_ko='아즈키')


@pytest.fixture
def cache_dir():
    class MemoryFile:
        content = None
        def __truediv__(self, name):
            return self
        def exists(self):
            return self.content is not None
        def read_text(self, **kwargs):
            return self.content
        def write_text(self, content, **kwargs):
            self.content = content
    return MemoryFile()


def decision(candidates, **kwargs):
    return decide(ARTIST, candidates, complete=kwargs.get('complete', True),
                  occupied_ids=kwargs.get('occupied', set()), rejected_ids=kwargs.get('rejected', set()))


def test_unique_exact_name_and_duplicate_search_results():
    candidate = dict(id=ID, name='AZKi')
    result = decision([candidate, candidate, dict(id='b'*22, name='AZKi Tribute')])
    assert result['status'] == 'match' and result['spotify_id'] == ID
    assert len(result['candidates']) == 1


@pytest.mark.parametrize('candidates,options,reason', [
    ([dict(id=ID, name='AZKi'), dict(id='b'*22, name='AZKi')], {}, 'multiple_exact_names'),
    ([dict(id=ID, name='AZKi')], {'complete': False}, 'incomplete_search'),
    ([dict(id=ID, name='AZKi')], {'occupied': {ID}}, 'existing_account_ownership'),
    ([dict(id=ID, name='AZKi')], {'rejected': {ID}}, 'previously_rejected_identity'),
    ([dict(id=ID, name='AZ Ki')], {}, 'no_exact_name'),
    ([dict(id=ID, name='AZKi Tribute')], {}, 'no_exact_name'),
])
def test_unsafe_candidates_are_not_linked(candidates, options, reason):
    result = decision(candidates, **options)
    assert result['status'] != 'match' and result['reason'] == reason


def test_search_pagination_finds_second_exact_candidate():
    client = SpotifyCatalogClient('', '', interval_seconds=0)
    client.get = AsyncMock(side_effect=[
        dict(artists=dict(items=[dict(id=ID, name='AZKi')], next='provider-url', total=2)),
        dict(artists=dict(items=[dict(id='b'*22, name='AZKi')], next=None, total=2)),
    ])
    items, complete = asyncio.run(client.search_artists('AZKi'))
    assert complete and len(items) == 2
    assert client.get.call_args_list[1].kwargs['params']['offset'] == 1
    assert decision(items)['reason'] == 'multiple_exact_names'


@pytest.mark.parametrize('listing', [
    dict(items=[], next='next', total=20),
    dict(items=[dict(id=ID, name='AZKi')], next=None, total=20),
    dict(items=[dict(id=ID, name='AZKi')], next='next', total=20),
])
def test_search_truncation_never_proves_unique_identity(listing):
    client = SpotifyCatalogClient('', '')
    client.get = AsyncMock(return_value=dict(artists=listing))
    _, complete = asyncio.run(client.search_artists('AZKi', max_pages=1))
    assert not complete


def test_malformed_search_is_rejected():
    client = SpotifyCatalogClient('', '')
    client.get = AsyncMock(return_value=dict(artists=dict(items=[dict(id='bad', name='AZKi')],total=1)))
    with pytest.raises(SpotifyFailure, match='malformed_artist_search'):
        asyncio.run(client.search_artists('AZKi'))


def test_rate_limit_is_preserved():
    client = SpotifyCatalogClient('', '')
    client.get = AsyncMock(side_effect=SpotifyFailure('rate_limited', retry=True, retry_after=120))
    with pytest.raises(SpotifyFailure) as exc:
        asyncio.run(client.search_artists('AZKi'))
    assert exc.value.retry_after == 120 and client.get.call_count == 1


def test_discovery_preserves_prior_identity_review(cache_dir, monkeypatch):
    provider = SpotifyCatalogClient('', '')
    provider.search_artists = AsyncMock(return_value=([dict(id=ID, name='AZKi')], True))
    monkeypatch.setattr(tool, 'SpotifyCatalogClient', lambda *args, **kwargs: provider)
    monkeypatch.setattr(tool, 'rejected_ids', lambda: set())
    monkeypatch.setattr(tool, 'previously_skipped_artists', lambda: {1})
    results = asyncio.run(tool.research([ARTIST], set(), cache_dir))
    assert results[0]['status'] == 'review'
    assert results[0]['reason'] == 'previous_identity_review_requires_recheck'


def test_discovery_does_not_assign_same_profile_to_two_artists(cache_dir, monkeypatch):
    provider = SpotifyCatalogClient('', '')
    provider.search_artists = AsyncMock(return_value=([dict(id=ID, name='AZKi')], True))
    monkeypatch.setattr(tool, 'SpotifyCatalogClient', lambda *args, **kwargs: provider)
    monkeypatch.setattr(tool, 'rejected_ids', lambda: set())
    monkeypatch.setattr(tool, 'previously_skipped_artists', lambda: set())
    results = asyncio.run(tool.research([ARTIST, dict(ARTIST, id=2)], set(), cache_dir))
    assert all(r['status'] == 'review' and r['reason'] == 'shared_candidate_between_catalog_artists' for r in results)


def test_discovery_stops_batch_on_rate_limit(cache_dir, monkeypatch):
    provider = SpotifyCatalogClient('', '')
    provider.search_artists = AsyncMock(side_effect=SpotifyFailure('rate_limited', retry=True, retry_after=120))
    monkeypatch.setattr(tool, 'SpotifyCatalogClient', lambda *args, **kwargs: provider)
    monkeypatch.setattr(tool, 'rejected_ids', lambda: set())
    monkeypatch.setattr(tool, 'previously_skipped_artists', lambda: set())
    results = asyncio.run(tool.research([ARTIST, dict(ARTIST, id=2)], set(), cache_dir))
    assert len(results) == 1 and results[0]['status'] == 'error'
    assert results[0]['retry_after'] == 120 and provider.search_artists.call_count == 1
