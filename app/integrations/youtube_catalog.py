"""Bounded YouTube reads for the normalized catalog; no database dependencies."""
from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Literal

import httpx
from pydantic import BaseModel, Field


class YouTubeFailure(Exception):
    def __init__(self, reason: str, *, retry: bool = False, retry_after: float = 0):
        super().__init__(reason)
        self.reason, self.retry, self.retry_after = reason, retry, retry_after


class Video(BaseModel):
    id: str = Field(pattern=r'^[A-Za-z0-9_-]{11}$')
    channel_id: str = Field(pattern=r'^UC[A-Za-z0-9_-]{22}$')
    title: str = Field(min_length=1)
    description: str = ''
    published_at: datetime | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    scheduled: bool = False
    duration_seconds: int | None = Field(default=None, ge=0)
    availability: Literal['public', 'unlisted', 'private', 'unknown'] = 'unknown'


class Comment(BaseModel):
    id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    captured_at: datetime


SINGING = ('歌枠', '歌配信', 'カラオケ', '弾き語り', 'うたわく', 'singing', 'karaoke', 'acoustic')
COVER = ('cover', '歌ってみた', '歌唱', 'カバー', 'covered by')
STAMP = re.compile(r'(?<![\d:])((?:\d{1,2}:)?[0-5]?\d:[0-5]\d)(?![\d:])')


def purpose(video: Video) -> str | None:
    if video.ended_at and video.started_at:
        return 'archive' if any(k in video.title.casefold() for k in SINGING) else None
    if video.started_at or video.scheduled:
        return None
    return 'cover' if any(k in (video.title + '\n' + video.description).casefold() for k in COVER) else None


def parse_setlist(content: str) -> list[dict]:
    """Conservative fallback. Retain source lines; never resolve names to entities."""
    rows, seen = [], set()
    for line in content.splitlines():
        match = STAMP.search(line)
        if not match:
            continue
        stamp = match.group(1)
        title = line[match.end():].strip()
        title = re.sub(r'^[~〜～\-–—]\s*(?:\d{1,2}:)?[0-5]?\d:[0-5]\d\s*', '', title)
        title = title.strip(' \t-–—|｜:：.')
        title = re.sub(r'^(?:#\s*)?(?:제\s*)?\d+\s*(?:곡목?|曲目?)?\s*(?:[.．:：\-—)]\s*)+', '', title)
        quoted = re.search(r'[「『"](.+?)[」』"]', title)
        if quoted:
            title = quoted.group(1)
        title = re.sub(r'\s+[0-9０-９]+(?:[.．][0-9０-９]+)?(?:点|pts?\.?)?\s*$', '', title, flags=re.I).strip()
        if not title or re.match(r'^(start|end|opening|closing|mc|intro|outro|挨拶|雑談|終了|시작|종료)(?:\b|\s|[!！])', title, re.I):
            continue
        parts = [int(p) for p in stamp.split(':')]
        seconds = sum(p * 60 ** i for i, p in enumerate(reversed(parts)))
        if seconds in seen:
            continue
        seen.add(seconds)
        rows.append(dict(timestamp=stamp, start_seconds=seconds, title=title.replace('／', '/').replace('｜', '/')[:300], original_artist=None, raw_line=line))
    return sorted(rows, key=lambda r: r['start_seconds'])[:200]


def _date(value):
    if not value:
        return None
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Missing timezone')
    return result


def _video(item) -> Video:
    snippet, live = item['snippet'], item.get('liveStreamingDetails', {})
    duration = item.get('contentDetails', {}).get('duration', '')
    match = re.fullmatch(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration)
    seconds = sum(int(v or 0) * n for v, n in zip(match.groups(), (3600, 60, 1))) if match else None
    return Video(id=item['id'], channel_id=snippet['channelId'], title=snippet['title'],
                 description=snippet.get('description', ''), published_at=_date(snippet.get('publishedAt')),
                 started_at=_date(live.get('actualStartTime')), ended_at=_date(live.get('actualEndTime')),
                 scheduled=bool(live.get('scheduledStartTime')) or snippet.get('liveBroadcastContent') in ('live', 'upcoming'),
                 duration_seconds=seconds, availability=item.get('status', {}).get('privacyStatus', 'unknown'))


