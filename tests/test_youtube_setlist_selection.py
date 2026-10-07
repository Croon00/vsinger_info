"""Offline regression of live 5850 comments captured on 2026-10-06.

Semantic decisions are fixtures, not claims about live model accuracy.
"""
import asyncio
import hashlib
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from openai import APIConnectionError, APIStatusError

from app.integrations import youtube_setlist as integration
from app.integrations.youtube_catalog import Comment, parse_setlist
from app.integrations.youtube_setlist import ComparisonResult, SetlistDecision
from app.schemas.worker_jobs import JobRequest
from app.services import youtube_setlist as service


CHAT = '''5:07 配信開始！
13:10 てあせ！
18:34 みかげさんがよく汗をかくところ（手、おでこ、膝の裏）
35:55 「ありがとうのありがとう！！」
45:45 恋の炊き込みご飯！
1:21:30 深影さんは実は日本酒は飲めない！
1:30:42 自己紹介するみかげさん（可愛い！！！！！！ww）MIKAGE！！
2:01:50 ワールドワイドみかげ！！
2:05:50 「面白いこと言えなかった！！！泣」
2:09:38 飲酒配信に興味ありネキ（みかげさん）
2:10:32 みかげさんはIPAがわからない＆ビールの香りが苦手
2:13:00 みかげさんはサワーも飲めない
2:13:08 みかげさんはほろ酔いを飲みきれないでガチ酔いするレベル（3分の1で）
2:21:48 「被写隊のセイレーン」ww
2:25:41 深影さん、羽緒たん、れうちんの中で唯一お酒を飲むのがれうちん
2:26:10 「寒いのいやーーー！！！」'''
SONGS = '''SetList
0:06:30　01. STAND-ALONE / Aimer
0:24:58　02. ray / BUMP OF CHICKEN
0:40:06　03. 441 / miwa
0:57:57　04. ブルーバード / いきものがかり
1:09:10　05. Ham / ずっと真夜中でいいのに。
1:23:10　06. 冬眠 / ヨルシカ
1:35:03　07. 星の唄 / buzzG
1:43:39　08. メトロノーム / 米津玄師
1:55:30　09. 弱虫モンブラン / DECO*27
2:14:08　10. from Y to Y / ジミーサムP
2:33:51　11. 燈 / 崎山蒼志
2:40:52　12. 裸の勇者 / Vaundy
3:00:06　13. 心做し / 蝶々P
3:12:41　14. 楓 / スピッツ'''


def comment(identifier, content):
    return Comment(id=identifier, text=content, captured_at=datetime.now(UTC))


def decision_for_5850(contexts):
    songs = []
    for number, line in enumerate(SONGS.splitlines()[1:], 2):
        timestamp, numbered = line.split('　')
        title, artist = numbered.split('. ', 1)[1].split(' / ')
        songs.append(dict(line_number=number, timestamp=timestamp, title=title, original_artist=artist))
    return ComparisonResult(status='ok', decision=SetlistDecision(
        decision='selected', selected_candidate_id='songs', reason='Fourteen explicit song/artist pairs; other comment is chat.',
        judgments=[dict(candidate_id=c['candidate_id'], category='setlist' if c['candidate_id'] == 'songs' else 'chat',
                        reason='Song list' if c['candidate_id'] == 'songs' else 'Conversation highlights') for c in contexts],
        songs=songs))


def test_5850_prefers_fourteen_songs_to_sixteen_chat_lines(monkeypatch):
    assert len(parse_setlist(CHAT)) == 16 and len(parse_setlist(SONGS)) == 14
    comments = [comment('chat', CHAT), comment('songs', SONGS)]
    compare = AsyncMock(side_effect=decision_for_5850)
    monkeypatch.setattr(service, 'compare_setlist_candidates', compare)
    result = asyncio.run(service.select_setlist(comments, 12424))
    assert result['candidates'][0]['comment'].id == 'songs'
    assert result['comment'].id == 'songs' and len(result['rows']) == 14
    assert result['rows'][0]['title'] == 'STAND-ALONE'
    assert result['rows'][-1]['original_artist'] == 'スピッツ'
    assert len(result['candidates']) == 2 and compare.await_count == 1


def test_shortlist_is_bounded_unique_and_does_not_require_heading_or_artist():
    comments = [comment(str(i), '00:30 Song') for i in range(6)]
    assert len(service.shortlist(comments + comments)) == 3
    assert len(service.shortlist(comments[:1])) == 1


@pytest.mark.parametrize('state', ['no_songs', 'uncertain'])
def test_semantic_rejection_never_restores_rule_rows(monkeypatch, state):
    decision = SetlistDecision(decision=state, selected_candidate_id=None, reason='Chat or unresolved conflict',
        judgments=[dict(candidate_id='chat', category='chat' if state == 'no_songs' else 'uncertain', reason='Not confirmed songs')], songs=[])
    monkeypatch.setattr(service, 'compare_setlist_candidates', AsyncMock(return_value=ComparisonResult(status='ok', decision=decision)))
    result = asyncio.run(service.select_setlist([comment('chat', CHAT)], 12424))
    assert result['rows'] == [] and result['comment'] is None
    assert result['selection']['status'] == state
    assert result['candidates'][0]['comment'].text == CHAT


@pytest.mark.parametrize('status', ['unconfigured', 'transient_error', 'provider_error', 'invalid_response'])
def test_failed_comparison_never_restores_rule_rows(monkeypatch, status):
    monkeypatch.setattr(service, 'compare_setlist_candidates', AsyncMock(return_value=ComparisonResult(status=status)))
    result = asyncio.run(service.select_setlist([comment('chat', CHAT)], 12424))
    assert not result['rows'] and result['selection']['status'] == status


