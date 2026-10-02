"""Shared bounded avatar download, conversion and verified object storage upload."""
from hashlib import sha256
from io import BytesIO
import ipaddress
import socket
from urllib.parse import urljoin, urlsplit
import warnings

import boto3
from botocore.config import Config
import httpx
from PIL import Image, ImageOps

from app.services.avatar_assets import SIZES, CACHE_CONTROL, storage_settings, public_base

Image.MAX_IMAGE_PIXELS = 40_000_000
MAX_BYTES = 20 * 1024 * 1024


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
    with httpx.Client(timeout=httpx.Timeout(20, connect=10), headers={'User-Agent': 'schedule-music-avatar/1.0'}) as client:
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
        client, bucket = storage()
    for filename, content in [('original', data), *((f'{s}.webp', generated[s]) for s in SIZES)]:
        client.put_object(Bucket=bucket, Key=f'{prefix}/{filename}', Body=content,
            ContentType='image/webp' if filename.endswith('.webp') else 'application/octet-stream',
            CacheControl=CACHE_CONTROL)
    with httpx.Client(timeout=20) as http:
        for size in SIZES:
            response = http.get(public_base() + prefix + f'/{size}.webp')
            if response.status_code == 403:
                raise ValueError('bucket_requires_public_read')
            response.raise_for_status()
            if response.content != generated[size]:
                raise ValueError('public_content_mismatch')
            if response.headers.get('cache-control') != CACHE_CONTROL:
                raise ValueError('cache_control_mismatch')
    return public_base() + prefix + '/512.webp'
