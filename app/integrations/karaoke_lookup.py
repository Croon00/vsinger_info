from __future__ import annotations

import json
import re
from dataclasses import dataclass

from openai import AsyncOpenAI

from app.core.config import settings
from app.integrations.jpop_playlist_tj import cached_jpop_playlist_matches


@dataclass(frozen=True)
class KaraokeMatch:
    song_title: str
    original_artist: str | None
    tj_number: str
    ky_number: str


def split_song_credit(value: str) -> tuple[str, str | None]:
    """Split common setlist forms such as `song / artist` without requiring a credit."""
    cleaned = value.strip()
    for separator in (" / ", " ／ ", "｜", " | ", "/", "／"):
        if separator in cleaned:
            title, artist = cleaned.rsplit(separator, 1)
            if title.strip() and artist.strip():
                return title.strip(), artist.strip()
            if title.strip() and not artist.strip():
                return title.strip(), None
    match = re.match(r"^(?P<title>.+?)\s+[（(](?:原曲|original)[:：]?\s*(?P<artist>.+?)[）)]$", cleaned, re.I)
    if match:
        return match.group("title").strip(), match.group("artist").strip()
    return cleaned, None


async def lookup_karaoke_numbers(songs: list[tuple[str, str | None]]) -> list[KaraokeMatch]:
    """Use web search to verify TJ/KY registrations; unknown entries stay 등록X."""
    defaults = [KaraokeMatch(title, artist, "등록X", "등록X") for title, artist in songs]
    source_matches = cached_jpop_playlist_matches(songs)
    for index, source_match in source_matches.items():
        defaults[index] = KaraokeMatch(
            songs[index][0], songs[index][1] or source_match.artist, source_match.tj_number, "등록X"
        )
    if len(source_matches) == len(songs):
        return defaults
    if not songs or not settings.openai_api_key:
        return defaults

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    numbered = "\n".join(
        f"{index}. 곡명={title}; 원곡가수={artist or '미상'}"
        for index, (title, artist) in enumerate(songs)
    )
    try:
        response = await client.responses.create(
            model=settings.openai_model,
            tools=[{"type": "web_search_preview"}],
            input=(
                "다음 곡들이 한국 노래방 TJ미디어 또는 금영엔터테인먼트(KY)에 등록되어 있는지 "
                "웹 검색으로 확인하세요. 공식 TJ/금영 검색 결과를 우선하고 번호를 추측하지 마세요. "
                "확인되지 않거나 미등록이면 반드시 '등록X'로 쓰세요. 입력 순서를 유지한 JSON 배열만 반환하세요. "
                "각 원소 키는 song_title, original_artist(null 가능), tj_number, ky_number 입니다.\n" + numbered
            ),
        )
        raw = response.output_text.strip()
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
        data = json.loads(raw)
        if not isinstance(data, list) or len(data) != len(songs):
            return defaults
        searched = [
            KaraokeMatch(
                song_title=str(item.get("song_title") or songs[index][0]).strip(),
                original_artist=(str(item["original_artist"]).strip() if item.get("original_artist") else songs[index][1]),
                tj_number=str(item.get("tj_number") or "등록X").strip(),
                ky_number=str(item.get("ky_number") or "등록X").strip(),
            )
            for index, item in enumerate(data)
        ]
        return [defaults[index] if index in source_matches else searched[index] for index in range(len(songs))]
    except Exception:
        return defaults
