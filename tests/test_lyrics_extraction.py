import pytest
from pydantic import ValidationError

from app.schemas.lyrics_review import LyricsEntry
from app.services.lyrics_extraction import comment_lyrics, description_lyrics

# Synthetic lines only; no real lyrics in fixtures.
VERSE = [f'テストの言葉 {i} 行目です' for i in range(1, 15)]


def test_header_block_stops_at_announcements():
    text = '\n'.join(['「テスト曲」', 'Vocal : 歌い手', 'Music : 作曲者', '────────', 'Lyrics',
                      *VERSE[:7], '', *VERSE[7:], '', '▼Release', 'https://example.com/a', '#テスト'])
    found = description_lyrics(text)
    assert found['method'] == 'header'
    assert found['line_count'] == 14
    assert found['lyrics'].splitlines()[0] == VERSE[0] and found['lyrics'].splitlines()[-1] == VERSE[-1]
    assert '' in found['lyrics'].splitlines()  # verse break kept


def test_unannounced_block_between_decorations():
    text = '\n'.join(['新曲です！', '𓆝𓆟𓆜𓆞𓆝𓆟𓆜', *VERSE, '𓆝𓆟𓆜𓆞𓆝𓆟𓆜', '💿CD予約', 'https://example.com'])
    found = description_lyrics(text)
    assert found['method'] == 'block' and found['line_count'] == 14


def test_cjk_radicals_are_text_not_decoration():
    text = '\n'.join(['Lyrics', *VERSE[:6], '⾃分次第だから', *VERSE[6:]])
    assert description_lyrics(text)['line_count'] == 15


def test_credits_tracklists_and_links_are_not_lyrics():
    text = '\n'.join(['Vocal : 歌い手', 'Lyrics : 作詞者', '【収録楽曲】', *[f'{i:02} 曲名{i}' for i in range(1, 16)],
                      '・CDアルバム', '・ポストカード', 'https://example.com'])
    assert description_lyrics(text) is None


def test_comment_needs_lyrics_announcement_or_title():
    praise = '\n'.join(f'この曲本当に最高 {i}' for i in range(20))
    assert comment_lyrics(praise, 'テスト曲') is None
    assert comment_lyrics('歌詞↓\n' + '\n'.join(VERSE), 'テスト曲')['method'] == 'announced'
    titled = comment_lyrics('テスト曲\n作詞：誰か\n' + '\n'.join(VERSE), 'テスト曲')
    assert titled['method'] == 'titled' and titled['line_count'] == 14


def test_review_entry_requires_lyrics_when_approved():
    base = dict(key='recording:1', recording_ids=[1, 2], title='テスト曲')
    assert LyricsEntry(**base).approved is False
    with pytest.raises(ValidationError):
        LyricsEntry(**base, approved=True)
    with pytest.raises(ValidationError):
        LyricsEntry(**{**base, 'recording_ids': [1, 1]})
    assert LyricsEntry(**base, approved=True, original_lyrics='a').approved
