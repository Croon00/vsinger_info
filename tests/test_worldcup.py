from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routers import worldcup as router_module
from app.core.config import settings
from app.db.catalog_session import get_catalog_session
from app.schemas.worldcup import WorldcupSubmission
from app.services.worldcup import AddressLimiter, SubmissionRejected, check_pace, validate_bracket


def video(n):
    return f'vid{n:08d}'


def bracket(size=16, seconds=600, **extra):
    """A complete bracket where the left song always wins."""
    matches, alive, remaining = [], [video(n) for n in range(size)], size
    while remaining >= 2:
        winners = []
        for i in range(0, remaining, 2):
            matches.append(dict(round=remaining, winner=alive[i], loser=alive[i + 1]))
            winners.append(alive[i])
        alive, remaining = winners, remaining // 2
    return dict(submission_id=str(uuid4()), client_id=str(uuid4()), scope_kind='agency', scope_label='Label',
                size=size, duration_seconds=seconds, matches=matches, **extra)


@pytest.mark.parametrize('size', [8, 16, 32, 64, 128])
def test_complete_brackets_validate(size):
    first, champion = validate_bracket(WorldcupSubmission(**bracket(size)))
    assert len(first) == size and champion == video(0)


@pytest.mark.parametrize('tamper, reason', [
    (lambda b: b['matches'].append(dict(b['matches'][0])), 'match_count'),
    (lambda b: b['matches'].reverse(), 'round_order'),
    (lambda b: b['matches'][1].update(loser=video(0)), 'duplicate_song'),
    (lambda b: b['matches'][8].update(winner=video(3)), 'pairing'),  # round two must pair round-one winners
    (lambda b: b['matches'][-1].update(winner=video(15), loser=video(14)), 'pairing'),
])
def test_tampered_brackets_are_rejected(tamper, reason):
    data = bracket(16)
    tamper(data)
    with pytest.raises(SubmissionRejected, match=reason):
        validate_bracket(WorldcupSubmission(**data))


def test_pace_and_address_window():
    with pytest.raises(SubmissionRejected, match='too_fast'):
        check_pace(WorldcupSubmission(**bracket(16, seconds=14)))
    check_pace(WorldcupSubmission(**bracket(16, seconds=15)))
    limiter = AddressLimiter(limit=2, window=10)
    assert limiter.allow('a', 0) and limiter.allow('a', 1) and not limiter.allow('a', 2)
    assert limiter.allow('b', 2) and limiter.allow('a', 11.5)


@pytest.fixture
def api(monkeypatch):
    app = FastAPI()
    app.include_router(router_module.router, prefix='/api')
    state = SimpleNamespace(ready=True, runs={}, stats_calls=[], official=None, recent=0, commits=0, kinds=[])

    class FakeSession:
        def commit(self):
            state.commits += 1

    app.dependency_overrides[router_module.write_session] = lambda: FakeSession()
    app.dependency_overrides[get_catalog_session] = lambda: FakeSession()
    repo = router_module.repository
    monkeypatch.setattr(repo, 'ready', lambda session: state.ready)
    monkeypatch.setattr(repo, 'submission_run', lambda session, sid: state.runs.get(sid))

    def insert(session, submission, champion, is_local):
        run = SimpleNamespace(id=len(state.runs) + 1, is_local=is_local, champion=champion,
                              song_kind=submission.song_kind)
        state.runs[submission.submission_id] = run
        return run.id
    monkeypatch.setattr(repo, 'insert_run', insert)
    def playable(session, ids, kind):
        state.kinds.append(kind)
        return state.official if state.official is not None else set(ids)
    monkeypatch.setattr(repo, 'playable_videos', playable)
    monkeypatch.setattr(repo, 'recent_client_runs', lambda session, client: state.recent)

    def stats(session, **kwargs):
        state.stats_calls.append(kwargs)
        item = dict(video_id=video(0), title='Song', appearances=1, championships=1, championship_rate=1.0,
                    match_wins=4, match_losses=0, match_win_rate=1.0)
        return dict(items=[item], total=1, offset=kwargs.get('offset', 0), limit=kwargs.get('limit', 50), total_runs=1)
    monkeypatch.setattr(repo, 'stats', stats)
    monkeypatch.setattr(router_module, 'address_limiter', AddressLimiter(limit=1000))
    monkeypatch.setattr(settings, 'api_key', 'fixture')
    with TestClient(app, headers={'X-API-Key': 'fixture'}) as client:
        yield client, state


