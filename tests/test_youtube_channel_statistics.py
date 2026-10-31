import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock

from app.integrations.youtube_channel_statistics import fetch_statistics
from app.integrations.youtube_catalog import YouTubeClient
import httpx


def test_statistics_batches_ids_and_preserves_hidden_counts():
    ids = ['UC' + str(i).zfill(22) for i in range(51)]
    captured = datetime.now(UTC)
    client = AsyncMock()
    client.get.side_effect = [
        {'items': [dict(id=ids[0], snippet={'publishedAt': '2018-02-01T03:00:00Z'},
                        statistics={'subscriberCount': '123000', 'hiddenSubscriberCount': False})]},
        {'items': [dict(id=ids[50], statistics={'subscriberCount': '10', 'hiddenSubscriberCount': True})]},
    ]
    rows = asyncio.run(fetch_statistics(client, ids + [ids[0]], captured))
    assert client.get.await_count == 2
    assert len(client.get.await_args_list[0].kwargs['id'].split(',')) == 50
    assert rows[0].subscriber_count == 123000
    assert rows[0].created_at.year == 2018
    assert rows[0].captured_at == captured
    assert rows[1].subscriber_count is None and rows[1].subscribers_hidden


def test_missing_statistics_are_unknown_not_zero():
    client = AsyncMock()
    client.get.return_value = {'items': [{'id': 'UC' + 'a'*22}]}
    rows = asyncio.run(fetch_statistics(client, ['UC'+'a'*22], datetime.now(UTC)))
    assert rows[0].subscriber_count is None and rows[0].created_at is None


def test_normal_poll_captures_statistics_without_an_extra_channel_request():
    channel = 'UC' + 'a'*22
    resources = []
    def respond(request):
        resources.append(request.url.path.rsplit('/', 1)[-1])
        if resources[-1] == 'channels':
            assert 'statistics' in request.url.params['part']
            return httpx.Response(200, json={'items': [dict(id=channel,
                contentDetails={'relatedPlaylists': {'uploads': 'uploads'}},
                snippet={'publishedAt': '2020-01-01T00:00:00Z'},
                statistics={'subscriberCount': '10000', 'hiddenSubscriberCount': False})]})
        return httpx.Response(200, json={'items': []})
    client = YouTubeClient('fake', transport=httpx.MockTransport(respond), interval=0)
    playlist, videos, truncated = asyncio.run(client.recent(channel))
    assert (playlist, videos, truncated) == ('uploads', [], False)
    assert client.channel_statistics.subscriber_count == 10000
    assert resources == ['channels', 'playlistItems']
