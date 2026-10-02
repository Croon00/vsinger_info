"""Profile image discovery only; no posts, videos, persistence or uploads."""
import asyncio
import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import unquote, urlsplit
from typing import Literal

import httpx
from pydantic import BaseModel, Field

from app.core.config import settings
from app.integrations.youtube_catalog import YouTubeClient, YouTubeFailure
from app.integrations.x_client import get_x_profile_image_url, x_configured


class AvatarCandidate(BaseModel):
    account_id: int = Field(gt=0)
    platform: Literal['youtube', 'x']
    external_id: str
    source_url: str


class AvatarSourceError(Exception):
    def __init__(self, code, *, retry=False, retry_after=0):
        super().__init__(code)
        self.code, self.retry, self.retry_after = code, retry, max(0, retry_after)


def retry_delay(response):
    header = response.headers.get('Retry-After', '0')
    try:
        return max(0, float(header))
    except ValueError:
        try:
            return max(0, (parsedate_to_datetime(header) - datetime.now(UTC)).total_seconds())
        except (ValueError, TypeError):
            return 60


def profile_path(url, hosts):
    try:
        parsed = urlsplit(url)
        if (parsed.scheme != 'https' or parsed.hostname not in hosts or parsed.username or parsed.password
                or parsed.port not in (None, 443)):
            raise ValueError()
        return unquote(parsed.path).strip('/').split('/')
    except ValueError:
        raise AvatarSourceError('invalid_profile_url') from None


def youtube_selector(account):
    parts = profile_path(account['url'], ('youtube.com', 'www.youtube.com', 'm.youtube.com'))
    stored = account.get('platform_id')
    if stored and re.fullmatch(r'UC[A-Za-z0-9_-]{22}', stored):
        return {'id': stored}
    if len(parts) == 2 and parts[0] == 'channel' and re.fullmatch(r'UC[A-Za-z0-9_-]{22}', parts[1]):
        return {'id': parts[1]}
    if len(parts) == 1 and re.fullmatch(r'@[^\s/?#]{3,30}', parts[0]):
        return {'forHandle': parts[0]}
    if len(parts) == 2 and parts[0] == 'user' and re.fullmatch(r'[A-Za-z0-9_-]{1,100}', parts[1]):
        return {'forUsername': parts[1]}
    raise AvatarSourceError('channel_id_required')


def x_username(account):
    parts = profile_path(account['url'], ('x.com', 'www.x.com', 'twitter.com', 'www.twitter.com'))
    if len(parts) != 1 or not re.fullmatch(r'[A-Za-z0-9_]{1,15}', parts[0]) or parts[0].lower() in {
        'home', 'explore', 'search', 'settings', 'intent', 'i', 'messages', 'notifications'}:
        raise AvatarSourceError('invalid_x_profile_url')
    return parts[0]


async def discover(account):
    if account['platform'] == 'youtube':
        try:
            selector = youtube_selector(account)
            data = await YouTubeClient(settings.youtube_api_key).get('channels', part='snippet', **selector)
            items = data['items']
            if not items:
                raise AvatarSourceError('channel_unavailable')
            item = items[0]
            if 'id' in selector and item['id'] != selector['id']:
                raise AvatarSourceError('channel_mismatch')
            if not re.fullmatch(r'UC[A-Za-z0-9_-]{22}', item['id']):
                raise AvatarSourceError('malformed_channel')
            thumbnails = item.get('snippet', {}).get('thumbnails', {})
            for size in ('high', 'medium', 'default'):
                url = thumbnails.get(size, {}).get('url')
                if isinstance(url, str) and url.startswith('https://'):
                    return AvatarCandidate(account_id=account['id'], platform='youtube',
                                           external_id=item['id'], source_url=url)
            raise AvatarSourceError('image_missing')
        except YouTubeFailure as exc:
            raise AvatarSourceError(exc.reason, retry=exc.retry, retry_after=exc.retry_after) from None
        except (KeyError, TypeError, AttributeError):
            raise AvatarSourceError('malformed_channel') from None
    if account['platform'] == 'x':
        username = x_username(account)
        if not x_configured():
            raise AvatarSourceError('missing_x_configuration')
        try:
            url = await asyncio.wait_for(get_x_profile_image_url(username), timeout=30)
            if not url.startswith('https://'):
                raise AvatarSourceError('invalid_image_url')
            return AvatarCandidate(account_id=account['id'], platform='x', external_id=username, source_url=url)
        except httpx.HTTPStatusError as exc:
            retry = exc.response.status_code == 429 or exc.response.status_code >= 500
            raise AvatarSourceError('x_http_error', retry=retry, retry_after=retry_delay(exc.response)) from None
        except (httpx.RequestError, TimeoutError):
            raise AvatarSourceError('x_timeout', retry=True) from None
        except RuntimeError:
            raise AvatarSourceError('x_image_unavailable') from None
        except AvatarSourceError:
            raise
        except Exception:
            # Includes a depleted twscrape UserByScreenName pool. Never expose SDK messages.
            raise AvatarSourceError('x_provider_unavailable', retry=True, retry_after=300) from None
    raise AvatarSourceError('unsupported_platform')
