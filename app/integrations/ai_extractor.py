from __future__ import annotations

import json
import logging
import re
from typing import Any, Literal

from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import settings


logger = logging.getLogger(__name__)


ItemType = Literal["notice", "release", "live_event", "ticket", "merch", "irrelevant"]
EventFormat = Literal["onsite", "hybrid", "online", "unknown"]


class SourceItemClassification(BaseModel):
    """새로 수집한 글을 Discord 라우팅용 타입으로 분류한 결과입니다."""

    model_config = ConfigDict(extra="forbid")

    item_type: ItemType
    confidence: float = Field(ge=0, le=1)
    reason_ko: str | None = Field(...)


class MusicEventExtraction(BaseModel):
    """LLM이 추출한 음악 이벤트 후보를 검증하는 Pydantic 모델입니다."""

    model_config = ConfigDict(extra="forbid")

    is_live_event: bool
    event_format: EventFormat = Field(...)
    title: str | None = Field(...)
    title_ko: str | None = Field(...)
    starts_at: str | None = Field(...)
    venue: str | None = Field(...)
    venue_ko: str | None = Field(...)
    ticket_opens_at: str | None = Field(...)
    ticket_closes_at: str | None = Field(...)
    ticket_url: str | None = Field(...)
    price_text: str | None = Field(...)
    ticket_details_ko: str | None = Field(...)
    confidence: float = Field(ge=0, le=1)

    def to_event_candidate(self) -> dict[str, Any] | None:
        """검증된 추출 결과를 DB 저장에 쓰는 일정 후보 dict로 변환합니다."""
        if not self.is_live_event or not self.title or self.confidence < 0.55:
            return None

        event = self.model_dump()
        if self.title_ko:
            event["title"] = self.title_ko
        if self.venue_ko:
            event["venue"] = self.venue_ko
        if self.ticket_details_ko:
            price_text = self.price_text
            event["price_text"] = (
                f"{price_text}\n\n{self.ticket_details_ko}"
                if price_text
                else self.ticket_details_ko
            )
        return event


EVENT_SCHEMA = {
    "name": "music_event_extraction",
    "schema": MusicEventExtraction.model_json_schema(),
    "strict": True,
}

ITEM_CLASSIFICATION_SCHEMA = {
    "name": "source_item_classification",
    "schema": SourceItemClassification.model_json_schema(),
    "strict": True,
}

RULE_KEYWORDS: dict[ItemType, tuple[str, ...]] = {
    "ticket": (
        "チケット",
        "先行",
        "一般販売",
        "抽選",
        "受付",
        "応募",
        "当落",
        "締切",
        "eplus",
        "イープラス",
        "ぴあ",
        "ローチケ",
        "ticket",
    ),
    "live_event": (
        "live",
        "ライブ",
        "公演",
        "開催",
        "出演",
        "fes",
        "フェス",
        "one-man",
        "oneman",
        "ワンマン",
        "two-man",
        "twoman",
        "ツーマン",
        "会場",
        "streaming live",
    ),
    "merch": (
        "グッズ",
        "goods",
        "販売",
        "予約",
        "受注",
        "特典",
        "通販",
        "store",
        "booth",
        "アクリル",
        "缶バッジ",
        "tシャツ",
    ),
    "release": (
        "リリース",
        "配信開始",
        "digital",
        "single",
        "album",
        "ep",
        "mv公開",
        "music video",
        "楽曲",
        "新曲",
    ),
    "notice": (
        "お知らせ",
        "告知",
        "公開",
        "配信",
        "放送",
        "キャンペーン",
        "コラボ",
        "参加",
        "決定",
    ),
    "irrelevant": (),
}


def openai_configured() -> bool:
    """OpenAI API key가 설정되어 AI 추출을 실행할 수 있는지 확인합니다."""
    return bool(settings.openai_api_key)


class YouTubeSetlistEntry(BaseModel):
    """한 영상 댓글에서 확인한 곡 한 줄입니다."""

    model_config = ConfigDict(extra="forbid")

    timestamp: str = Field(min_length=3, max_length=12)
    song_title: str = Field(min_length=1, max_length=300)
    original_artist: str | None = Field(..., max_length=300)


