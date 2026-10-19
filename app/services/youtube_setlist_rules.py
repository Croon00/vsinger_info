"""Bounded extraction from explicit setlist sections, without semantic guesses.

Unlabelled ``A / B`` remains the original song-information text with no artist
assignment. A slash alone cannot distinguish a title, romanization or artist.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re
import unicodedata

from app.integrations.youtube_catalog import find_timestamps, timestamp_seconds

RULE_POLICY = 'setlist-rules-1'
DECOR = ' \t\u3000┗└├│─━═•・🎵🎶🎤♫♪✨✦★☆▸▶🎀🐶🤍❇️'
HEADING = re.compile(r'(?:set\s*list|song\s*list|歌枠セットリスト|セットリスト|セトリ|세트리스트|歌唱タイムスタンプ)', re.I)
FIELD_ORDER = {
    'title_first': re.compile(r'(?:曲名|曲|song(?: title)?|title|곡명|제목)\s*[/／|｜]\s*(?:歌手|アーティスト|artist|가수|원곡자)', re.I),
    'artist_first': re.compile(r'(?:歌手|アーティスト|artist|가수|원곡자)\s*[/／|｜]\s*(?:曲名|曲|song(?: title)?|title|곡명|제목)', re.I),
}
ORDINAL = re.compile(r'^(?:(?:[＃#]\s*[0-9０-９]+|[0-9０-９]+\s*曲目)\s*|'
                     r'(?:[0-9０-９]{1,3}\s*[.．、)]\s+|[①-⑳]\s*))')
SONG_NUMBER = re.compile(r'[0-9０-９]+\s*曲目(?:\s*[/／]\s*[0-9０-９]+(?:st|nd|rd|th)\s+song)?', re.I)
LABEL_NOTE = r'(?:\s*(?:[（(【\[].*[）)】\]]|[:：]\s+.+))?'
NON_SONG = re.compile(r'(?:start|end|opening|closing|intro|outro|mc|talk|chat|'
                      r'配信開始|配信終了|開始|終了|挨拶|雑談|告知|重大告知|アフタートーク|'
                      r'시작|종료|인사|잡담|공지)' + LABEL_NOTE, re.I)
SECTION_END = re.compile(r'(?:end|closing|outro|配信終了|終了|アフタートーク|종료)' + LABEL_NOTE, re.I)
PAIR = re.compile(r'\S\s*[/／|｜]\s*\S')
TIME_LIKE = re.compile(r'[0-9０-９]+\s*[:：]\s*[0-9０-９]+')
RANGE = re.compile(r'\s*[~〜～–—−-]\s*')
ANNOTATION = re.compile(r'\s*[（(【\[]\s*(?:take\s*\d+|key\s*[+-]?\d+|[+-]\d+|初|初披露|NEW)\s*[）)】\]]\s*$', re.I)


@dataclass
class RuleCandidate:
    rows: list[dict] = field(default_factory=list)
    reason: str = 'no_explicit_setlist'
    blocks_selection: bool = False


def _heading(line: str) -> bool:
    def strip_decoration(value):
        # Header only: never apply generic punctuation stripping to song text.
        while value and unicodedata.category(value[0])[0] in 'PSZM':
            value = value[1:]
        while value and unicodedata.category(value[-1])[0] in 'PSZM':
            value = value[:-1]
        return value

    value = strip_decoration(line)
    match = HEADING.match(value)
    if not match:
        return False
    tail = strip_decoration(value[match.end():])
    tail = strip_decoration(HEADING.sub('', tail))
    if tail in ('代理投稿', 'ネタバレ注意', 'タイムスタンプ'):
        return True
    return not tail or bool(re.fullmatch(r'[0-9０-９]+\s*(?:songs?|曲)', tail, re.I)) or any(
        pattern.fullmatch(tail) for pattern in FIELD_ORDER.values())


def _clean(value: str, *, number: bool = True) -> tuple[str, bool]:
    value = value.strip(DECOR)
    value = re.sub(r'^[:：](?=[0-9０-９]{1,3}[.．、)]\s+)', '', value)
    numbered = False
    if number:
        match = ORDINAL.match(value)
        if match:
            numbered = True
            value = value[match.end():].strip(DECOR)
    value = value.strip()
    while ANNOTATION.search(value):
        value = ANNOTATION.sub('', value).rstrip()
    return value, numbered


def _label(value: str, *, end_only: bool = False) -> bool:
    value = value.strip(DECOR)
    wrappers = {'【': '】', '[': ']', '(': ')', '（': '）', '<': '>', '《': '》'}
    while len(value) > 1 and wrappers.get(value[0]) == value[-1]:
        value = value[1:-1].strip(DECOR)
    return bool((SECTION_END if end_only else NON_SONG).fullmatch(value))


def _info(value: str, order: str | None, numbered: bool) -> tuple[str, str | None] | None:
    value = value.strip(DECOR)
    if not value or len(value) > 300 or 'http://' in value or 'https://' in value:
        return None
    quoted = re.fullmatch(r'[「『]([^」』]+)[」』]\s*(?:[/／]\s*)?(.*)', value)
    if quoted:
        title, artist = quoted.groups()
        return title, artist.strip() or None
    if not (numbered or PAIR.search(value)):
        return None
    if value.endswith(('/', '／', '|', '｜')):
        return None
    if order:
        # Only an explicit field-order legend permits assigning an artist.
        # Multiple separators stay unresolved (including title-internal slashes).
        pieces = re.split(r'\s*(?://|[/／|｜])\s*', value)
        if len(pieces) != 2 or not all(pieces):
            return None
        return (pieces[0], pieces[1]) if order == 'title_first' else (pieces[1], pieces[0])
    return value, None


def extract_rules(context: dict, duration: int | None) -> RuleCandidate:
    """Either accept a whole bounded section or leave it for model/review.

    Known non-song markers are skipped. Ambiguous timestamp entries invalidate
    the candidate instead of silently publishing an incomplete interpretation.
    """
    lines = [line['text'] for line in context['lines']]
    explicit = any(_heading(line) for line in lines)
    if context['truncated']:
        return RuleCandidate(reason='truncated', blocks_selection=True)
    if not explicit:
        # An unheaded competing list may split time/title across lines or put
        # its ordinal after the time. Do not dismiss it as chat in either case.
        structured = any(PAIR.search(line) or ORDINAL.match(line.strip(DECOR)) or
                         re.search(r'[「『][^」』]+[」』]', line) or
                         any(_clean(line[stamp.end():])[1] for stamp in find_timestamps(line))
                         for line in lines)
        return RuleCandidate(reason='no_explicit_setlist', blocks_selection=structured)
    active, order = False, None
    used, seen, rows, untimed_songs = set(), set(), [], set()

    def ambiguous(reason):
        return RuleCandidate(reason=reason, blocks_selection=True)

    for i, line in enumerate(lines):
        if _heading(line):
            active, order = True, None
            for name, pattern in FIELD_ORDER.items():
                if pattern.search(line):
                    order = name
            continue
        if not active or i in used:
            continue
        legend = next((name for name, pattern in FIELD_ORDER.items() if pattern.fullmatch(line.strip())), None)
        if legend:
            order = legend
            continue
        if _label(line):
            # MC can separate songs. Only an explicit closing section ends it.
            active = not _label(line, end_only=True)
            continue
        stamps = find_timestamps(line)
        if not stamps:
            if TIME_LIKE.search(line):
                return ambiguous('malformed_or_non_video_time')
            cleaned, numbered = _clean(line)
            if numbered or _info(cleaned, order, False):
                untimed_songs.add(i)
            continue
        if len(stamps) > 2 or (len(stamps) == 2 and not RANGE.fullmatch(line[stamps[0].end():stamps[1].start()])):
            return ambiguous('multiple_timestamps')
        stamp = stamps[0].group(1)
        # Mixed colon styles can be an ordinal followed by a time (１：6:49).
        if ':' in stamp and '：' in stamp:
            return ambiguous('ambiguous_colon_boundary')
        seconds = timestamp_seconds(stamp)
        if (duration is not None and seconds >= duration) or seconds in seen:
            return ambiguous('invalid_or_duplicate_start')
        if len(stamps) == 2 and timestamp_seconds(stamps[1].group(1)) <= seconds:
            return ambiguous('invalid_range')
        left = line[:stamps[0].start()].strip(DECOR)
        right = line[stamps[-1].end():].strip()
        # Remove brackets around the timestamp only; title parentheses survive.
        wrappers = {'【': '】', '[': ']', '(': ')', '（': '）'}
        if left and right and wrappers.get(left[-1]) == right[0]:
            left, right = left[:-1].rstrip(), right[1:].lstrip()
        # A plain number before a time is an ordinal; never strip a second
        # number from the title (e.g. 01 3:54 8.32 / *Luna).
        prefix_number = bool(re.fullmatch(r'[0-9０-９]+\s*[.．、):：]?', left))
        if SONG_NUMBER.fullmatch(left.strip('『』「」 ')) or prefix_number:
            left, prefix_number = '', True
        left, left_number = _clean(left)
        right, right_number = _clean(re.sub(r'^[~〜～–—−-]\s+', '', right), number=not prefix_number)
        numbered = prefix_number or left_number or right_number
        previous_number = (i > 0 and i - 1 not in used and
                           bool(SONG_NUMBER.fullmatch(lines[i - 1].strip(DECOR + '『』「」 '))))
        numbered = numbered or previous_number
        if left and right:
            return ambiguous('text_on_both_sides')
        content = left or right
        if _label(content):
            continue
        start, end = i - 1 if previous_number else i, i
        if not content:
            neighbours = []
            for direction in (-1, 1):
                for offset in range(1, 4):
                    j = i + direction * offset
                    if not 0 <= j < len(lines) or j in used:
                        break
                    other = lines[j]
                    if not other.strip():
                        continue
                    if find_timestamps(other) or _heading(other) or _label(other):
                        break
                    cleaned, has_number = _clean(other)
                    info = _info(cleaned, order, numbered or has_number)
                    if info:
                        neighbours.append((j, cleaned, has_number))
                    break
            if len(neighbours) != 1:
                return ambiguous('ambiguous_adjacent_song')
            j, content, has_number = neighbours[0]
            numbered = numbered or has_number
            start, end = min(start, j), max(i, j)
        info = _info(content, order, numbered)
        if info is None:
            return ambiguous('unstructured_song_text')
        title, artist = info
        if end - start >= 4:
            return ambiguous('evidence_span_too_long')
        if any(j in used for j in range(start, end + 1)):
            return ambiguous('overlapping_evidence')
        # Fields must remain exact source substrings after decoration removal.
        span = lines[start:end + 1]
        if not any(title in part for part in span) or (artist and not any(artist in part for part in span)):
            return ambiguous('missing_source_evidence')
        rows.append(dict(timestamp=stamp, start_seconds=seconds, title=title, original_artist=artist,
                         raw_line='\n'.join(span), line_number=start + 1, end_line_number=end + 1))
        used.update(range(start, end + 1))
        seen.add(seconds)
        if len(rows) > 200:
            return ambiguous('too_many_songs')
    if untimed_songs - used:
        return ambiguous('song_without_time')
    if not rows:
        return ambiguous('no_supported_songs')
    return RuleCandidate(rows=sorted(rows, key=lambda row: row['start_seconds']), reason='explicit_setlist')


def choose_rules(contexts: list[dict], duration: int | None) -> tuple[int | None, list[RuleCandidate]]:
    parsed = [extract_rules(context, duration) for context in contexts]
    if any(candidate.blocks_selection for candidate in parsed):
        return None, parsed
    signatures = [{(r['start_seconds'], r['title'], r['original_artist']) for r in candidate.rows} for candidate in parsed]
    for i in sorted(range(len(parsed)), key=lambda i: -len(parsed[i].rows)):
        if signatures[i] and all(other <= signatures[i] for other in signatures):
            return i, parsed
    return None, parsed
