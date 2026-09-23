"""Independent YouTube workflow. No X, legacy SQL, or management UI dependencies."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse
import re

from app.core.config import settings
from app.integrations.youtube_catalog import YouTubeClient, YouTubeFailure, parse_setlist, purpose
from app.integrations.ai_extractor import extract_youtube_setlist
from app.repositories import youtube_collection as repository
from app.schemas.worker_jobs import JobRequest


def client():
    return YouTubeClient(settings.youtube_api_key)


def _translate(exc):
    from app.services.music_jobs import RetryableJobError, PermanentJobError
    if exc.retry:
        raise RetryableJobError(retry_after=exc.retry_after) from None
    raise PermanentJobError(exc.reason) from None


async def collect_poll(job, payload):
    from app.services.music_jobs import db_call, PermanentJobError
    state = await db_call(repository.poll_state, job.external_account_id)
    captured = datetime.now(UTC)
    provider = client()
    try:
        if payload.backfill_video_ids:
            videos = await provider.videos(list(dict.fromkeys(payload.backfill_video_ids)))
            playlist, truncated = None, False
            if {v.id for v in videos} != set(payload.backfill_video_ids):
                raise PermanentJobError('Backfill contains unavailable videos; submit available IDs separately')
        else:
            playlist, videos, truncated = await provider.recent(payload.channel_id)
            # A long scheduled/live video can fall outside the newest uploads
            # window. Remember its ID until a later poll observes completion.
            pending = state['provider_state'].get('youtube_pending_video_ids', [])
            known = {v.id for v in videos}
            missing = [v for v in pending if isinstance(v, str) and re.fullmatch(r'[A-Za-z0-9_-]{11}', v) and v not in known][:200]
            if missing:
                videos.extend(await provider.videos(missing))
    except YouTubeFailure as exc:
        _translate(exc)
    if payload.backfill_video_ids and any(v.channel_id != payload.channel_id for v in videos):
        raise PermanentJobError('Channel mismatch')
    # An uploads playlist can include a video whose current owner is another
    # channel. Ignore that entry while continuing to poll the requested owner.
    videos = [video for video in videos if video.channel_id == payload.channel_id]
    last = state['last_polled_at']
    gap = bool(truncated and last and all(v.published_at and v.published_at > last for v in videos))
    return dict(state=state, captured_at=captured, playlist=playlist, truncated=truncated, gap=gap,
                videos=videos, purposes={v.id: purpose(v) for v in videos})


async def collect_video(job, payload):
    from app.services.music_jobs import db_call, PermanentJobError
    before = await db_call(repository.snapshot, payload.youtube_video_id)
    captured = datetime.now(UTC)
    result = dict(snapshot=before, captured_at=captured, video=None, rows=[], comment=None,
                  extractor='rules-1', outcome='unavailable')
    provider = client()
    try:
        videos = await provider.videos([payload.youtube_video_id])
        if not videos:
            # Public API cannot distinguish deletion from an inaccessible private video.
            result['outcome'] = 'private_or_deleted'
            return result
        video = videos[0]
        if video.id != payload.youtube_video_id or video.channel_id != payload.channel_id:
            raise PermanentJobError('Channel or video mismatch')
        result['video'] = video
        if video.availability == 'private':
            result['outcome'] = 'private_or_deleted'
            return result
        if purpose(video) != payload.purpose:
            result['outcome'] = 'not_eligible'
            return result
        if payload.purpose == 'cover':
            result['outcome'] = 'collected'
            return result
        due = video.ended_at + timedelta(hours=24)
        if captured < due:
            result.update(outcome='not_due' if payload.wait_count < 168 else 'wait_exhausted', due_at=due)
            return result
        comments, truncated = await provider.comments(video.id)
        result['comments_truncated'] = truncated
        if not comments:
            result['outcome'] = 'waiting' if payload.wait_count < 168 else 'wait_exhausted'
            return result
        comment = max(comments, key=lambda c: len(parse_setlist(c.text)))
        rows = parse_setlist(comment.text)
        # Only bounded comment context is sent to the optional retained extractor.
        extracted = await extract_youtube_setlist(comment.text[:20000])
        if extracted is not None:
            evidence = {r['timestamp']: r for r in rows}
            refined = []
            for entry in extracted:
                raw = evidence.get(entry['timestamp'])
                if raw and entry['title'] and entry['title'].casefold() in raw['raw_line'].casefold():
                    artist = entry.get('original_artist')
                    refined.append({**raw, 'title': entry['title'], 'original_artist': artist if artist and artist.casefold() in raw['raw_line'].casefold() else None})
            if refined:
                rows = sorted({r['start_seconds']: r for r in refined}.values(), key=lambda r: r['start_seconds'])
                result['extractor'] = 'openai:' + settings.openai_model
        rows = [r for r in rows if video.duration_seconds is None or r['start_seconds'] < video.duration_seconds]
        result.update(comment=comment, rows=rows, outcome='collected' if rows else ('waiting' if payload.wait_count < 168 else 'wait_exhausted'))
        return result
    except YouTubeFailure as exc:
        if exc.reason in ('commentsDisabled', 'videoNotFound'):
            result['outcome'] = 'comments_disabled' if exc.reason == 'commentsDisabled' else 'private_or_deleted'
            return result
        _translate(exc)


def url_request(*, account_id: int, channel_id: str, url: str, purpose: str = 'archive', request_run: str = 'initial') -> JobRequest:
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError('Expected a public HTTPS YouTube URL')
    parts = parsed.path.strip('/').split('/')
    video_id = None
    if parsed.hostname == 'youtu.be' and len(parts) == 1:
        video_id = parts[0]
    elif parsed.hostname in ('youtube.com', 'www.youtube.com', 'm.youtube.com'):
        if parsed.path == '/watch':
            values = parse_qs(parsed.query).get('v', [])
            video_id = values[0] if len(values) == 1 else None
        elif len(parts) == 2 and parts[0] in ('live', 'shorts'):
            video_id = parts[1]
    if not video_id or not re.fullmatch(r'[A-Za-z0-9_-]{11}', video_id):
        raise ValueError('Expected an exact YouTube video URL')
    request = JobRequest(job_type='youtube_collect', external_account_id=account_id,
                        payload=dict(channel_id=channel_id, youtube_video_id=video_id, purpose=purpose, request_run=request_run))
    request.parsed_payload()
    return request


def handlers():
    from app.services.music_jobs import Handler
    return {'youtube_poll': Handler(collect_poll, repository.persist_poll, timeout_seconds=600),
            'youtube_collect': Handler(collect_video, repository.persist_collect, timeout_seconds=180)}
