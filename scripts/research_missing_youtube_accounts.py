"""Research proposed catalog rows for known legacy YouTube monitors.

This command calls the official YouTube Data API and opens the catalog in a
read-only transaction. It writes a public-metadata-only proposal under the
git-ignored readiness report directory and never changes either database.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx
import psycopg
from dotenv import dotenv_values
from psycopg.rows import dict_row


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "db-migration" / "reports" / "single-db-readiness" / "youtube-account-proposal.json"
CHANNELS = {
    "UCkJYa9mVS25eHOO9bM7YK3Q": "花譜",
    "UC3VN9h8fokwB2XURWHNcdWw": "ヰ世界情緒",
    "UCZYl1o6ftRLKZP6U4KjQl3g": "理芽",
    "UC5BzXtjnKt1fjEDjEJwx5JA": "春猿火",
    "UCyCbd63S29BuFOkJC2-aR4g": "幸祜",
}


def configured(name: str, filename: str) -> str:
    value = (os.environ.get(name) or dotenv_values(ROOT / filename).get(name) or "").strip()
    if not value:
        raise RuntimeError(f"{name} is not configured")
    return value


def main() -> int:
    api_key = configured("YOUTUBE_API_KEY", ".env")
    catalog_url = configured("DATABASE_URL", ".env")
    response = httpx.get(
        "https://www.googleapis.com/youtube/v3/channels",
        params={
            "part": "snippet,contentDetails",
            "id": ",".join(CHANNELS),
            "key": api_key,
            "maxResults": 50,
        },
        timeout=30,
    )
    response.raise_for_status()
    items = {item["id"]: item for item in response.json().get("items", [])}
    if set(items) != set(CHANNELS):
        missing = sorted(set(CHANNELS) - set(items))
        raise RuntimeError("YouTube API omitted configured channel IDs: " + ",".join(missing))

    proposals = []
    with psycopg.connect(catalog_url, connect_timeout=20, row_factory=dict_row) as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        conn.execute("SET LOCAL search_path=public,pg_catalog")
        conn.execute("SET LOCAL statement_timeout='30s'")
        for channel_id, artist_name in CHANNELS.items():
            channel = items[channel_id]
            snippet = channel.get("snippet") or {}
            artist_rows = [dict(row) for row in conn.execute(
                """SELECT DISTINCT a.id,a.slug,a.name_native,a.name_ko,a.name_latin
                   FROM artists a
                   LEFT JOIN artist_aliases aa ON aa.artist_id=a.id
                   WHERE lower(a.name_native)=lower(%s)
                      OR lower(COALESCE(a.name_ko,''))=lower(%s)
                      OR lower(COALESCE(a.name_latin,''))=lower(%s)
                      OR lower(COALESCE(aa.alias,''))=lower(%s)
                   ORDER BY a.id""",
                (artist_name, artist_name, artist_name, artist_name),
            ).fetchall()]
            existing = []
            if len(artist_rows) == 1:
                existing = [dict(row) for row in conn.execute(
                    """SELECT e.id,e.platform_id,e.handle,e.url,e.collection_enabled,e.archived_at,
                              ae.relationship,ae.is_primary,ae.label,ae.position
                       FROM artist_external_accounts ae
                       JOIN external_accounts e ON e.id=ae.account_id
                       WHERE ae.artist_id=%s AND e.platform='youtube'
                       ORDER BY ae.position,e.id""",
                    (artist_rows[0]["id"],),
                ).fetchall()]
            custom_url = snippet.get("customUrl")
            handle = custom_url if custom_url and custom_url.startswith("@") else None
            canonical_url = (
                "https://www.youtube.com/" + handle
                if handle else "https://www.youtube.com/channel/" + channel_id
            )
            proposals.append({
                "platform": "youtube",
                "platform_id": channel_id,
                "handle": handle,
                "url": canonical_url,
                "collection_enabled": True,
                "official_title": snippet.get("title"),
                "official_custom_url": custom_url,
                "uploads_playlist_id": ((channel.get("contentDetails") or {}).get("relatedPlaylists") or {}).get("uploads"),
                "country": snippet.get("country"),
                "published_at": snippet.get("publishedAt"),
                "artist_lookup": artist_name,
                "artist_candidates": artist_rows,
                "existing_youtube_accounts": existing,
                "proposed_relationship": "owner",
                "proposed_is_primary": not any(row["is_primary"] for row in existing),
                "proposed_position": max((row["position"] for row in existing), default=-1) + 1,
                "proposed_label": "YouTube Sub Channel" if existing else "YouTube",
            })
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "YouTube Data API channels.list(part=snippet,contentDetails)",
        "proposals": proposals,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({
        "ok": True,
        "proposal_count": len(proposals),
        "unique_artist_matches": sum(len(row["artist_candidates"]) == 1 for row in proposals),
        "handles_found": sum(bool(row["handle"]) for row in proposals),
        "report": REPORT.relative_to(ROOT).as_posix(),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
