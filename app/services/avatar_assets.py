"""Managed avatar URL contract; no storage or image I/O in read requests."""
import re

from app.core.config import Settings

SIZES = (128, 256, 512)
CACHE_CONTROL = "public, max-age=31536000, immutable"
PATH_PATTERN = re.compile(r"avatars/v1/[0-9]+/[a-f0-9]{32}/512\.webp$")

def public_storage_settings():
    common = Settings()
    return {
        "AWS_ENDPOINT_URL_S3": common.aws_endpoint_url_s3,
        "AVATAR_BUCKET": common.avatar_bucket,
    }


def storage_settings():
    """Upload-only settings; normal image URLs do not require credentials."""
    common = Settings()
    return {
        **public_storage_settings(),
        "AWS_ACCESS_KEY_ID": common.aws_access_key_id,
        "AWS_SECRET_ACCESS_KEY": common.aws_secret_access_key,
        "AWS_REGION": common.aws_region,
    }

def public_base():
    values = public_storage_settings()
    endpoint = (values.get("AWS_ENDPOINT_URL_S3") or "").rstrip("/")
    bucket = values.get("AVATAR_BUCKET") or "artists-avator"
    return f"{endpoint}/{bucket}/" if endpoint else ""

def avatar_variants(url, base=None):
    base = public_base() if base is None else base
    if not url or not base or not url.startswith(base) or not PATH_PATTERN.fullmatch(url[len(base):]):
        return {}
    return {str(size): url.rsplit("/", 1)[0] + f"/{size}.webp" for size in SIZES}
