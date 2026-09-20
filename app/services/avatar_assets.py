"""Managed avatar URL contract; no storage or image I/O in read requests."""
import os
import re
from pathlib import Path
from dotenv import dotenv_values

SIZES = (128, 256, 512)
CACHE_CONTROL = "public, max-age=31536000, immutable"
PATH_PATTERN = re.compile(r"avatars/v1/[0-9]+/[a-f0-9]{32}/512\.webp$")

def storage_settings():
    values = dict(dotenv_values(Path(__file__).resolve().parents[2] / ".env.catalog"))
    for key in ("AWS_ENDPOINT_URL_S3", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_REGION", "AVATAR_BUCKET"):
        if key in os.environ:
            values[key] = os.environ[key]
    return values

def public_base():
    values = storage_settings()
    endpoint = (values.get("AWS_ENDPOINT_URL_S3") or "").rstrip("/")
    bucket = values.get("AVATAR_BUCKET") or "artists-avator"
    return f"{endpoint}/{bucket}/" if endpoint else ""

def avatar_variants(url, base=None):
    base = public_base() if base is None else base
    if not url or not base or not url.startswith(base) or not PATH_PATTERN.fullmatch(url[len(base):]):
        return {}
    return {str(size): url.rsplit("/", 1)[0] + f"/{size}.webp" for size in SIZES}