class YouTubeSetlistExtraction(BaseModel):
    """댓글 속 노래 행만 담는 구조화된 셋리스트입니다."""

    model_config = ConfigDict(extra="forbid")

    songs: list[YouTubeSetlistEntry] = Field(..., max_length=200)


YOUTUBE_SETLIST_SCHEMA = {
    "name": "youtube_setlist_extraction",
    "schema": YouTubeSetlistExtraction.model_json_schema(),
    "strict": True,
}

# A long setlist still fits comfortably in this cap while preventing one
# malformed comment from producing an unexpectedly large response bill.
YOUTUBE_SETLIST_MAX_OUTPUT_TOKENS = 4000


async def extract_youtube_setlist(comment: str) -> list[dict[str, str | None]] | None:
    """영상 댓글 전체를 한 번의 LLM 호출로 정제합니다.

    AI가 설정되지 않았거나 유효한 응답을 주지 못하면 ``None``을 반환해,
    호출자가 기존 정규식 파서로 안전하게 되돌아갈 수 있게 합니다.
    """
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
                        "Return only songs the streamer actually sang. "
                        "Ignore START, END, opening/closing, MC, greetings, links, "
                        "hashtags, viewer counts, scores, timestamps without a song, "
                        "and explanatory text. Do not invent a song or artist. "
                        "Keep each song's starting timestamp exactly as written, remove "
                        "numbering and decoration from the title, and set original_artist "
                        "only when the comment explicitly states it."
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


def classify_source_item_by_rules(raw_text: str, page_context: str | None = None) -> SourceItemClassification:
    """LLM 비용을 쓰기 전에 명확한 키워드로 글 타입을 빠르게 분류합니다.

    티켓 공지는 라이브 키워드를 함께 포함하는 경우가 많으므로 ticket을
    live_event보다 먼저 검사합니다. 낮은 confidence는 LLM 재분류 여지를
    남기기 위한 값입니다.
    """
    text = f"{raw_text}\n{page_context or ''}".lower()
    compact_text = re.sub(r"\s+", " ", text)

    for item_type in ("ticket", "live_event", "merch", "release", "notice"):
        for keyword in RULE_KEYWORDS[item_type]:
            if keyword.lower() in compact_text:
                return SourceItemClassification(
                    item_type=item_type,
                    confidence=0.72,
                    reason_ko=f"키워드 `{keyword}`를 기준으로 분류했습니다.",
                )

    return SourceItemClassification(
        item_type="irrelevant",
        confidence=0.55,
        reason_ko="알림이 필요한 키워드를 찾지 못했습니다.",
    )


async def classify_source_item(
    *,
    artist_name: str,
    raw_text: str,
    page_context: str | None = None,
) -> SourceItemClassification:
    """새 글 하나를 notice/release/live_event/ticket/merch/irrelevant로 분류합니다.

    확실한 라이브, 티켓, 굿즈, 릴리즈 글은 룰 결과를 그대로 사용합니다.
    일반 공지나 무관 글처럼 애매한 경우에만 OpenAI가 설정되어 있으면
    LLM 분류를 추가로 수행합니다.
    """
    rule_result = classify_source_item_by_rules(raw_text, page_context)
    if (
        not settings.openai_api_key
        or rule_result.item_type in {"ticket", "live_event", "merch", "release"}
        or rule_result.confidence >= 0.8
    ):
        return rule_result

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    response = await client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {
                "role": "system",
                "content": (
                    "J-pop/virtual artist official posts를 Discord 알림 타입으로 분류하세요. "
                    "item_type은 notice, release, live_event, ticket, merch, irrelevant 중 하나입니다. "
                    "release는 음원/앨범/MV 공개, live_event는 라이브/페스/출연, "
                    "ticket은 선행/일반판매/추첨/응모/마감, merch는 굿즈/상품/특전/예약판매입니다. "
                    "잡담, 단순 인사, 알림 가치가 낮은 글은 irrelevant로 분류하세요."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"아티스트/소스명: {artist_name}\n\n"
                    f"게시글:\n{raw_text}\n\n"
                    f"연결 페이지 본문:\n{page_context or '(없음)'}"
                ),
            },
        ],
        response_format={"type": "json_schema", "json_schema": ITEM_CLASSIFICATION_SCHEMA},
    )
    content = response.choices[0].message.content
    if not content:
        return rule_result
    return SourceItemClassification.model_validate(json.loads(content))