def test_submit_stores_once_and_flags_local_runs(api):
    client, state = api
    data = bracket(16)
    response = client.post('/api/worldcup/results', json=data, headers={'X-UtaMowa-Client': 'local-dev'})
    assert response.status_code == 201, response.text
    assert response.json()['winner']['championships'] == 1 and state.commits == 1
    run = next(iter(state.runs.values()))
    assert run.is_local is True and run.champion == video(0)
    assert state.stats_calls[-1]['include_local'] is True
    again = client.post('/api/worldcup/results', json=data)
    assert again.status_code == 200 and again.json()['duplicate'] is True and len(state.runs) == 1
    public = client.post('/api/worldcup/results', json=bracket(8, seconds=7))
    assert public.status_code == 201 and list(state.runs.values())[-1].is_local is False
    assert state.kinds[-1] == 'original' and state.stats_calls[-1]['song_kind'] == 'original'
    cover = client.post('/api/worldcup/results', json=bracket(8, seconds=7, song_kind='cover'))
    assert cover.status_code == 201 and list(state.runs.values())[-1].song_kind == 'cover'
    assert state.kinds[-1] == 'cover' and state.stats_calls[-1]['song_kind'] == 'cover'
    assert client.post('/api/worldcup/results', json=bracket(16, song_kind='live')).status_code == 422


def test_submit_rejections(api):
    client, state = api
    assert client.post('/api/worldcup/results', json=bracket(16, seconds=3)).json()['detail'] == 'invalid_bracket:too_fast'
    state.official = {video(n) for n in range(15)}
    assert client.post('/api/worldcup/results', json=bracket(16)).json()['detail'] == 'invalid_bracket:unknown_song'
    state.official, state.recent = None, 20
    assert client.post('/api/worldcup/results', json=bracket(16)).status_code == 429
    state.recent = 0
    assert client.post('/api/worldcup/results', json={**bracket(16), 'size': 12}).status_code == 422
    assert client.post('/api/worldcup/results', json={**bracket(16), 'extra': 1}).status_code == 422
    state.ready = False
    assert client.post('/api/worldcup/results', json=bracket(16)).status_code == 503
    assert not state.runs


def test_stats_parameters_and_local_visibility(api):
    client, state = api
    response = client.get('/api/worldcup/stats', params=[('agency', 'Label'), ('order', 'match_win_rate'),
                                                         ('video_ids', video(2)), ('video_ids', video(1)),
                                                         ('min_appearances', '3'), ('limit', '10')])
    assert response.status_code == 200, response.text
    assert response.headers['cache-control'] == 'private, no-store'
    assert state.stats_calls[-1] == dict(include_local=False, song_kind='original', agency='Label',
                                         video_ids=[video(1), video(2)], order='match_win_rate',
                                         min_appearances=3, offset=0, limit=10)
    client.get('/api/worldcup/stats?song_kind=cover')
    assert state.stats_calls[-1]['song_kind'] == 'cover'
    assert client.get('/api/worldcup/stats?song_kind=live').status_code == 422
    client.get('/api/worldcup/stats', headers={'X-UtaMowa-Client': 'local-dev'})
    assert state.stats_calls[-1]['include_local'] is True
    for query in ['order=bad', 'video_ids=short', 'limit=0', 'min_appearances=0']:
        assert client.get('/api/worldcup/stats?' + query).status_code == 422
    state.ready = False
    assert client.get('/api/worldcup/stats').status_code == 503


def test_pool_summary_counts_each_song_once_per_artist_and_agency():
    from app.services.worldcup_pool import summarize
    artists = [(1, 'A', 'Label'), (2, 'B', 'Label'), (3, 'C', 'Other'), (4, 'Group', 'Label')]
    entries = [dict(artist_name='A'), dict(artist_name='A · B'), dict(artist_name='C · A'),
               dict(artist_name='Group'), dict(artist_name='Unknown'), dict(artist_name='')]
    result = summarize(entries, artists)
    assert result['total'] == 6
    assert result['artists'] == [dict(id=1, count=3), dict(id=2, count=1), dict(id=3, count=1), dict(id=4, count=1)]
    assert result['agencies'] == [dict(name='Label', count=4), dict(name='Other', count=1)]


def test_pool_summary_endpoint_caches_per_kind(api, monkeypatch):
    client, _ = api
    from app.services import worldcup_pool
    calls = []
    monkeypatch.setattr(worldcup_pool, '_cache', {})
    monkeypatch.setattr(worldcup_pool, '_entries', lambda session, kind: calls.append(kind) or [dict(artist_name='A')])
    class Session:
        def execute(self, *_):
            return SimpleNamespace(all=lambda: [(1, 'A', 'Label')])
    from app.api.routers import worldcup as module
    module_app = client.app
    module_app.dependency_overrides[get_catalog_session] = lambda: Session()
    first = client.get('/api/worldcup/pool-summary?song_kind=cover')
    assert first.status_code == 200, first.text
    assert first.json() == dict(song_kind='cover', total=1, agencies=[dict(name='Label', count=1)],
                                artists=[dict(id=1, count=1)])
    client.get('/api/worldcup/pool-summary?song_kind=cover')
    client.get('/api/worldcup/pool-summary')
    assert calls == ['cover', 'original']
    assert client.get('/api/worldcup/pool-summary?song_kind=live').status_code == 422
