"""Report-derived formats and adversarial edges; no model or remote database."""
import asyncio
from unittest.mock import AsyncMock

import pytest

from app.integrations.youtube_setlist import ComparisonResult
from app.services import youtube_setlist as service
from app.services.youtube_setlist_rules import extract_rules, choose_rules
from test_youtube_setlist_selection import comment, CHAT


def context(body, identifier='source'):
    return service.context_for(comment(identifier, body))


@pytest.mark.parametrize('body,title,artist,seconds', [
    ('SetList\n12:24 初恋 / 村下孝蔵', '初恋 / 村下孝蔵', None, 744),
    ('SetList\n01. 00:12:56 拝啓、少年よ / Hump Back', '拝啓、少年よ / Hump Back', None, 776),
    ('SetList\n0:05:55：01. 少年と魔法のロボット // 40mP', '少年と魔法のロボット // 40mP', None, 355),
    ('SetList\n1 . メアの教育 / コウ 【3:42～6:56】', 'メアの教育 / コウ', None, 222),
    ('SetList\n『１曲目 / 1st Song 』3:09~7:14\n├ お気に召すまま / Eve\n└ (Oki ni Mesumama)', 'お気に召すまま / Eve', None, 189),
    ('SetList\n01. いーあるふぁんくらぶ／みきとP\n┗ 05:38 ~ 09:30', 'いーあるふぁんくらぶ／みきとP', None, 338),
    ('SetList\n0:20:31 🎤「怪獣」サカナクション', '怪獣', 'サカナクション', 1231),
    ('SetList\n０１：００ ～ ０２：００\n┗ Song / Artist', 'Song / Artist', None, 60),
    ('SetList\n90:00 「Song」Artist', 'Song', 'Artist', 5400),
    ('SetList\n01 3:54 8.32 / *Luna', '8.32 / *Luna', None, 234),
    ('SetList\n01. 03:54 1991', '1991', None, 234),
    ('SetList\n03:54 01. 55', '55', None, 234),
    ('SetList\n03:54 01. √64', '√64', None, 234),
    ('SetList\n03:54 ハロ/ハワユ / ナノウ', 'ハロ/ハワユ / ナノウ', None, 234),
    ('SetList\n03:54 START:DASH!! / μ’s', 'START:DASH!! / μ’s', None, 234),
    ('SetList\n03:54 Week End / indigo la end', 'Week End / indigo la end', None, 234),
    ('SetList\n03:54 REVIVER / MY FIRST STORY', 'REVIVER / MY FIRST STORY', None, 234),
    ('SetList\n曲名 / 歌手\n03:54 Song / Artist', 'Song', 'Artist', 234),
    ('SetList\nArtist / Title\n03:54 Artist / Song', 'Song', 'Artist', 234),
    ('SetList\n03:54 「Song」Artist（take2）', 'Song', 'Artist', 234),
    ('SetList\n1曲目\n15:10 花は桜君は美し （いきものがかり さん）', '花は桜君は美し （いきものがかり さん）', None, 910),
    ('SetList\n[01:00] Song (version) / Artist (Name)', 'Song (version) / Artist (Name)', None, 60),
    ('SetList\n01. 01:00 (Song)', '(Song)', None, 60),
    ('SetList\n01:00 -ERROR / niki', '-ERROR / niki', None, 60),
    ('SetList\n01. 01:00 Song:', 'Song:', None, 60),
])
def test_report_formats_preserve_exact_source_fields(body, title, artist, seconds):
    parsed = extract_rules(context(body), 10000)
    assert not parsed.blocks_selection, parsed.reason
    assert len(parsed.rows) == 1
    row = parsed.rows[0]
    assert (row['title'], row['original_artist'], row['start_seconds']) == (title, artist, seconds)
    assert row['raw_line'] == '\n'.join(body.splitlines()[row['line_number']-1:row['end_line_number']])
    assert title in row['raw_line']
    assert not artist or artist in row['raw_line']


@pytest.mark.parametrize('body', [
    CHAT,
    'Setlistについて話す\n00:10 Cute / Funny',
    'SetList\n00:10 so cute',
    'SetList\n00:10 https://youtu.be/abcdefghijk',
    'SetList\n１：6:49：ウィーアー！ / Artist',
    'SetList\n01:00 AM2：00 / Artist',
    'SetList\n01:00 A / Artist 02:00 B / Artist',
    'SetList\n02:00~01:00 Song / Artist',
    'SetList\n0:3603 Song / Artist',
    'SetList\n01:00 Song /',
    'SetList\n01:00 Song / Artist\n01:00 Another / Artist',
    'SetList\n01:00 Song / Artist\n02:00 Unexplained text',
    'SetList\nSong / Artist\n01:00\nDifferent / Artist',
    'SetList\n曲名 / 歌手\n01:00 ハロ/ハワユ / ナノウ',
    'SetList\n01:00 Song / Artist\n04. Another / Artist',
    'SetList\n01:00 Song / Artist\nAnother / Artist',
])
def test_ambiguous_or_non_song_input_is_not_automatically_published(body):
    assert not extract_rules(context(body), 10000).rows


