"""Verify all uploaded variants before their URL can be published; fake S3 and HTTP."""
from unittest.mock import Mock

from botocore.exceptions import ClientError, EndpointConnectionError
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
        with pytest.raises(storage.AvatarStorageError) as caught:
            storage.upload(prefix, b'original', generated, client=client, bucket='bucket')
        assert caught.value.details['stage'] == 'verify_public'
        assert caught.value.details['object_name'] == '128.webp'
        assert caught.value.details['code'] == {
            '403': 'bucket_requires_public_read', 'content': 'public_content_mismatch',
            'cache': 'cache_control_mismatch'}[failure]
    else:
        assert storage.upload(prefix, b'original', generated, client=client, bucket='bucket').endswith('/512.webp')
        assert len(requests) == 3
    assert client.put_object.call_count == 4
    assert all(call.kwargs['CacheControl'] == CACHE_CONTROL for call in client.put_object.call_args_list)


@pytest.mark.parametrize('failed_call,stage,filename', [
    (1, 'upload_original', 'original'), (3, 'upload_variant', '256.webp')])
def test_s3_failure_identifies_object_without_leaking_sdk_details(failed_call, stage, filename):
    client = Mock()
    exc = ClientError({'Error': {'Code': 'AccessDenied', 'Message': 'secret-token'},
                       'ResponseMetadata': {'HTTPStatusCode': 403,
                                            'HTTPHeaders': {'Authorization': 'secret-token'}}}, 'PutObject')
    client.put_object.side_effect = [None] * (failed_call - 1) + [exc]
    with pytest.raises(storage.AvatarStorageError) as caught:
        storage.upload('avatars/v1/1/' + 'a'*32, b'original', {s: b'webp' for s in SIZES},
                       client=client, bucket='bucket')
    assert caught.value.details == {'stage': stage, 'object_name': filename,
        'code': 's3_error', 'error_type': 'ClientError', 'provider_code': 'AccessDenied', 'http_status': 403}
    assert 'secret-token' not in str(caught.value.details) + str(caught.value)
    assert client.put_object.call_count == failed_call


def test_missing_config_is_distinguished_from_upload(monkeypatch):
    monkeypatch.setattr(storage, 'storage_settings', lambda: {})
    with pytest.raises(storage.AvatarStorageError) as caught:
        storage.upload('avatars/v1/1/' + 'a'*32, b'original', {s: b'webp' for s in SIZES})
    assert caught.value.details == {'stage': 'storage_config', 'code': 'missing_storage_configuration',
                                   'error_type': 'ValueError'}


@pytest.mark.parametrize('failure,code,http_status', [
    ('404', 'public_http_error', 404), ('timeout', 'storage_timeout', None),
    ('connect', 'storage_connection_error', None)])
def test_public_failure_is_safe_and_identifies_variant(monkeypatch, failure, code, http_status):
    def response(request):
        if failure == 'timeout':
            raise httpx.ReadTimeout('secret-token', request=request)
        if failure == 'connect':
            raise httpx.ConnectError('secret-token', request=request)
        return httpx.Response(404, text='secret-token')
    http = httpx.Client(transport=httpx.MockTransport(response))
    monkeypatch.setattr(storage.httpx, 'Client', lambda **kwargs: http)
    monkeypatch.setattr(storage, 'public_base', lambda: 'https://storage.test/bucket/?secret-token=')
    with pytest.raises(storage.AvatarStorageError) as caught:
        storage.upload('avatars/v1/1/' + 'a'*32, b'original', {s: b'webp' for s in SIZES},
                       client=Mock(), bucket='bucket')
    details = caught.value.details
    assert details['stage'] == 'verify_public' and details['object_name'] == '128.webp'
    assert details['code'] == code
    assert details.get('http_status') == http_status
    assert 'secret-token' not in str(details) + str(caught.value)


@pytest.mark.parametrize('exc', [
    RuntimeError('secret-token'), ValueError('secret-token'),
    EndpointConnectionError(endpoint_url='https://secret-token.test'),
    ClientError({'Error': {'Code': 'secret-token', 'Message': 'secret-token'}}, 'PutObject')])
def test_unrecognized_storage_exceptions_never_publish_raw_messages(exc):
    error = storage.storage_error(exc, stage='storage')
    assert 'secret-token' not in str(error.details) + str(error)


def test_redirect_to_private_address_is_rejected(monkeypatch):
    def address(host, *args):
        return [(2, 1, 6, '', ('127.0.0.1' if host == 'private.test' else '8.8.8.8', 443))]
    monkeypatch.setattr(storage.socket, 'getaddrinfo', address)
    http = httpx.Client(transport=httpx.MockTransport(lambda request:
        httpx.Response(302, headers={'Location': 'https://private.test/image'})))
    monkeypatch.setattr(storage.httpx, 'Client', lambda **kwargs: http)
    with pytest.raises(ValueError, match='non_public_source'):
        storage.download('https://public.test/image')
