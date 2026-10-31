"""Batched, validated YouTube view counts; missing statistics stay unknown."""
from datetime import datetime
from pydantic import BaseModel, Field


class VideoStatistics(BaseModel):
    video_id: str = Field(pattern=r'^[A-Za-z0-9_-]{11}$')
    channel_id: str = Field(pattern=r'^UC[A-Za-z0-9_-]{22}$')
    view_count: int | None = Field(default=None, ge=0)
    captured_at: datetime


async def fetch_statistics(client, ids, captured_at):
    ids = list(dict.fromkeys(ids))
    rows = []
    for start in range(0, len(ids), 50):
        batch = ids[start:start+50]
        data = await client.get('videos', part='snippet,statistics', id=','.join(batch))
        for item in data['items']:
            if item['id'] not in batch:
                raise ValueError('Unrequested video statistics')
            rows.append(VideoStatistics(video_id=item['id'], channel_id=item['snippet']['channelId'],
                view_count=item.get('statistics', {}).get('viewCount'), captured_at=captured_at))
    return rows
