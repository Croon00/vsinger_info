"""Rank time-index comments, compare their meaning, and verify source evidence."""
from __future__ import annotations

import re

from app.integrations.youtube_catalog import STAMP, Comment
from app.integrations.youtube_setlist import ComparisonResult, compare_setlist_candidates

POLICY = 'setlist-comparison-2'
MAX_CONTEXT_CHARS = 20000


def shortlist(comments: list[Comment]) -> list[dict]:
    candidates = []
    seen = set()
    for comment in comments:
        if comment.id in seen:
            continue
        seen.add(comment.id)
        lines = [line for line in comment.text.splitlines() if STAMP.search(line)]
        if not lines:
            continue
        heading = bool(re.search(r'set\s*list|セットリスト|セトリ|세트리스트', comment.text, re.I))
        pairs = sum(bool(re.search(r'\S\s+[/／|｜—]\s+\S', line)) for line in lines)
        numbered = sum(bool(re.search(r'(?:\d+[.．、)]|[＃#]\d+|\d+曲目)', line)) for line in lines)
        # Length contributes at most one point; semantic structure carries more weight.
        score = 8 * heading + 4 * pairs / len(lines) + 2 * numbered / len(lines) + min(len(lines), 20) / 20
        candidates.append(dict(comment=comment, score=score, signals=dict(
            heading=heading, artist_pair_lines=pairs, numbered_lines=numbered, timestamp_lines=len(lines))))
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
    rows, seen = [], set()
    for song in decision.songs:
        line = lines.get(song.line_number, '')
        match = STAMP.search(line)
        title = song.title.strip()
        artist = song.original_artist.strip() if song.original_artist else None
        if (not match or match.group(1) != song.timestamp or not title or
                title not in line or (artist and artist not in line)):
            raise ValueError('Missing source evidence')
        seconds = sum(int(p) * 60 ** i for i, p in enumerate(reversed(song.timestamp.split(':'))))
        if seconds in seen or (duration is not None and seconds >= duration):
            raise ValueError('Invalid song time')
        seen.add(seconds)
        rows.append(dict(timestamp=song.timestamp, start_seconds=seconds, title=title,
                         original_artist=artist, raw_line=line, line_number=song.line_number))
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
            validation_error = str(exc)  # Fixed local messages; never provider exception text.
    for rank, (candidate, context) in enumerate(zip(candidates, contexts), 1):
        candidate.update(rank=rank, context_truncated=context['truncated'])
    return dict(candidates=candidates, comment=next((c['comment'] for c in candidates if c['comment'].id == selected), None),
                rows=rows, selection=dict(policy=POLICY, status=status,
                    considered_count=len(comments), retained_count=len(candidates),
                    comparison_calls=0 if result.status == 'unconfigured' else 1,
                    validation_error=validation_error,
                    retry_after_seconds=result.retry_after_seconds,
                    model_result=result.decision.model_dump() if result.decision else None))
