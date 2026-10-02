"""Verify all uploaded variants before their URL can be published; fake S3 and HTTP."""
from unittest.mock import Mock

import httpx
import pytest

from app.services import avatar_storage as storage
from app.services.avatar_assets import CACHE_CONTROL, SIZES


@pytest.mark.parametrize('failure', [None, '403', 'content', 'cache'])
def test_upload_requires_public_identical_cacheable_variants(monkeypatch, failure):
    generated = {size: f'webp-{size}'.encode() for size in SIZES}
    prefix = 'avatars/v1/1/' + 'a'*32
    client = Mock()
    requests = []
    def response(request):
        requests.append(request.url.path)
        size = int(request.url.path.rsplit('/', 1)[-1].split('.')[0])
        return httpx.Response(403 if failure == '403' else 200,
            content=b'wrong' if failure == 'content' else generated[size],
            headers={'Cache-Control': 'wrong' if failure == 'cache' else CACHE_CONTROL})
    http = httpx.Client(transport=httpx.MockTransport(response))
    monkeypatch.setattr(storage.httpx, 'Client', lambda **kwargs: http)
    monkeypatch.setattr(storage, 'public_base', lambda: 'https://storage.test/bucket/')
    if failure:
        with pytest.raises(ValueError):
            storage.upload(prefix, b'original', generated, client=client, bucket='bucket')
    else:
        assert storage.upload(prefix, b'original', generated, client=client, bucket='bucket').endswith('/512.webp')
        assert len(requests) == 3
    assert client.put_object.call_count == 4
    assert all(call.kwargs['CacheControl'] == CACHE_CONTROL for call in client.put_object.call_args_list)


def test_redirect_to_private_address_is_rejected(monkeypatch):
    def address(host, *args):
        return [(2, 1, 6, '', ('127.0.0.1' if host == 'private.test' else '8.8.8.8', 443))]
    monkeypatch.setattr(storage.socket, 'getaddrinfo', address)
    http = httpx.Client(transport=httpx.MockTransport(lambda request:
        httpx.Response(302, headers={'Location': 'https://private.test/image'})))
    monkeypatch.setattr(storage.httpx, 'Client', lambda **kwargs: http)
    with pytest.raises(ValueError, match='non_public_source'):
        storage.download('https://public.test/image')
