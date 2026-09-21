"""AI extraction retained only for the independent YouTube setlist workflow."""
from __future__ import annotations

import json
import logging
import re

from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import settings

logger = logging.getLogger(__name__)


def openai_configured() -> bool:
    return bool(settings.openai_api_key)


class YouTubeSetlistEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    timestamp: str = Field(min_length=3, max_length=12)
    song_title: str = Field(min_length=1, max_length=300)
    original_artist: str | None = Field(..., max_length=300)


class YouTubeSetlistExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    songs: list[YouTubeSetlistEntry] = Field(..., max_length=200)


YOUTUBE_SETLIST_SCHEMA = {
    "name": "youtube_setlist_extraction",
    "schema": YouTubeSetlistExtraction.model_json_schema(),
    "strict": True,
}
YOUTUBE_SETLIST_MAX_OUTPUT_TOKENS = 4000


async def extract_youtube_setlist(comment: str) -> list[dict[str, str | None]] | None:
    """Extract song rows from an independent YouTube setlist comment."""
    if not settings.openai_api_key or not comment.strip():
        return None
    client = AsyncOpenAI(api_key=settings.openai_api_key, timeout=30.0, max_retries=0)
    try:
        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You clean one YouTube singing-stream setlist comment. "
                        "Return only songs the streamer actually sang. Ignore START, END, "
                        "opening/closing, MC, greetings, links, hashtags, viewer counts, "
                        "scores, timestamps without a song, and explanatory text. Do not "
                        "invent a song or artist. Keep each starting timestamp exactly as "
                        "written and set original_artist only when explicitly stated."
                    ),
                },
                {"role": "user", "content": f"Setlist comment:\n{comment}"},
            ],
            response_format={"type": "json_schema", "json_schema": YOUTUBE_SETLIST_SCHEMA},
            max_tokens=YOUTUBE_SETLIST_MAX_OUTPUT_TOKENS,
        )
        content = response.choices[0].message.content
        if not content:
            return None
        result = YouTubeSetlistExtraction.model_validate(json.loads(content))
    except Exception as exc:
        logger.warning("YouTube setlist AI extraction failed: %s", exc)
        return None

    entries: list[dict[str, str | None]] = []
    seen: set[tuple[str, str]] = set()
    timestamp_pattern = re.compile(r"^(?:\d{1,2}:)?[0-5]?\d:[0-5]\d$")
    for entry in result.songs:
        timestamp = entry.timestamp.strip()
        title = entry.song_title.strip()
        if not timestamp_pattern.fullmatch(timestamp) or not title:
            continue
        key = (timestamp, title.casefold())
        if key in seen:
            continue
        seen.add(key)
        entries.append({
            "timestamp": timestamp,
            "title": title,
            "original_artist": entry.original_artist.strip() if entry.original_artist else None,
        })
    return entries
