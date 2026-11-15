"""Bounded, authenticated Holodex live reads. No database or YouTube API calls.

Holodex API terms and warranty disclaimer: https://docs.holodex.net/#section/LICENSE
Data is provided as-is by Holodex; availability and accuracy are not guaranteed.
"""
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Literal

import httpx
from pydantic import BaseModel, Field, ValidationError, field_validator


class HolodexFailure(Exception):
    def __init__(self, reason: str, *, retry_after: float = 60):
        super().__init__(reason)
        self.reason = reason
        self.retry_after = max(60, retry_after)


class HolodexStream(BaseModel):
    id: str = Field(pattern=r'^[A-Za-z0-9_-]{11}$')
    channel_id: str = Field(pattern=r'^UC[A-Za-z0-9_-]{22}$')
    title: str = Field(min_length=1)
    status: Literal['live', 'upcoming']
    start_actual: datetime | None = None
    start_scheduled: datetime | None = None
    end_actual: datetime | None = None

    @field_validator('start_actual', 'start_scheduled', 'end_actual')
    @classmethod
    def aware_dates(cls, value):
        if value is not None and value.tzinfo is None:
            raise ValueError('Missing timezone')
        return value


class HolodexClient:
    def __init__(self, key: str, *, transport=None):
        self.key, self.transport = key, transport

    async def live(self, channels: list[str]) -> list[HolodexStream]:
        if not self.key:
            raise HolodexFailure('missing_api_key', retry_after=900)
        channels = list(dict.fromkeys(channels))
        result = {}
        # Keep URLs bounded. The documented users/live endpoint accepts channel IDs.
        async with httpx.AsyncClient(timeout=30, transport=self.transport) as client:
            for offset in range(0, len(channels), 50):
                batch = set(channels[offset:offset+50])
                try:
                    response = await client.get('https://holodex.net/api/v2/users/live',
                        params={'channels': ','.join(sorted(batch))}, headers={'X-APIKEY': self.key})
                except httpx.TransportError:
                    raise HolodexFailure('transport') from None
                if response.is_error:
                    delay = 900 if response.status_code in (401, 403) else 60
                    header = response.headers.get('Retry-After', '')
                    try:
                        delay = max(delay, float(header))
                    except ValueError:
                        try:
                            delay = max(delay, (parsedate_to_datetime(header)-datetime.now(UTC)).total_seconds())
                        except (ValueError, TypeError, OverflowError):
                            pass
                    reason = 'unauthorized' if response.status_code in (401, 403) else (
                        'rate_limited' if response.status_code == 429 else 'provider_error')
                    raise HolodexFailure(reason, retry_after=delay)
                try:
                    rows = response.json()
                    if not isinstance(rows, list) or len(rows) > 5000:
                        raise ValueError()
                    for row in rows:
                        if not isinstance(row, dict):
                            raise ValueError()
                        # Ignore external placeholders, past videos and collab channels.
                        channel = row.get('channel_id') or (row.get('channel') or {}).get('id')
                        if row.get('type') != 'stream' or row.get('status') not in ('live', 'upcoming') or channel not in batch:
                            continue
                        stream = HolodexStream.model_validate({**row, 'channel_id': channel})
                        if not stream.end_actual:
                            result[stream.id] = stream
                except (ValueError, TypeError, AttributeError, ValidationError):
                    raise HolodexFailure('malformed_response') from None
        return list(result.values())
