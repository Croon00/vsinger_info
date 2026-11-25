"""Pick lyrics candidates out of YouTube descriptions and comments.

Pure functions only. Every result is a review candidate: descriptions and comments mix
lyrics with credits, release notes and prose, so nothing here is published directly.
"""
from __future__ import annotations

import re
import unicodedata

JAPANESE = re.compile(r'[\u2e80-\u2fdf\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]')
HANGUL = re.compile(r'[가-힣]')
LATIN_WORD = re.compile(r'[A-Za-z]{2,}')
# A line that only says "Lyrics" / "歌詞", possibly decorated: ▼Lyrics, [Lyric], 💫Lyrics💫, 歌詞↓
HEADER = re.compile(r'^[^\w]*(lyrics?|歌詞)[^\w]*$', re.I)
SEPARATOR = re.compile(r'^\s*([^\w\s])\1{2,}|^\s*[-─━┈＿_=＝~～‥・…]{3,}')
URL = re.compile(r'https?://|www\.', re.I)
CREDIT = re.compile(r'\S\s*[:：]\s*\S|^[^\w「『(（]*[▼▽▶■◆●★☆◎※#＃【\[]')
LIST_ITEM = re.compile(r'^\s*(\d{1,2}[.:：\s]|[・･]\s*\S)')
MAX_LINE = 60
MIN_LINES = 8


TEXT_CHAR = re.compile(r'[\u2e80-\u2fdf\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff가-힣A-Za-z0-9]')


def _decorative(line: str) -> bool:
    """Separators made of decoration only (𓆝𓆟𓆜, +‥‥‥, ✼••┈┈) or a line led by an emoji/symbol
    such as 💿CD予約 or 🐟YouTube, which in descriptions marks announcements, not lyrics."""
    text = line.strip()
    if not text:
        return False
    if len(text) >= 3 and not TEXT_CHAR.search(text):
        return True
    first = text[0]
    if TEXT_CHAR.match(first):  # CJK radicals such as ⾃ are category So but are text
        return False
    return unicodedata.category(first) == 'So' or 0x13000 <= ord(first) <= 0x1342F


def _stop(line: str) -> bool:
    return bool(URL.search(line) or SEPARATOR.match(line) or _decorative(line))


def _lyric_like(line: str) -> bool:
    text = line.strip()
    return (0 < len(text) <= MAX_LINE and not _stop(text) and not CREDIT.search(text)
            and not LIST_ITEM.match(text) and '#' not in text and '@' not in text
            and bool(JAPANESE.search(text) or HANGUL.search(text) or LATIN_WORD.search(text)))


def _trim(lines: list[str]) -> list[str]:
    while lines and not lines[0].strip():
        lines = lines[1:]
    while lines and not lines[-1].strip():
        lines = lines[:-1]
    # Keep single blank lines between verses, collapse longer gaps.
    out = []
    for line in lines:
        if line.strip() or (out and out[-1].strip()):
            out.append(line.strip())
    return out


def _count(lines: list[str]) -> int:
    return sum(1 for line in lines if line.strip())


def _segments(lines: list[str]):
    """Runs of lines between separators, URLs, marker/credit lines and 3+ blank lines."""
    start, blanks = 0, 0
    for index, line in enumerate(lines + ['---']):
        text = line.strip()
        boundary = index == len(lines) or _stop(text) or (text and not _lyric_like(text) and CREDIT.search(text))
        blanks = blanks + 1 if not text else 0
        if boundary or blanks >= 3:
            yield lines[start:index]
            start = index + 1
            blanks = 0


def _after_header(lines: list[str]) -> list[str] | None:
    for index, line in enumerate(lines):
        if HEADER.match(line.strip()):
            body = []
            for following in lines[index + 1:]:
                if _stop(following.strip()) or (following.strip() and CREDIT.search(following.strip())
                                                  and not _lyric_like(following)):
                    if _count(body):
                        break
                    continue
                body.append(following)
            body = _trim(body)
            if _count(body) >= MIN_LINES:
                return body
    return None


def _best_block(lines: list[str], minimum: int, ratio: float) -> list[str] | None:
    best = None
    for segment in _segments(lines):
        segment = _trim(segment)
        filled = [line for line in segment if line]
        if len(filled) < minimum:
            continue
        if sum(_lyric_like(line) for line in filled) / len(filled) < ratio:
            continue
        if best is None or len(filled) > _count(best):
            best = segment
    return best


def description_lyrics(text: str) -> dict | None:
    """Lyrics block of a video description, or None. ``method`` says how it was found."""
    lines = (text or '').splitlines()
    body = _after_header(lines)
    if body:
        return dict(lyrics='\n'.join(body), method='header', line_count=_count(body))
    body = _best_block(lines, 12, 0.85)
    if body:
        return dict(lyrics='\n'.join(body), method='block', line_count=_count(body))
    return None


def _normal(value: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFKC', value or '').casefold() if c.isalnum())


def comment_lyrics(text: str, title: str) -> dict | None:
    """A comment counts only when it is announced as lyrics (header or song title first),
    so long praise or analysis comments are not mistaken for lyrics."""
    lines = (text or '').splitlines()
    filled = [line.strip() for line in lines if line.strip()]
    if not filled:
        return None
    key = _normal(title)
    head = filled[:3]
    announced = any(HEADER.match(line) or re.search(r'歌詞|lyrics?', line, re.I) and len(line) <= 20 for line in head)
    titled = bool(key) and any(key in _normal(line) and len(_normal(line)) <= len(key) + 12 for line in head)
    if not (announced or titled):
        return None
    def announcement(line):
        text = line.strip()
        return bool(HEADER.match(text) or (re.search(r'歌詞|lyrics?', text, re.I) and len(text) <= 20)
                    or (key and _normal(text) == key))
    # Announcement/title lines are dropped only at the top, never inside the lyrics.
    start = 0
    for index, line in enumerate(lines):
        if line.strip() and line.strip() not in head:
            break
        if announcement(line):
            start = index + 1
    body = [line for line in lines[start:]
            if not URL.search(line) and not (CREDIT.search(line.strip()) and not _lyric_like(line))]
    body = _trim(body)
    filled = [line for line in body if line]
    if len(filled) < 12 or sum(_lyric_like(line) for line in filled) / len(filled) < 0.8:
        return None
    return dict(lyrics='\n'.join(body), method='announced' if announced else 'titled', line_count=len(filled))
