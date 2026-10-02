"""Provider response fixtures only. Never calls YouTube or X."""
import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest

from app.integrations import avatar_sources as sources
from app.integrations.youtube_catalog import YouTubeClient

CHANNEL = 'UC' + 'a' * 22


def account(platform='youtube', **updates):
    return dict({'id': 1, 'platform': platform, 'platform_id': CHANNEL if platform == 'youtube' else '123',
                 'url': 'https://www.youtube.com/@singer' if platform == 'youtube' else 'https://x.com/singer'}, **updates)


@pytest.mark.parametrize('url,expected', [
    (f'https://youtube.com/channel/{CHANNEL}', {'id': CHANNEL}),
    ('https://www.youtube.com/@singer', {'forHandle': '@singer'}),
    ('https://youtube.com/user/Singer', {'forUsername': 'Singer'}),
])
def test_channel_url_resolution(url, expected):
    assert sources.youtube_selector(account(url=url, platform_id=None)) == expected


@pytest.mark.parametrize('url', ['https://youtube.com/c/Singer', 'https://youtube.com/watch?v=123',
                                'https://evil.test/@singer', 'http://youtube.com/@singer',
                                'https://youtube.com:444/@singer'])
def test_unresolved_or_untrusted_channels_are_not_name_searched(url):
    with pytest.raises(sources.AvatarSourceError):
        sources.youtube_selector(account(url=url, platform_id=None))


@pytest.mark.parametrize('thumbnails,expected', [
    ({'high': {'url': 'https://image.test/high'}, 'medium': {'url': 'https://image.test/medium'}}, 'high'),
    ({'medium': {'url': 'https://image.test/medium'}}, 'medium'),
    ({'default': {'url': 'https://image.test/default'}}, 'default'),
])
def test_youtube_profile_thumbnail_priority(monkeypatch, thumbnails, expected):
    get = AsyncMock(return_value={'items': [{'id': CHANNEL, 'snippet': {'thumbnails': thumbnails}}]})
    monkeypatch.setattr(YouTubeClient, 'get', get)
    candidate = asyncio.run(sources.discover(account()))
    assert candidate.source_url == f'https://image.test/{expected}'
    get.assert_awaited_once_with('channels', part='snippet', id=CHANNEL)


@pytest.mark.parametrize('data,code', [({'items': []}, 'channel_unavailable'),
    ({'items': [{'id': CHANNEL, 'snippet': {}}]}, 'image_missing'),
    ({'items': [{'id': 'UC' + 'b'*22}]}, 'channel_mismatch'),
    ({'items': [{'id': CHANNEL, 'snippet': None}]}, 'malformed_channel')])
def test_unusable_youtube_responses(monkeypatch, data, code):
    monkeypatch.setattr(YouTubeClient, 'get', AsyncMock(return_value=data))
    with pytest.raises(sources.AvatarSourceError, match=code):
        asyncio.run(sources.discover(account()))


def test_x_reuses_selected_provider_and_propagates_cooldown(monkeypatch):
    monkeypatch.setattr(sources, 'x_configured', lambda: True)
    lookup = AsyncMock(return_value='https://image.test/x.png')
    monkeypatch.setattr(sources, 'get_x_profile_image_url', lookup)
    assert asyncio.run(sources.discover(account('x'))).platform == 'x'
    lookup.assert_awaited_once_with('singer')
    response = httpx.Response(429, headers={'Retry-After': '900'}, request=httpx.Request('GET', 'https://api.x.com'))
    lookup.side_effect = httpx.HTTPStatusError('secret', request=response.request, response=response)
    with pytest.raises(sources.AvatarSourceError) as failure:
        asyncio.run(sources.discover(account('x')))
    assert failure.value.retry and failure.value.retry_after == 900
    assert 'secret' not in str(failure.value)


@pytest.mark.parametrize('url', ['https://x.com/singer/status/123', 'https://x.com/home', 'https://evil.test/singer'])
def test_x_requires_profile_url(url):
    with pytest.raises(sources.AvatarSourceError):
        sources.x_username(account('x', url=url))
