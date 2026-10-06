"""Shared bounded avatar download, conversion and verified object storage upload."""
from hashlib import sha256
from io import BytesIO
import ipaddress
import re
import socket
from urllib.parse import urljoin, urlsplit
import warnings

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
import httpx
from PIL import Image, ImageOps

from app.services.avatar_assets import SIZES, CACHE_CONTROL, storage_settings, public_base

Image.MAX_IMAGE_PIXELS = 40_000_000
MAX_BYTES = 20 * 1024 * 1024

# SDK messages and request URLs can contain credentials. Keep only known codes
# and structural metadata, never exception messages, response bodies or headers.
S3_ERROR_CODES = {
    'AccessDenied', 'AuthorizationHeaderMalformed', 'BadDigest', 'EntityTooLarge',
    'ExpiredToken', 'IncompleteBody', 'InternalError', 'InvalidAccessKeyId',
    'InvalidArgument', 'InvalidDigest', 'InvalidRequest', 'InvalidToken',
    'NoSuchBucket', 'NoSuchKey', 'NotImplemented', 'RequestTimeout',
    'RequestTimeTooSkewed', 'ServiceUnavailable', 'SignatureDoesNotMatch', 'SlowDown',
    'Throttling', 'ThrottlingException', 'TooManyRequests',
}
VALIDATION_ERRORS = {
    'missing_storage_configuration', 'bucket_requires_public_read',
    'public_content_mismatch', 'cache_control_mismatch',
}


class AvatarStorageError(ValueError):
    """Safe diagnostic that remains compatible with the explicit migration CLI."""

    def __init__(self, details):
        self.details = details
        super().__init__(details['code'])


def storage_error(exc, *, stage, object_name=None):
    if isinstance(exc, AvatarStorageError):
        return exc
    name = type(exc).__name__
    details = {'stage': stage, 'code': 'storage_exception',
               'error_type': name if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,79}', name) else 'Exception'}
    if object_name is not None:
        details['object_name'] = object_name
    if isinstance(exc, ClientError):
        details['code'] = 's3_error'
        provider_code = exc.response.get('Error', {}).get('Code')
        details['provider_code'] = provider_code if provider_code in S3_ERROR_CODES else 'unrecognized'
        status = exc.response.get('ResponseMetadata', {}).get('HTTPStatusCode')
        if isinstance(status, int) and 100 <= status <= 599:
            details['http_status'] = status
    elif isinstance(exc, httpx.HTTPStatusError):
        details.update(code='public_http_error', http_status=exc.response.status_code)
    elif isinstance(exc, (httpx.TimeoutException, TimeoutError)):
        details['code'] = 'storage_timeout'
    elif isinstance(exc, httpx.RequestError):
        details['code'] = 'storage_connection_error'
    elif isinstance(exc, ValueError) and len(exc.args) == 1 and isinstance(exc.args[0], str) and exc.args[0] in VALIDATION_ERRORS:
        details['code'] = exc.args[0]
        if exc.args[0] == 'bucket_requires_public_read':
            details['http_status'] = 403
    return AvatarStorageError(details)


def public_url(url):
    parsed = urlsplit(url)
    if parsed.scheme not in ('https', 'http') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('invalid_source_url')
    if parsed.port not in (None, 80, 443):
        raise ValueError('unsupported_source_port')
    addresses = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == 'https' else 80))
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError('non_public_source')
    return url


def download(url):
    with httpx.Client(timeout=httpx.Timeout(20, connect=10), headers={'User-Agent': 'UtaMowa-avatar/1.0'}) as client:
        for _ in range(6):
            public_url(url)
            with client.stream('GET', url) as response:
                if response.is_redirect:
                    url = urljoin(url, response.headers['location'])
                    continue
                response.raise_for_status()
                data = bytearray()
                for chunk in response.iter_bytes():
                    data.extend(chunk)
                    if len(data) > MAX_BYTES:
                        raise ValueError('source_too_large')
                return bytes(data)
    raise ValueError('too_many_redirects')


def variants(data):
    if len(data) > MAX_BYTES:
        raise ValueError('source_too_large')
    with warnings.catch_warnings():
        warnings.simplefilter('error', Image.DecompressionBombWarning)
        with Image.open(BytesIO(data)) as source:
            source.load()
            image = ImageOps.exif_transpose(source).convert('RGBA' if 'A' in source.getbands() else 'RGB')
            result = {}
            for size in SIZES:
                copy = image.copy()
                copy.thumbnail((size, size), Image.Resampling.LANCZOS)
                output = BytesIO()
                copy.save(output, format='WEBP', quality=85, method=6)
                result[size] = output.getvalue()
            return result


def image_prefix(artist_id, data, generated):
    digest = sha256(data + b''.join(generated[s] for s in SIZES)).hexdigest()[:32]
    return f'avatars/v1/{artist_id}/{digest}'


def storage():
    values = storage_settings()
    required = ('AWS_ENDPOINT_URL_S3', 'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_REGION')
    if any(not values.get(k) for k in required):
        raise ValueError('missing_storage_configuration')
    client = boto3.client('s3', endpoint_url=values['AWS_ENDPOINT_URL_S3'],
        aws_access_key_id=values['AWS_ACCESS_KEY_ID'], aws_secret_access_key=values['AWS_SECRET_ACCESS_KEY'],
        region_name=values['AWS_REGION'], config=Config(signature_version='s3v4', s3={'addressing_style': 'path'},
            connect_timeout=10, read_timeout=30, retries={'max_attempts': 3, 'mode': 'standard'},
            request_checksum_calculation='when_required', response_checksum_validation='when_required'))
    return client, values.get('AVATAR_BUCKET') or 'artists-avator'


def upload(prefix, data, generated, *, client=None, bucket=None):
    if client is None:
        try:
            client, bucket = storage()
        except Exception as exc:
            raise storage_error(exc, stage='storage_config') from None
    for filename, content in [('original', data), *((f'{s}.webp', generated[s]) for s in SIZES)]:
        try:
            client.put_object(Bucket=bucket, Key=f'{prefix}/{filename}', Body=content,
                ContentType='image/webp' if filename.endswith('.webp') else 'application/octet-stream',
                CacheControl=CACHE_CONTROL)
        except Exception as exc:
            raise storage_error(exc, stage='upload_original' if filename == 'original' else 'upload_variant',
                                object_name=filename) from None
    filename = None
    try:
        with httpx.Client(timeout=20) as http:
            for size in SIZES:
                filename = f'{size}.webp'
                response = http.get(public_base() + prefix + '/' + filename)
                if response.status_code == 403:
                    raise ValueError('bucket_requires_public_read')
                response.raise_for_status()
                if response.content != generated[size]:
                    raise ValueError('public_content_mismatch')
                if response.headers.get('cache-control') != CACHE_CONTROL:
                    raise ValueError('cache_control_mismatch')
    except Exception as exc:
        raise storage_error(exc, stage='verify_public', object_name=filename) from None
    return public_base() + prefix + '/512.webp'