def test_chat_boundaries_repeats_and_unlabelled_artist_order():
    body = 'SetList\n00:01 配信開始\n01:00 Song / Artist\n02:00 MC\n03:00 Song / Artist\n【アフタートーク】\n04:00 Cute / Funny'
    rows = extract_rules(context(body), 1000).rows
    assert [row['start_seconds'] for row in rows] == [60, 180]
    assert all(row['original_artist'] is None for row in rows)


@pytest.mark.parametrize('heading', ['🌙🎼セトリ🌙🎼', '～ セトリ / Song List ～', 'Set list（ネタバレ注意）',
                                    '⟡ SETLIST ⟡', 'セトリ代理投稿', '🎵【歌枠セットリスト】🎵', 'SETLIST ─── 22 Songs♪'])
def test_only_standalone_decorated_headings_activate_rules(heading):
    assert len(extract_rules(context(heading + '\n01:00 Song / Artist'), 300).rows) == 1
    assert not extract_rules(context('00:10 ' + heading + 'について話す\n01:00 Song / Artist'), 300).rows


def test_numbered_start_with_commentary_is_not_a_song():
    body = 'SetList\n00. 0:00:43 配信開始 （L4TSやAWA国際交流歌合戦の振り返りなどなど）\n01. 01:00 ~ Song / Artist'
    rows = extract_rules(context(body), 1000).rows
    assert len(rows) == 1 and rows[0]['title'] == 'Song / Artist'


def test_standalone_mc_does_not_drop_remaining_songs_and_new_section_resets_legend():
    body = 'SetList 曲名 / 歌手\n01:00 First / Artist\nMC\n02:00 Second / Artist\nSetList\n03:00 Artist / Third'
    rows = extract_rules(context(body), 1000).rows
    assert [(r['title'], r['original_artist']) for r in rows] == [('First', 'Artist'), ('Second', 'Artist'), ('Artist / Third', None)]


def test_duration_truncation_and_no_crossing_timestamp():
    assert not extract_rules(context('SetList\n01:00 Song / Artist'), 60).rows
    assert not extract_rules(context('SetList\n01:00\n02:00 Song / Artist'), 300).rows
    truncated = context('SetList\n01:00 Song / Artist') | {'truncated': True}
    assert not extract_rules(truncated, 300).rows
    assert not extract_rules(context('SetList\n1曲目\n01:00\n\n\nSong / Artist'), 300).rows


def test_multiple_candidates_only_choose_exact_supported_superset():
    full = context('SetList\n01:00 A / Artist\n02:00 B / Artist', 'full')
    partial = context('SetList\n01:00 A / Artist', 'partial')
    assert choose_rules([partial, full, context('00:10 配信開始', 'chat')], 20000)[0] == 1
    # Quotes in an unheaded reaction comment can also be song titles. Rules
    # cannot resolve that meaning, so preserve the existing model comparison.
    assert choose_rules([partial, full, context(CHAT, 'chat')], 20000)[0] is None
    conflict = context('SetList\n01:00 Different / Artist', 'conflict')
    assert choose_rules([full, conflict], 20000)[0] is None
    unheaded = context('01:00 Different / Artist', 'unheaded')
    assert choose_rules([full, unheaded], 20000)[0] is None
    for body in ('01:00\nDifferent / Artist', '01:00 01. Different', '01:00 「Different」Artist'):
        assert choose_rules([full, context(body)], 20000)[0] is None


def test_rules_bypass_model_failure_and_preserve_comment(monkeypatch):
    model = AsyncMock(side_effect=AssertionError('Explicit list must not call the model'))
    monkeypatch.setattr(service, 'compare_setlist_candidates', model)
    source = comment('source', 'SetList\n01:00 Song / Artist')
    result = asyncio.run(service.select_setlist([source], 300))
    assert result['comment'] is source and len(result['rows']) == 1
    assert result['selection']['method'] == 'rules'
    assert result['selection']['comparison_calls'] == 0
    assert result['selection']['model_result'] is None
    model.assert_not_awaited()


def test_rule_ambiguity_keeps_existing_model_failure_behavior(monkeypatch):
    model = AsyncMock(return_value=ComparisonResult(status='transient_error'))
    monkeypatch.setattr(service, 'compare_setlist_candidates', model)
    result = asyncio.run(service.select_setlist([comment('s', 'SetList\n01:00 maybe singing')], 300))
    assert result['rows'] == [] and result['selection']['status'] == 'transient_error'
    assert result['selection']['method'] == 'model'
    model.assert_awaited_once()


def test_provider_retains_explicit_time_ordinal_boundary():
    import httpx
    from app.integrations.youtube_catalog import YouTubeClient
    body = 'SetList\n0:05:55：01. Song // Artist'
    data = {'items': [{'snippet': {'topLevelComment': {'id': 'source', 'snippet': {'textOriginal': body}}}}]}
    provider = YouTubeClient('fixture', transport=httpx.MockTransport(lambda _: httpx.Response(200, json=data)), interval=0)
    comments, _ = asyncio.run(provider.comments('abcdefghijk'))
    assert len(comments) == 1
    assert service.shortlist(comments)[0]['signals']['timestamp_lines'] == 1


def test_song_list_heading_is_ranked_before_unstructured_mentions():
    comments = [comment(str(i), 'Setlistについて話す\n00:10 cute') for i in range(3)]
    comments.append(comment('songs', 'Song List\n01:00 Song / Artist'))
    assert service.shortlist(comments)[0]['comment'].id == 'songs'
