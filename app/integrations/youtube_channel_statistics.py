"""Validated public channel metadata; creation date is separate from debut date."""
from datetime import datetime
from pydantic import BaseModel, Field


class ChannelStatistics(BaseModel):
    channel_id: str = Field(pattern=r'^UC[A-Za-z0-9_-]{22}$')
    created_at: datetime | None = None
    subscriber_count: int | None = Field(default=None, ge=0)
    subscribers_hidden: bool = False
    captured_at: datetime


async def fetch_statistics(client, ids, captured_at):
    rows = []
    ids = list(dict.fromkeys(ids))
    for offset in range(0, len(ids), 50):
        batch = ids[offset:offset + 50]
        data = await client.get('channels', part='snippet,statistics', id=','.join(batch))
        for item in data['items']:
            if item['id'] not in batch:
                raise ValueError('Unrequested YouTube channel')
            stats = item.get('statistics', {})
            hidden = stats.get('hiddenSubscriberCount', False)
            rows.append(ChannelStatistics(channel_id=item['id'],
                created_at=item.get('snippet', {}).get('publishedAt'),
                subscriber_count=None if hidden else stats.get('subscriberCount'),
                subscribers_hidden=hidden, captured_at=captured_at))
    return rows
