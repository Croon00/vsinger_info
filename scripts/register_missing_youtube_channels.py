"""Register verified catalogue channels that do not already have a monitor.

Preview by default. --apply adds only missing monitors, preserving existing
owners and disabled monitors. No Discord messages or calendar events are sent.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.artist_identity import artist_name_aliases, name_key
from app.core.db import get_connection
from app.integrations.youtube_channel_monitor import (
    create_youtube_channel_monitor,
    resolve_youtube_channel,
)

DEFAULT_SEEDS = (
    PROJECT_ROOT / "data/seeds/rkmusic_missing_youtube_channels.json",
    PROJECT_ROOT / "data/seeds/kamitsubaki_missing_youtube_channels.json",
)


def matching_names(name: str) -> set[str]:
    return {name_key(alias) for alias in artist_name_aliases(name)}


def registration_action(
    entry: dict[str, Any],
    artists: list[dict[str, Any]],
    monitors: list[dict[str, Any]],
    channel_id: str | None = None,
) -> str:
    """Match curated aliases and shared channels without merging artist rows."""
    aliases = matching_names(entry["artist_name"])
    if not any(aliases.intersection(matching_names(artist["name"])) for artist in artists):
        return "missing_artist"
    for monitor in monitors:
        if aliases.intersection(matching_names(monitor["artist_name"])) or (
            channel_id and monitor["youtube_channel_id"] == channel_id
        ):
            return "already_registered" if monitor["is_active"] else "disabled"
    return "register"


async def register_missing(
    entries: list[dict[str, Any]], *, apply: bool, owner: str
) -> list[dict[str, Any]]:
    with get_connection() as conn:
        artists = conn.execute("SELECT name FROM artists").fetchall()
        monitors = conn.execute(
            "SELECT artist_name, youtube_channel_id, is_active FROM youtube_channel_monitors"
        ).fetchall()
    results = []
    for entry in entries:
        result = {"artist_name": entry["artist_name"], "source_url": entry["source_url"]}
        try:
            action = registration_action(entry, artists, monitors)
            if action != "register":
                results.append({**result, "status": action})
                continue
            channel = await resolve_youtube_channel(entry["channel_url"])
            result.update(channel_url=channel["channel_url"], channel_title=channel["channel_title"])
            action = registration_action(entry, artists, monitors, channel["youtube_channel_id"])
            if action == "register":
                if apply:
                    monitor = await create_youtube_channel_monitor(
                        discord_user_id=owner,
                        artist_name=entry["artist_name"],
                        channel_url=channel["channel_url"],
                    )
                    result["monitor_id"] = monitor["id"]
                monitors.append({
                    "artist_name": entry["artist_name"],
                    "youtube_channel_id": channel["youtube_channel_id"],
                    "is_active": True,
                })
                action = "registered" if apply else "would_register"
            results.append({**result, "status": action})
        except Exception as exc:
            # Provider exceptions may contain URLs with API keys.
            results.append({**result, "status": "failed", "error_type": type(exc).__name__})
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=Path, action="append", help="Verified channel JSON list; repeatable.")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--discord-user-id", default="system:catalogue", help="Owner for newly added monitors only.")
    args = parser.parse_args()
    entries = []
    for path in args.seed or DEFAULT_SEEDS:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError(f"Expected a list of verified channels: {path}")
        for entry in payload:
            if not all(isinstance(entry.get(key), str) and entry[key].strip()
                       for key in ("artist_name", "channel_url", "source_url")):
                raise ValueError(f"Invalid verified channel entry: {path}")
        entries.extend(payload)
    results = asyncio.run(register_missing(entries, apply=args.apply, owner=args.discord_user_id))
    print(json.dumps(results, ensure_ascii=True, indent=2))
    return int(any(row["status"] in {"failed", "missing_artist"} for row in results))


if __name__ == "__main__":
    raise SystemExit(main())