@pytest.mark.parametrize('mutation', ['id', 'line', 'title', 'artist', 'timestamp', 'duplicate', 'judgments', 'truncated', 'duration'])
def test_source_validation_rejects_entire_invalid_selection(mutation):
    contexts = [service.context_for(comment('songs', SONGS))]
    decision = decision_for_5850(contexts).decision
    duration = 12424
    if mutation == 'id': decision.selected_candidate_id = 'unknown'
    if mutation == 'line': decision.songs[0].line_number = 999
    if mutation == 'title': decision.songs[0].title = 'Invented song'
    if mutation == 'artist': decision.songs[0].original_artist = 'Invented artist'
    if mutation == 'timestamp': decision.songs[0].timestamp = '0:06:31'
    if mutation == 'duplicate': decision.songs.append(decision.songs[0])
    if mutation == 'judgments': decision.judgments = []
    if mutation == 'truncated': contexts[0]['truncated'] = True
    if mutation == 'duration': duration = 390
    with pytest.raises(ValueError):
        service.verified_rows(decision, contexts, duration)


def test_mixed_comment_only_saves_supported_song_and_allows_single_song():
    context = service.context_for(comment('mixed', '00:10 配信開始\n01:00 新曲\n02:00 雑談'))
    decision = SetlistDecision(decision='selected', selected_candidate_id='mixed', reason='One song between chat',
        judgments=[dict(candidate_id='mixed', category='mixed', reason='Songs and chat')],
        songs=[dict(line_number=2, timestamp='01:00', title='新曲', original_artist=None)])
    assert [r['title'] for r in service.verified_rows(decision, [context], 180)] == ['新曲']


def test_context_bound_does_not_cut_mid_line():
    c = comment('long', '00:00 Song\n' + 'x' * 20000)
    context = service.context_for(c)
    assert context['truncated'] and context['lines'] == [dict(line_number=1, text='00:00 Song')]


def test_invalid_source_decision_is_recorded_without_partial_rows(monkeypatch):
    contexts = [service.context_for(comment('songs', SONGS))]
    result = decision_for_5850(contexts)
    result.decision.songs[-1].title = 'Invented song'
    monkeypatch.setattr(service, 'compare_setlist_candidates', AsyncMock(return_value=result))
    selected = asyncio.run(service.select_setlist([comment('songs', SONGS)], 12424))
    assert not selected['rows'] and selected['comment'] is None
    assert selected['selection']['status'] == 'invalid_response'
    assert selected['selection']['validation_error'] == 'Missing source evidence'


def test_existing_job_key_is_unchanged_and_retries_are_distinct():
    req = JobRequest(job_type='youtube_collect', external_account_id=1,
        payload=dict(channel_id='UC' + 'a' * 22, youtube_video_id='abcdefghijk'))
    old_payload = req.parsed_payload().model_dump(exclude={'selection_retry_count'})
    canonical = json.dumps(old_payload, sort_keys=True, separators=(',', ':'), ensure_ascii=True)
    assert req.key() == 'youtube_collect:v1:1:' + hashlib.sha256(canonical.encode()).hexdigest()
    assert req.key() != req.model_copy(update={'payload': {**req.payload, 'selection_retry_count': 1}}).key()


def mock_client(monkeypatch, *, content=None, finish='stop', error=None):
    create = AsyncMock(side_effect=error) if error else AsyncMock(return_value=SimpleNamespace(choices=[
        SimpleNamespace(finish_reason=finish, message=SimpleNamespace(content=content))]))
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    manager = AsyncMock()
    manager.__aenter__.return_value = client
    monkeypatch.setattr(integration, 'AsyncOpenAI', lambda **_: manager)
    monkeypatch.setattr(integration.settings, 'openai_api_key', 'fixture')
    return create


@pytest.mark.parametrize('content,finish', [('not json', 'stop'), ('{}', 'stop'), (None, 'stop'), ('{}', 'length')])
def test_adapter_rejects_malformed_or_truncated_response(monkeypatch, content, finish):
    mock_client(monkeypatch, content=content, finish=finish)
    result = asyncio.run(integration.compare_setlist_candidates([dict(candidate_id='chat', lines=[])]))
    assert result.status == 'invalid_response'


@pytest.mark.parametrize('code,expected', [(401, 'provider_error'), (403, 'provider_error'), (429, 'transient_error'), (500, 'transient_error')])
def test_adapter_classifies_safe_provider_failure_without_secrets(monkeypatch, code, expected):
    response = httpx.Response(code, request=httpx.Request('POST', 'https://example.test'), headers={'Retry-After': '7200'})
    error = APIStatusError('SECRET', response=response, body=None)
    mock_client(monkeypatch, error=error)
    result = asyncio.run(integration.compare_setlist_candidates([]))
    assert result.status == expected and 'SECRET' not in result.model_dump_json()
    assert result.retry_after_seconds == 7200


def test_adapter_transport_and_unconfigured(monkeypatch):
    mock_client(monkeypatch, error=APIConnectionError(request=httpx.Request('POST', 'https://example.test')))
    assert asyncio.run(integration.compare_setlist_candidates([])).status == 'transient_error'
    monkeypatch.setattr(integration.settings, 'openai_api_key', None)
    assert asyncio.run(integration.compare_setlist_candidates([])).status == 'unconfigured'


def test_adapter_structured_success(monkeypatch):
    contexts = [service.context_for(comment('songs', SONGS))]
    expected = decision_for_5850(contexts).decision
    create = mock_client(monkeypatch, content=expected.model_dump_json())
    result = asyncio.run(integration.compare_setlist_candidates(contexts))
    assert result.decision == expected
    assert create.call_args.kwargs['response_format']['json_schema']['strict'] is True
