"""Rank comments and validate bounded, explicit source spans for each song."""
from __future__ import annotations

import re

from app.integrations.youtube_catalog import STAMP, Comment, timestamp_seconds
from app.integrations.youtube_setlist import ComparisonResult, compare_setlist_candidates

POLICY = 'setlist-comparison-3'
MAX_CONTEXT_CHARS = 20000
MAX_EVIDENCE_LINES = 4
HEADING = re.compile(r'set\s*list|セットリスト|セトリ|세트리스트|歌唱タイムスタンプ', re.I)
PAIR = re.compile(r'\S\s*[/／|｜—]\s*\S')
NUMBERED = re.compile(r'^\s*(?:M\.?\s*)?(?:[＃#]\s*)?[0-9０-９]+\s*[.．、)曲]')


def shortlist(comments: list[Comment]) -> list[dict]:
    candidates, seen = [], set()
    for comment in comments:
        if comment.id in seen:
            continue
        seen.add(comment.id)
        lines = comment.text.splitlines()
        indices = [i for i, line in enumerate(lines) if STAMP.search(line)]
        if not indices:
            continue
        heading = bool(HEADING.search(comment.text))
        # Include a short continuation, stopping before the next timestamp.
        # These are ranking signals only, never automatic song evidence.
        pairs = numbered = 0
        for i in indices:
            block = [lines[i]]
            for line in lines[i + 1:i + MAX_EVIDENCE_LINES]:
                if STAMP.search(line) or not line.strip():
                    break
                block.append(line)
            pairs += any(PAIR.search(re.sub(r'https?://\S+', '', line)) for line in block)
            numbered += bool(NUMBERED.search(lines[i]) or re.search(r'[＃#]\s*[0-9０-９]+', lines[i]))
        score = 8 * heading + 4 * pairs / len(indices) + 2 * numbered / len(indices) + min(len(indices), 20) / 20
        candidates.append(dict(comment=comment, score=score, signals=dict(
            heading=heading, artist_pair_lines=pairs, numbered_lines=numbered, timestamp_lines=len(indices))))
    return sorted(candidates, key=lambda c: (-c['score'], c['comment'].id))[:3]


def context_for(comment: Comment) -> dict:
    lines, size = [], 0
    for number, line in enumerate(comment.text.splitlines(), 1):
        if size + len(line) + 1 > MAX_CONTEXT_CHARS:
            break
        lines.append(dict(line_number=number, text=line))
        size += len(line) + 1
    return dict(candidate_id=comment.id, lines=lines,
                truncated=len(lines) != len(comment.text.splitlines()))


def verified_rows(decision, contexts: list[dict], duration: int | None) -> list[dict]:
    ids = {c['candidate_id'] for c in contexts}
    judgments = {j.candidate_id: j for j in decision.judgments}
    if set(judgments) != ids or len(judgments) != len(decision.judgments):
        raise ValueError('Invalid candidate judgments')
    if decision.decision != 'selected':
        if decision.selected_candidate_id is not None or decision.songs:
            raise ValueError('Unexpected selection')
        if decision.decision == 'no_songs' and any(j.category != 'chat' for j in decision.judgments):
            raise ValueError('Inconsistent no-songs decision')
        return []
    selected = decision.selected_candidate_id
    if selected not in ids or judgments[selected].category not in ('setlist', 'mixed') or not decision.songs:
        raise ValueError('Invalid selection')
    context = next(c for c in contexts if c['candidate_id'] == selected)
    if context['truncated']:
        raise ValueError('Selected context was truncated')
    lines = {line['line_number']: line['text'] for line in context['lines']}
    rows, seen, used_lines = [], set(), set()
    for song in decision.songs:
        start = song.line_number
        end = song.end_line_number if song.end_line_number is not None else start
        if not start <= end < start + MAX_EVIDENCE_LINES or any(n not in lines for n in range(start, end + 1)):
            raise ValueError('Invalid evidence span')
        span = [lines[n] for n in range(start, end + 1)]
        stamps = [(i, list(STAMP.finditer(line))) for i, line in enumerate(span) if STAMP.search(line)]
        # One timestamp line, with an optional end time. Never join adjacent songs.
        if len(stamps) != 1 or not 1 <= len(stamps[0][1]) <= 2:
            raise ValueError('Ambiguous evidence timestamps')
        index, matches = stamps[0]
        match = matches[0]
        if len(matches) == 2:
            separator = span[index][match.end():matches[1].start()]
            if not re.fullmatch(r'\s*[~〜～–—−-]\s*', separator):
                raise ValueError('Ambiguous evidence timestamps')
            if timestamp_seconds(matches[1].group(1)) <= timestamp_seconds(match.group(1)):
                raise ValueError('Invalid time range')
        title = song.title.strip()
        artist = song.original_artist.strip() if song.original_artist else None
        if (timestamp_seconds(match.group(1)) != timestamp_seconds(song.timestamp) or not title or
                not any(title in line for line in span) or (artist and not any(artist in line for line in span))):
            raise ValueError('Missing source evidence')
        seconds = timestamp_seconds(match.group(1))
        if seconds in seen or (duration is not None and seconds >= duration):
            raise ValueError('Invalid song time')
        evidence_lines = set(range(start, end + 1))
        if evidence_lines & used_lines:
            raise ValueError('Overlapping song evidence')
        seen.add(seconds)
        used_lines.update(evidence_lines)
        rows.append(dict(timestamp=match.group(1), start_seconds=seconds, title=title,
                         original_artist=artist, raw_line='\n'.join(span), line_number=start, end_line_number=end))
    return sorted(rows, key=lambda r: r['start_seconds'])


async def select_setlist(comments: list[Comment], duration: int | None) -> dict:
    candidates = shortlist(comments)
    contexts = [context_for(c['comment']) for c in candidates]
    result = await compare_setlist_candidates(contexts) if contexts else ComparisonResult(status='unconfigured')
    rows, selected, validation_error = [], None, None
    status = ('no_songs' if not contexts else
              'invalid_response' if result.status == 'ok' and result.decision is None else result.status)
    if result.status == 'ok' and result.decision is not None:
        try:
            rows = verified_rows(result.decision, contexts, duration)
            status = result.decision.decision
            selected = result.decision.selected_candidate_id
        except ValueError as exc:
            status = 'invalid_response'
            validation_error = str(exc)
    for rank, (candidate, context) in enumerate(zip(candidates, contexts), 1):
        candidate.update(rank=rank, context_truncated=context['truncated'])
    return dict(candidates=candidates, comment=next((c['comment'] for c in candidates if c['comment'].id == selected), None),
                rows=rows, selection=dict(policy=POLICY, status=status,
                    considered_count=len(comments), retained_count=len(candidates),
                    comparison_calls=0 if result.status == 'unconfigured' else 1,
                    validation_error=validation_error,
                    retry_after_seconds=result.retry_after_seconds,
                    model_result=result.decision.model_dump() if result.decision else None))