async def extract_music_event(
    artist_name: str,
    raw_text: str,
    page_context: str | None = None,
) -> dict[str, Any] | None:
    """X 게시물 원문에서 공연/예매 일정 정보를 Pydantic 모델로 검증해 추출합니다."""
    if not settings.openai_api_key:
        return None

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    response = await client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {
                "role": "system",
                "content": (
                    "J-pop 라이브, 콘서트, 이벤트, 예매, 응모 일정 정보를 추출하세요. "
                    "event_format은 실제 공연장이 있으면 onsite, 현장 공연과 온라인 중계를 함께 하면 hybrid, "
                    "YouTube Live·歌枠·生配信처럼 온라인 전용이면 online, 근거가 부족하면 unknown으로 반환하세요. "
                    "YouTube 링크가 있어도 실제 회장과 開場/開演 정보가 있으면 온라인 전용으로 판단하지 마세요. "
                    "알 수 없는 필드는 null로 반환하세요. 날짜와 시간은 가능하면 ISO 8601 형식을 사용하세요. "
                    "사용자에게 보이는 제목, 장소, 좌석, 가격, 신청 기간 정보는 한국어로 번역하세요. "
                    "연결된 페이지 문맥에 좌석 종류, 좌석 가격, 신청 시작/종료일, 예매 URL이 있으면 "
                    "ticket_details_ko에 포함하세요."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"아티스트: {artist_name}\n\n게시물\n{raw_text}\n\n"
                    f"연결 페이지 문맥:\n{page_context or '(없음)'}"
                ),
            },
        ],
        response_format={"type": "json_schema", "json_schema": EVENT_SCHEMA},
    )
    content = response.choices[0].message.content
    if not content:
        return None

    extraction = MusicEventExtraction.model_validate(json.loads(content))
    event = extraction.to_event_candidate()
    if event is not None:
        event["event_format"] = infer_event_format(
            raw_text=raw_text,
            page_context=page_context,
            venue=event.get("venue"),
            ticket_url=event.get("ticket_url"),
            model_format=event.get("event_format", "unknown"),
        )
    return event


def infer_event_format(
    *,
    raw_text: str,
    page_context: str | None = None,
    venue: str | None = None,
    ticket_url: str | None = None,
    model_format: EventFormat = "unknown",
) -> EventFormat:
    """Combine deterministic physical/streaming signals with the model result."""
    text = "\n".join(filter(None, (raw_text, page_context, venue, ticket_url))).lower()
    broadcast_signals = (
        "youtube.com/live", "歌枠", "生配信", "オンライン配信",
        "youtube live", "streaming live", "ライブ配信", "配信限定",
    )
    onsite_signals = (
        "開場", "開演", "会場", "現地", "来場", "ライブハウス", "zepp",
        "hall", "ホール", "arena", "アリーナ", "劇場", "会館",
    )
    has_broadcast = any(signal in text for signal in broadcast_signals)
    has_youtube_link = "youtube.com/" in text or "youtu.be/" in text
    normalized_venue = (venue or "").strip().lower()
    online_venue_signals = ("youtube", "유튜브", "온라인", "配信", "stream")
    has_physical_venue = bool(normalized_venue) and not any(
        signal in normalized_venue for signal in online_venue_signals
    )
    has_onsite = has_physical_venue or any(signal in text for signal in onsite_signals)
    if has_broadcast and has_onsite:
        return "hybrid"
    if has_onsite:
        return "onsite"
    if has_broadcast or has_youtube_link:
        return "online"
    return model_format
