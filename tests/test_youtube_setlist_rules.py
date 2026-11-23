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


# User-provided source: https://www.youtube.com/watch?v=dSszoaOjZiY
# Original Japanese song information is retained; the supplied translation is
# not substituted for the comment or used to invent title/artist credits.
NUMBERED_TIMELINE = '''タイムスタンプ⏲
00:00:00 本日のサムネ
00:00:20 OP
00:03:25 Start stream！

00:14:03 1. 迷宮バタフライ/ほしな歌唄（CV：水樹奈々）
00:19:10 2. アンインストール/石川智晶
00:26:38 3. 島のうた セイレーン Ver./セイレーン (CV：鈴木みのり) 、人魚 (CV：大木咲絵子、七瀬彩夏)
00:28:07 4. 人マニア/原口沙輔
00:30:29 5. 太陽が昇らない世界/Aimer
00:37:07 6. 独りんぼエンヴィー/電ポルP
00:40:45 7. フィクサー/ぬゆり
00:48:57 8. The Everlasting Guilty Crown/EGOIST
00:54:37 9. 花の唄/Aimer
01:00:51 10. SPARK-AGAIN/Aimer

01:09:58 11. メフィスト/女王蜂
01:13:55 12. Magia/Kalafina
01:19:13 13. 名前のない怪物/EGOIST
01:25:30 14. ないない/ReoNa
01:29:47 15. 拝啓ドッペルゲンガー/kemu

01:34:14 Ending talk

～ハイライト～
00:12:34 今日のセトリは匂わせ
01:34:26 明日はオンラインライブ！
01:47:37 お名前呼び
01:48:52 ここかわいい'''


def test_user_numbered_timeline_extracts_fifteen_songs_without_model(monkeypatch):
    model = AsyncMock(side_effect=AssertionError('Bounded numbered songs must not call the model'))
    monkeypatch.setattr(service, 'compare_setlist_candidates', model)
    comments = [comment('songs', NUMBERED_TIMELINE),
                comment('reaction', '00:23:23 どこ見てんだ？\n00:43:37 体が！沈む！'),
                comment('no_identity', '1曲目\n14:30〜\n\n高評価ポチ。おつやや')]
    result = asyncio.run(service.select_setlist(comments, 7000))
    rows = result['rows']
    assert len(rows) == 15
    assert rows[0]['start_seconds'] == 843
    assert rows[-1]['start_seconds'] == 5387
    assert rows[-1]['title'] == '拝啓ドッペルゲンガー/kemu'
    assert result['selection']['method'] == 'rules'
    assert result['selection']['comparison_calls'] == 0
    for row in rows:
        assert row['title'] in row['raw_line']
        assert row['raw_line'] == NUMBERED_TIMELINE.splitlines()[row['line_number'] - 1]
    model.assert_not_awaited()


@pytest.mark.parametrize('body', [
    NUMBERED_TIMELINE.replace('2. アンインストール', '3. アンインストール'),
    NUMBERED_TIMELINE.replace('00:19:10 2.', '00:13:00 2.'),
    NUMBERED_TIMELINE.replace('00:19:10 2.', '00:14:03 2.'),
    NUMBERED_TIMELINE.replace('00:19:10 2.', '2.'),
    NUMBERED_TIMELINE.replace('00:19:10 2.', '00:18:00 00:19:10 2.'),
    NUMBERED_TIMELINE.replace('00:19:10 2. アンインストール/石川智晶', '00:19:10 cute'),
    NUMBERED_TIMELINE.replace('アンインストール/石川智晶', 'https://example.test/song'),
    NUMBERED_TIMELINE.split('01:34:14 Ending talk')[0],
    'タイムスタンプ\n01:00 1. Greetings\n02:00 2. News\n03:00 Ending talk',
])
def test_incomplete_or_ambiguous_timeline_remains_for_review(body):
    assert not extract_rules(context(body), 7000).rows


def test_numbered_timeline_does_not_override_conflicting_song_candidate():
    full = context(NUMBERED_TIMELINE, 'full')
    conflict = context('00:14:03 01. Different / Artist', 'conflict')
    assert choose_rules([full, conflict], 7000)[0] is None
    truncated = full | {'truncated': True}
    assert not extract_rules(truncated, 7000).rows


def test_explicit_list_with_talk_ordinals_and_ending_does_not_include_mc():
    body = '''♪セトリ
00:00:00 start
00:00:30 opening
00:03:12 ハシタイロ/rionos
00:07:07 おはなし①
00:13:44 偏食/香椎モイミ
00:17:31 おはなし②
00:19:47 プラチナ/坂本真綾
00:43:15 ending
🗣MC
00:07:07 おはなし①（楽しい感じだったので）'''
    result = extract_rules(context(body), 3000)
    assert [r['start_seconds'] for r in result.rows] == [192, 824, 1187]
    assert all('おはなし' not in r['title'] for r in result.rows)


def test_explicit_pipe_ordinals_ranges_and_spaced_dash_keep_verbatim_fields():
    body = '''♬セトリ/Set List♬
00:07:17 ~ 00:12:25 01| Faraway | 苺咲べりぃ(Maisaki Berry)
00:19:09 ~ 00:24:18 02| 明日への手紙(Asuhe no tegami) | 手嶌葵(Tesima aoi)'''
    rows = extract_rules(context(body), 3000).rows
    assert [r['title'] for r in rows] == [
        'Faraway | 苺咲べりぃ(Maisaki Berry)', '明日への手紙(Asuhe no tegami) | 手嶌葵(Tesima aoi)']
    assert all(r['original_artist'] is None for r in rows)
    body = 'セットリスト\n0:08:15 ただ君に晴れ (Just a Sunny Day for You) - ヨルシカ (Yorushika)'
    assert extract_rules(context(body), 3000).rows[0]['title'] == body.split('0:08:15 ')[1]


def test_combined_setlist_and_scenes_requires_complete_song_section_and_divider():
    body = '🪴セトリ＆シーン🪞\n0:15:17 新時代 / Ado\n0:19:12 ピースサイン / 米津玄師\n＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝\n0:20:00 Original Song「blink」MV投稿日'
    rows = extract_rules(context(body), 3000).rows
    assert [r['start_seconds'] for r in rows] == [917, 1152]
    assert all(r['raw_line'] in body for r in rows)
    assert not extract_rules(context(body.replace('＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝', '')), 3000).rows
    assert not extract_rules(context(body.replace('ピースサイン / 米津玄師', 'ここかわいい')), 3000).rows
