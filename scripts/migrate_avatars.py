"""Explicit avatar migration. prepare is local-only; apply uploads then updates matching rows."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
import ipaddress
import json
from pathlib import Path
import socket
import sys
from urllib.parse import urlsplit, urljoin
import warnings

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import boto3
from botocore.config import Config
import httpx
from PIL import Image, ImageOps
from sqlalchemy import text
from app.db.catalog_session import catalog_engine, catalog_url
from app.services.avatar_assets import SIZES, CACHE_CONTROL, storage_settings, public_base, avatar_variants

Image.MAX_IMAGE_PIXELS = 40_000_000
warnings.simplefilter("error", Image.DecompressionBombWarning)
MAX_BYTES = 20 * 1024 * 1024
WORK = ROOT / "db-migration/workspace/avatars"

def save_report(path, report):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)

def public_url(url):
    parsed = urlsplit(url)
    if parsed.scheme not in ("https", "http") or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("invalid_source_url")
    if parsed.port not in (None, 80, 443):
        raise ValueError("unsupported_source_port")
    addresses = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError("non_public_source")
    return url

def download(url):
    with httpx.Client(timeout=httpx.Timeout(20, connect=10), headers={"User-Agent": "schedule-music-avatar-import/1.0"}) as client:
        for _ in range(6):
            public_url(url)
            with client.stream("GET", url) as response:
                if response.is_redirect:
                    url = urljoin(url, response.headers["location"])
                    continue
                response.raise_for_status()
                data = bytearray()
                for chunk in response.iter_bytes():
                    data.extend(chunk)
                    if len(data) > MAX_BYTES:
                        raise ValueError("source_too_large")
                return bytes(data)
    raise ValueError("too_many_redirects")

def variants(data):
    with Image.open(BytesIO(data)) as source:
        source.load()
        image = ImageOps.exif_transpose(source).convert("RGBA" if "A" in source.getbands() else "RGB")
        result = {}
        for size in SIZES:
            copy = image.copy()
            copy.thumbnail((size, size), Image.Resampling.LANCZOS)
            output = BytesIO()
            copy.save(output, format="WEBP", quality=85, method=6)
            result[size] = output.getvalue()
        return result

def prepare_item(row):
    item = dict(row)
    if avatar_variants(item["source"]):
        return {**item, "status": "already_managed"}
    try:
        data = download(item["source"])
        generated = variants(data)
        # Hash the output too: encoder/settings changes produce a different immutable URL.
        digest = sha256(data + b"".join(generated.values())).hexdigest()[:32]
        prefix = f"avatars/v1/{item['id']}/{digest}"
        folder = WORK / prefix
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "original").write_bytes(data)
        for size, content in generated.items():
            (folder / f"{size}.webp").write_bytes(content)
        return {**item, "status": "prepared", "prefix": prefix,
                "source_bytes": len(data), "variant_bytes": {str(s):len(b) for s,b in generated.items()}}
    except Exception as exc:
        reason = f"http_{exc.response.status_code}" if isinstance(exc, httpx.HTTPStatusError) else type(exc).__name__
        return {**item, "status": "failed_download", "reason": reason}

def prepare(args):
    with catalog_engine(catalog_url()).connect() as conn:
        rows = [dict(r) for r in conn.execute(text(
            "SELECT id, avatar_url AS source FROM artists WHERE avatar_url IS NOT NULL AND avatar_url <> ''"
            + (" AND id=:id" if args.artist_id else "") + " ORDER BY id"),
            {"id":args.artist_id}).mappings()]
    if args.source_url:
        if not args.artist_id or len(rows) != 1:
            raise ValueError("--source-url requires one existing artist with an avatar")
        rows[0]["previous_url"] = rows[0]["source"]
        rows[0]["source"] = args.source_url
    report = {"created_at":datetime.now(timezone.utc).isoformat(), "items":[]}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for item in pool.map(prepare_item, rows):
            report["items"].append(item)
            save_report(args.report, report)
            print(f"artist {item['id']}: {item['status']}", flush=True)
    print(json.dumps(dict(Counter(i["status"] for i in report["items"]))))

def storage():
    settings = storage_settings()
    required = ("AWS_ENDPOINT_URL_S3","AWS_ACCESS_KEY_ID","AWS_SECRET_ACCESS_KEY","AWS_REGION")
    if any(not settings.get(k) for k in required):
        raise ValueError("missing_storage_configuration")
    client = boto3.client("s3", endpoint_url=settings["AWS_ENDPOINT_URL_S3"],
        aws_access_key_id=settings["AWS_ACCESS_KEY_ID"], aws_secret_access_key=settings["AWS_SECRET_ACCESS_KEY"],
        region_name=settings["AWS_REGION"], config=Config(signature_version="s3v4", s3={"addressing_style":"path"},
            connect_timeout=10, read_timeout=30, retries={"max_attempts":3,"mode":"standard"},
            request_checksum_calculation="when_required", response_checksum_validation="when_required"))
    return client, settings.get("AVATAR_BUCKET") or "artists-avator"

def apply(args):
    report = json.loads(args.report.read_text(encoding="utf-8"))
    client, bucket = storage()
    client.head_bucket(Bucket=bucket)
    engine = catalog_engine(catalog_url())
    for item in report["items"]:
        if item["status"] not in ("prepared", "uploaded", "failed_apply"):
            continue
        try:
            prefix = item["prefix"]
            folder = WORK / prefix
            for filename in ("original", *(f"{s}.webp" for s in SIZES)):
                content = (folder / filename).read_bytes()
                client.put_object(Bucket=bucket, Key=f"{prefix}/{filename}", Body=content,
                    ContentType="image/webp" if filename.endswith(".webp") else "application/octet-stream",
                    CacheControl=CACHE_CONTROL)
            new_url = public_base() + prefix + "/512.webp"
            # Verify ALL sizes anonymously before publishing an address in the DB.
            with httpx.Client(timeout=20) as http:
                for size in SIZES:
                    response = http.get(public_base() + prefix + f"/{size}.webp")
                    if response.status_code == 403:
                        item["status"] = "uploaded"
                        save_report(args.report, report)
                        raise ValueError("bucket_requires_public_read")
                    response.raise_for_status()
                    if response.content != (folder / f"{size}.webp").read_bytes():
                        raise ValueError("public_content_mismatch")
                    if response.headers.get("cache-control") != CACHE_CONTROL:
                        raise ValueError("cache_control_mismatch")
            # Persist rollback information before the short transaction.
            item["new_url"] = new_url
            item["status"] = "uploaded"
            save_report(args.report, report)
            with engine.begin() as conn:
                current = conn.execute(text("SELECT avatar_url FROM artists WHERE id=:id FOR UPDATE"),
                    {"id":item["id"]}).scalar_one()
                if current == new_url:
                    item["status"] = "applied"
                elif current != item.get("previous_url", item["source"]):
                    item["status"] = "conflict"
                else:
                    conn.execute(text("UPDATE artists SET avatar_url=:url, updated_at=clock_timestamp() WHERE id=:id"),
                        {"id":item["id"],"url":new_url})
                    item["status"] = "applied"
        except Exception as exc:
            item["status"] = "failed_apply"
            item["reason"] = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
            # Never print SDK/DB exception strings: they can contain credentials or signed URLs.
            print(f"artist {item['id']}: {item['reason']}", flush=True)
            save_report(args.report, report)
            if item["reason"] == "bucket_requires_public_read":
                raise SystemExit("Set the avatar bucket to public_read in Neon Console, then rerun apply.")
            continue
        save_report(args.report, report)
        print(f"artist {item['id']}: {item['status']}", flush=True)
    print(json.dumps(dict(Counter(i["status"] for i in report["items"]))))

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare","apply"])
    parser.add_argument("--report", type=Path, default=WORK/"migration.json")
    parser.add_argument("--artist-id", type=int)
    parser.add_argument("--source-url")
    args = parser.parse_args()
    if args.action == "prepare" and args.report.exists():
        parser.error("Report exists; choose a new --report to preserve migration/rollback history.")
    try:
        (prepare if args.action == "prepare" else apply)(args)
    except Exception as exc:
        print(f"Migration stopped: {type(exc).__name__}", file=sys.stderr)
        raise SystemExit(1) from None

if __name__ == "__main__":
    main()
