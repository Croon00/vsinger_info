"""Explicit avatar migration. prepare is local-only; apply uploads then updates matching rows."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import httpx
from sqlalchemy import text
from app.db.catalog_session import catalog_engine, catalog_url
from app.services.avatar_assets import SIZES, avatar_variants
from app.services.avatar_storage import public_url, download, variants, storage, image_prefix, upload

WORK = ROOT / "db-migration/workspace/avatars"

def save_report(path, report):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)

def prepare_item(row):
    item = dict(row)
    if avatar_variants(item["source"]):
        return {**item, "status": "already_managed"}
    try:
        data = download(item["source"])
        generated = variants(data)
        # Hash the output too: encoder/settings changes produce a different immutable URL.
        prefix = image_prefix(item['id'], data, generated)
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
            new_url = upload(prefix, (folder / 'original').read_bytes(),
                {s: (folder / f'{s}.webp').read_bytes() for s in SIZES}, client=client, bucket=bucket)
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
