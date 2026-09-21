"""Register five reviewed YouTube sub channels and reorder their X links.

The command previews by default. With --apply it writes one audited catalog
transaction: create the YouTube account and owner link at position 1, then move
the existing X link from position 1 to position 2. It never opens the legacy DB.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import uuid
from pathlib import Path

import psycopg
from dotenv import dotenv_values
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


ROOT = Path(__file__).resolve().parents[1]
OPERATION_ID = uuid.UUID("9e7c8c8e-3859-4b81-9d1e-e5a31025db71")
PROPOSALS = (
    {"artist": "花譜", "platform_id": "UCkJYa9mVS25eHOO9bM7YK3Q", "handle": "@kaf_sub",
     "url": "https://www.youtube.com/@kaf_sub", "uploads_playlist_id": "UUkJYa9mVS25eHOO9bM7YK3Q"},
    {"artist": "ヰ世界情緒", "platform_id": "UC3VN9h8fokwB2XURWHNcdWw", "handle": "@isekaijoucho_sub",
     "url": "https://www.youtube.com/@isekaijoucho_sub", "uploads_playlist_id": "UU3VN9h8fokwB2XURWHNcdWw"},
    {"artist": "理芽", "platform_id": "UCZYl1o6ftRLKZP6U4KjQl3g", "handle": "@rimstrangegirlclub",
     "url": "https://www.youtube.com/@rimstrangegirlclub", "uploads_playlist_id": "UUZYl1o6ftRLKZP6U4KjQl3g"},
    {"artist": "春猿火", "platform_id": "UC5BzXtjnKt1fjEDjEJwx5JA", "handle": "@harusaruhi_club",
     "url": "https://www.youtube.com/@harusaruhi_club", "uploads_playlist_id": "UU5BzXtjnKt1fjEDjEJwx5JA"},
    {"artist": "幸祜", "platform_id": "UCyCbd63S29BuFOkJC2-aR4g", "handle": "@koko_subchannel",
     "url": "https://www.youtube.com/@koko_subchannel", "uploads_playlist_id": "UUyCbd63S29BuFOkJC2-aR4g"},
)


def catalog_url() -> str:
    value = (dotenv_values(ROOT / ".env.catalog").get("NEW_CATALOG_DATABASE_URL") or "").strip()
    if not value:
        raise RuntimeError("NEW_CATALOG_DATABASE_URL is not configured")
    return value


def setup(conn, *, read_only: bool) -> None:
    if read_only:
        conn.execute("SET TRANSACTION READ ONLY")
    conn.execute("SET LOCAL search_path=public,pg_catalog")
    conn.execute("SET LOCAL statement_timeout='60s'")
    conn.execute("SET LOCAL lock_timeout='10s'")


def inspect(conn, *, lock: bool) -> tuple[str, list[dict]]:
    suffix = " FOR UPDATE" if lock else ""
    identity = str(conn.execute("SELECT id FROM catalog_instance" + suffix).fetchone()["id"])
    result = []
    for proposal in PROPOSALS:
        artists = conn.execute(
            "SELECT id,name_native FROM artists WHERE name_native=%s AND archived_at IS NULL" + suffix,
            (proposal["artist"],),
        ).fetchall()
        if len(artists) != 1:
            raise RuntimeError(f"Expected one active artist for {proposal['artist']}")
        artist_id = artists[0]["id"]
        existing_account = conn.execute(
            "SELECT id FROM external_accounts WHERE platform='youtube' AND platform_id=%s" + suffix,
            (proposal["platform_id"],),
        ).fetchall()
        handle_collision = conn.execute(
            "SELECT id,platform_id FROM external_accounts WHERE platform='youtube' AND lower(handle)=lower(%s)" + suffix,
            (proposal["handle"],),
        ).fetchall()
        primary = conn.execute(
            """SELECT ae.id,e.id AS account_id,e.handle,ae.position
               FROM artist_external_accounts ae JOIN external_accounts e ON e.id=ae.account_id
               WHERE ae.artist_id=%s AND e.platform='youtube' AND ae.is_primary=true""" + suffix,
            (artist_id,),
        ).fetchall()
        x_links = conn.execute(
            """SELECT ae.id,e.id AS account_id,e.handle,ae.position
               FROM artist_external_accounts ae JOIN external_accounts e ON e.id=ae.account_id
               WHERE ae.artist_id=%s AND e.platform='x'""" + suffix,
            (artist_id,),
        ).fetchall()
        if not existing_account and handle_collision:
            raise RuntimeError(f"YouTube handle collision for {proposal['artist']}")
        if len(primary) != 1 or primary[0]["position"] != 0:
            raise RuntimeError(f"Expected one primary YouTube link at position 0 for {proposal['artist']}")
        if len(x_links) != 1 or x_links[0]["position"] != 1:
            raise RuntimeError(f"Expected one X link at position 1 for {proposal['artist']}")
        result.append({
            **proposal,
            "artist_id": artist_id,
            "existing_account_id": existing_account[0]["id"] if existing_account else None,
            "primary_youtube_link_id": primary[0]["id"],
            "primary_youtube_handle": primary[0]["handle"],
            "x_link_id": x_links[0]["id"],
            "x_account_id": x_links[0]["account_id"],
            "x_handle": x_links[0]["handle"],
            "x_position_before": x_links[0]["position"],
        })
    return identity, result


def manifest(identity: str, rows: list[dict]) -> dict:
    return {
        "catalog_id": identity,
        "operation": "register_youtube_sub_accounts_v1",
        "youtube_label": "YouTube sub",
        "youtube_position": 1,
        "x_position": 2,
        "rows": rows,
    }


def verify_applied(conn) -> dict:
    verified = []
    for proposal in PROPOSALS:
        row = conn.execute(
            """SELECT a.id AS artist_id,e.id AS account_id,e.handle,e.collection_enabled,
                      ae.relationship,ae.is_primary,ae.label,ae.position,
                      (SELECT count(*) FROM artist_external_accounts xae
                       JOIN external_accounts xe ON xe.id=xae.account_id
                       WHERE xae.artist_id=a.id AND xe.platform='x' AND xae.position=2) AS x_at_two
               FROM artists a
               JOIN artist_external_accounts ae ON ae.artist_id=a.id
               JOIN external_accounts e ON e.id=ae.account_id
               WHERE a.name_native=%s AND e.platform='youtube' AND e.platform_id=%s""",
            (proposal["artist"], proposal["platform_id"]),
        ).fetchall()
        if len(row) != 1:
            raise RuntimeError(f"Registered account verification failed for {proposal['artist']}")
        value = row[0]
        if not (
            value["handle"] == proposal["handle"]
            and value["collection_enabled"] is True
            and value["relationship"] == "owner"
            and value["is_primary"] is False
            and value["label"] == "YouTube sub"
            and value["position"] == 1
            and value["x_at_two"] == 1
        ):
            raise RuntimeError(f"Registered relationship differs for {proposal['artist']}")
        verified.append(proposal["artist"])
    return {"verified_accounts": len(verified), "verified_artists": verified}


def digest(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def apply(conn, payload: dict, manifest_hash: str) -> dict:
    existing = conn.execute(
        "SELECT manifest_hash,result_summary FROM catalog_imports WHERE operation_id=%s",
        (OPERATION_ID,),
    ).fetchone()
    if existing:
        if existing["manifest_hash"] != manifest_hash:
            raise RuntimeError("Existing operation receipt has a different manifest")
        return {"already_applied": True, **existing["result_summary"]}
    if any(row["existing_account_id"] is not None for row in payload["rows"]):
        raise RuntimeError("A proposed YouTube account already exists without this receipt")

    changes = []
    mapping = []
    for row in payload["rows"]:
        before_x = conn.execute(
            "SELECT to_jsonb(aea) AS data FROM artist_external_accounts aea WHERE id=%s FOR UPDATE",
            (row["x_link_id"],),
        ).fetchone()["data"]
        after_x = conn.execute(
            """UPDATE artist_external_accounts
               SET position=2,updated_at=clock_timestamp()
               WHERE id=%s AND position=1 RETURNING to_jsonb(artist_external_accounts) AS data""",
            (row["x_link_id"],),
        ).fetchone()
        if not after_x:
            raise RuntimeError("X link position changed after preview")
        account = conn.execute(
            """INSERT INTO external_accounts
               (platform,platform_id,handle,url,collection_enabled)
               VALUES ('youtube',%s,%s,%s,true)
               RETURNING to_jsonb(external_accounts) AS data""",
            (row["platform_id"], row["handle"], row["url"]),
        ).fetchone()["data"]
        link = conn.execute(
            """INSERT INTO artist_external_accounts
               (artist_id,account_id,relationship,is_primary,label,position)
               VALUES (%s,%s,'owner',false,'YouTube sub',1)
               RETURNING to_jsonb(artist_external_accounts) AS data""",
            (row["artist_id"], account["id"]),
        ).fetchone()["data"]
        changes.extend([
            ("artist_external_accounts", row["x_link_id"], "update", before_x, after_x["data"],
             {"reason": "make room for reviewed YouTube sub account at position 1"}),
            ("external_accounts", account["id"], "create", None, account,
             {"youtube_channel_id": row["platform_id"], "uploads_playlist_id": row["uploads_playlist_id"]}),
            ("artist_external_accounts", link["id"], "create", None, link,
             {"artist": row["artist"], "reviewed_label": "YouTube sub"}),
        ])
        mapping.extend([
            {"entity_type": "external_accounts", "entity_id": account["id"], "version": account["version"]},
            {"entity_type": "artist_external_accounts", "entity_id": link["id"]},
            {"entity_type": "artist_external_accounts", "entity_id": row["x_link_id"]},
        ])

    summary = {
        "created_youtube_accounts": len(payload["rows"]),
        "created_artist_links": len(payload["rows"]),
        "moved_x_links": len(payload["rows"]),
    }
    receipt_id = conn.execute(
        """INSERT INTO catalog_imports
           (operation_id,catalog_instance_id,manifest_hash,source_kind,result_mapping,result_summary)
           VALUES (%s,%s,%s,'manual',%s,%s) RETURNING id""",
        (OPERATION_ID, payload["catalog_id"], manifest_hash, Jsonb(mapping), Jsonb(summary)),
    ).fetchone()["id"]
    for entity_type, entity_id, action, before, after, provenance in changes:
        conn.execute(
            """INSERT INTO catalog_changes
               (import_id,entity_type,entity_id,action,before_data,after_data,provenance)
               VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (receipt_id, entity_type, entity_id, action,
             Jsonb(before) if before is not None else None,
             Jsonb(after) if after is not None else None,
             Jsonb(provenance)),
        )
    return {"already_applied": False, **summary}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    with psycopg.connect(catalog_url(), connect_timeout=20, row_factory=dict_row) as conn:
        setup(conn, read_only=not args.apply)
        if args.apply:
            receipt = conn.execute(
                "SELECT result_summary FROM catalog_imports WHERE operation_id=%s",
                (OPERATION_ID,),
            ).fetchone()
            if receipt:
                verification = verify_applied(conn)
                print(json.dumps({"mode": "apply", "already_applied": True,
                                  **receipt["result_summary"], **verification}))
                return 0
        else:
            receipt = conn.execute(
                "SELECT result_summary FROM catalog_imports WHERE operation_id=%s",
                (OPERATION_ID,),
            ).fetchone()
            if receipt:
                verification = verify_applied(conn)
                print(json.dumps({"mode": "verify", "already_applied": True,
                                  **receipt["result_summary"], **verification}))
                return 0
        identity, rows = inspect(conn, lock=args.apply)
        payload = manifest(identity, rows)
        manifest_hash = digest(payload)
        preview = {
            "artists": [row["artist"] for row in rows],
            "youtube_accounts_to_create": sum(row["existing_account_id"] is None for row in rows),
            "x_links_to_move": sum(row["x_position_before"] == 1 for row in rows),
            "label": "YouTube sub",
            "youtube_position": 1,
            "x_position": 2,
            "manifest_hash": manifest_hash,
        }
        if not args.apply:
            print(json.dumps({"mode": "preview", **preview}))
            return 0
        result = apply(conn, payload, manifest_hash)
        print(json.dumps({"mode": "apply", **preview, **result}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
