"""Read-only YouTube channel research. Never writes to a database or sends notifications."""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.core.config import settings
from app.integrations.youtube_catalog import YouTubeClient, YouTubeFailure, SINGING

def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def summarize(seed, output):
    """Export observed channel statistics and title-rule candidates, not song statistics."""
    summaries, candidates = [], []
    for artist in seed["artists"]:
        path = output / (artist["slug"] + ".json")
        result = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        stats = result.get("channel_statistics", {})
        summaries.append(dict(
            name_native=artist["name_native"], name_ko=artist["name_ko"],
            agency=artist.get("agency") or "소속 미확인", group=artist.get("group", ""),
            affiliation_status=artist["affiliation_status"], channel_url=artist["channel_url"],
            subscribers=stats.get("subscriberCount", ""), views=stats.get("viewCount", ""),
            public_video_count=stats.get("videoCount", ""), listed_videos=result.get("listed_videos", ""),
            singing_candidates=result.get("singing_candidates", ""),
            listing_complete=result.get("listing_complete", False), captured_at=result.get("captured_at", ""),
        ))
        for video in result.get("uploads", []):
            if video["singing_candidate"]:
                candidates.append(dict(name_native=artist["name_native"], name_ko=artist["name_ko"],
                                       video_id=video["video_id"], title_native=video["title"],
                                       url="https://www.youtube.com/watch?v=" + video["video_id"],
                                       published_at=video.get("published_at"),
                                       verification_status="title_rule_candidate"))
    output.mkdir(parents=True, exist_ok=True)
    for name, entries in (("channel-statistics.csv", summaries), ("singing-candidates.csv", candidates)):
        with (output / name).open("w", encoding="utf-8-sig", newline="") as file:
            if entries:
                writer = csv.DictWriter(file, fieldnames=list(entries[0]))
                writer.writeheader()
                writer.writerows(entries)
    summary = dict(channels=len(summaries), listings_complete=sum(r["listing_complete"] for r in summaries),
                   singing_candidates=len(candidates), database_applied=False, setlists_collected=False,
                   korean_song_titles_applied=False)
    save(output / "summary.json", summary)
    print(json.dumps(summary))


async def research(seed, output, max_pages):
    provider = YouTubeClient(settings.youtube_api_key)
    failed = False
    for item in seed["artists"]:
        path = output / (item["slug"] + ".json")
        if path.exists():
            prior = json.loads(path.read_text(encoding="utf-8"))
            if prior.get("status") == "resolved" and (not max_pages or prior.get("listing_complete")):
                continue
        result = {**item, "captured_at": datetime.now(UTC).isoformat()}
        try:
            parts = urlparse(item["channel_url"]).path.strip("/").split("/")
            params = {"forHandle": parts[0]} if parts[0].startswith("@") else {"id": parts[1]}
            data = await provider.get("channels", part="snippet,contentDetails,statistics", **params)
            if len(data["items"]) != 1:
                result["status"] = "channel_unavailable"
                failed = True
            else:
                channel = data["items"][0]
                if params.get("id") and channel["id"] != params["id"]:
                    raise YouTubeFailure("channel_mismatch")
                result.update(status="resolved", channel_id=channel["id"],
                              channel_title=channel["snippet"]["title"],
                              description=channel["snippet"].get("description", ""),
                              channel_statistics=channel.get("statistics", {}),
                              canonical_url="https://www.youtube.com/channel/" + channel["id"])
                if max_pages:
                    playlist = channel["contentDetails"]["relatedPlaylists"]["uploads"]
                    entries, seen, token = [], set(), None
                    for _ in range(max_pages):
                        page = await provider.get("playlistItems", part="snippet,contentDetails", playlistId=playlist,
                                                  maxResults=50, **({"pageToken": token} if token else {}))
                        for entry in page["items"]:
                            snippet, content = entry["snippet"], entry["contentDetails"]
                            video_id = content["videoId"]
                            if video_id in seen or snippet.get("videoOwnerChannelId", channel["id"]) != channel["id"]:
                                continue
                            seen.add(video_id)
                            title = snippet["title"]
                            entries.append(dict(video_id=video_id, title=title,
                                                published_at=content.get("videoPublishedAt"),
                                                singing_candidate=any(k in title.casefold() for k in SINGING)))
                        token = page.get("nextPageToken")
                        if not token:
                            break
                    result.update(uploads=entries, listing_complete=not bool(token),
                                  listed_videos=len(entries),
                                  singing_candidates=sum(v["singing_candidate"] for v in entries))
        except YouTubeFailure as exc:
            failed = True
            result.update(status="failed", reason=exc.reason)
            save(path, result)
            if exc.retry:
                print(json.dumps({"slug": item["slug"], "status": "stopped", "reason": exc.reason}), flush=True)
                return 1
        save(path, result)
        print(json.dumps({k: result.get(k) for k in ("slug", "status", "channel_id", "listed_videos", "singing_candidates")}), flush=True)
    return int(failed)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=Path, default=ROOT / "data/seeds/requested_vsingers_2026_10_02.json")
    parser.add_argument("--output", type=Path, default=ROOT / "db-migration/reports/requested-vsingers-2026-10-02")
    parser.add_argument("--max-pages", type=int, default=0, help="0: channel resolution only; otherwise bounded uploads listing")
    parser.add_argument("--report-only", action="store_true", help="Export local CSVs without API or DB calls")
    args = parser.parse_args()
    if not 0 <= args.max_pages <= 400:
        parser.error("max-pages must be between 0 and 400")
    seed = json.loads(args.seed.read_text(encoding="utf-8"))
    if args.report_only:
        summarize(seed, args.output)
        return 0
    return asyncio.run(research(seed, args.output, args.max_pages))


if __name__ == "__main__":
    raise SystemExit(main())