class YouTubeClient:
    def __init__(self, key: str, *, transport=None, interval: float = 1):
        self.key, self.transport, self.interval = key, transport, interval
        self.last_request = 0.0

    async def get(self, resource: str, **params) -> dict:
        if not self.key:
            raise YouTubeFailure('missing_api_key')
        loop = asyncio.get_running_loop()
        await asyncio.sleep(max(0, self.interval - (loop.time() - self.last_request)))
        self.last_request = loop.time()
        try:
            async with httpx.AsyncClient(timeout=30, transport=self.transport) as client:
                response = await client.get('https://www.googleapis.com/youtube/v3/' + resource,
                                            params={**params, 'key': self.key})
        except httpx.TransportError:
            raise YouTubeFailure('transport', retry=True) from None
        try:
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError()
        except ValueError:
            raise YouTubeFailure('malformed_response', retry=response.status_code >= 500) from None
        if response.is_error:
            try:
                reason = (data.get('error', {}).get('errors') or [{}])[0].get('reason', '')
            except (AttributeError, TypeError, IndexError):
                reason = ''
            safe = reason if reason in ('commentsDisabled', 'videoNotFound', 'quotaExceeded', 'dailyLimitExceeded') else 'provider_error'
            retry = response.status_code == 429 or response.status_code >= 500 or safe in ('quotaExceeded', 'dailyLimitExceeded')
            delay = 86400 if safe in ('quotaExceeded', 'dailyLimitExceeded') else 0
            header = response.headers.get('Retry-After', '')
            try:
                delay = max(delay, float(header))
            except ValueError:
                try:
                    delay = max(delay, (parsedate_to_datetime(header) - datetime.now(UTC)).total_seconds())
                except (ValueError, TypeError):
                    pass
            raise YouTubeFailure(safe, retry=retry, retry_after=delay)
        if not isinstance(data.get('items'), list):
            raise YouTubeFailure('malformed_response')
        return data

    async def videos(self, ids: list[str]) -> list[Video]:
        result = []
        for offset in range(0, len(ids), 50):
            data = await self.get('videos', part='snippet,contentDetails,liveStreamingDetails,status', id=','.join(ids[offset:offset+50]))
            try:
                result.extend(_video(item) for item in data['items'])
            except (KeyError, TypeError, ValueError):
                raise YouTubeFailure('malformed_video') from None
        return result

    async def recent(self, channel: str) -> tuple[str, list[Video], bool]:
        data = await self.get('channels', part='contentDetails', id=channel)
        try:
            item = data['items'][0]
            if item['id'] != channel:
                raise ValueError()
            playlist = item['contentDetails']['relatedPlaylists']['uploads']
        except (IndexError, KeyError, TypeError, ValueError):
            raise YouTubeFailure('channel_unavailable') from None
        ids, token = [], None
        for _ in range(4):
            data = await self.get('playlistItems', part='contentDetails', playlistId=playlist, maxResults=50,
                                  **({'pageToken': token} if token else {}))
            try:
                ids.extend(item['contentDetails']['videoId'] for item in data['items'])
            except (KeyError, TypeError):
                raise YouTubeFailure('malformed_playlist') from None
            token = data.get('nextPageToken')
            if not token:
                break
        return playlist, await self.videos(list(dict.fromkeys(ids))), bool(token)

    async def comments(self, video: str) -> tuple[list[Comment], bool]:
        result, token = [], None
        for _ in range(3):
            data = await self.get('commentThreads', part='snippet', videoId=video, order='relevance', textFormat='plainText', maxResults=100,
                                  **({'pageToken': token} if token else {}))
            try:
                for item in data['items']:
                    comment = item['snippet']['topLevelComment']
                    content = comment['snippet'].get('textOriginal') or comment['snippet']['textDisplay']
                    if len(parse_setlist(content)) >= 2:
                        result.append(Comment(id=comment['id'], text=content, captured_at=datetime.now(UTC)))
            except (KeyError, TypeError, ValueError):
                raise YouTubeFailure('malformed_comment') from None
            token = data.get('nextPageToken')
            if not token:
                break
        return result, bool(token)
