from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


SourceType = Literal["x", "official_site", "ticket_site", "rss", "other"]
ArtistKind = Literal["vtuber", "singer"]


class ArtistAgencyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class ArtistAgency(BaseModel):
    id: int
    name: str
    created_at: datetime
CandidateStatus = Literal["needs_review", "ready", "synced", "ignored"]
EventType = Literal["live_event", "ticket"]
EventFormat = Literal["onsite", "hybrid", "online", "unknown"]
WebLyricsSourceMode = Literal["caption", "description", "comment", "audio"]


class WebSongCreate(BaseModel):
    artist_id: int
    title: str = Field(min_length=1, max_length=200)
    youtube_url: str = Field(min_length=1, max_length=500)
    source_mode: WebLyricsSourceMode = "caption"
    language_code: str = Field(default="ja", min_length=2, max_length=10)


class WebSongCreated(BaseModel):
    id: int
    artist_name: str
    title: str
    lyrics_source_type: str
    needs_review: bool
    spotify_track_id: str | None = None


class SongLyricsSummary(BaseModel):
    song_id: int
    spotify_track_id: str
    youtube_url: str
    has_lyrics: bool
    lyricist: str | None = None
    composer: str | None = None
    arranger: str | None = None


class SpotifyTrackYouTubeLinkCreate(BaseModel):
    spotify_track_id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=300)
    artist_name: str = Field(min_length=1, max_length=300)
    album_name: str | None = Field(default=None, max_length=300)
    youtube_url: str = Field(min_length=1, max_length=500)


class SongCreditsUpdate(BaseModel):
    lyricist: str | None = Field(default=None, max_length=300)
    composer: str | None = Field(default=None, max_length=300)
    arranger: str | None = Field(default=None, max_length=300)


class SongLyricsDetail(BaseModel):
    song_id: int
    original_title: str
    title_ko: str | None = None
    artist_name: str
    album_name: str | None = None
    youtube_url: str
    original_lyrics: str
    translation_ko: str
    pronunciation_ko: str
    lyrics_source_type: str
    lyrics_source_url: str | None = None
    needs_review: bool


class YouTubePerformanceUpdate(BaseModel):
    song_title: str | None = Field(default=None, max_length=300)
    song_title_ko: str | None = Field(default=None, max_length=300)
    original_artist: str | None = Field(default=None, max_length=300)
    original_artist_ko: str | None = Field(default=None, max_length=300)


class ArtistCreate(BaseModel):
    """아티스트 생성 API에서 받는 입력값입니다."""

    name: str = Field(min_length=1, max_length=120)
    display_name: str | None = Field(default=None, max_length=120)
    artist_kind: ArtistKind = "vtuber"
    agency: str | None = Field(default=None, max_length=120)
    show_in_spotify: bool = True
    show_in_lyrics: bool = True
    show_in_youtube_lives: bool = True
    notes: str | None = None
    profile_intro: str | None = None
    debut_date: str | None = Field(default=None, max_length=20)
    x_username: str | None = Field(
        default=None,
        description="선택 X 핸들입니다. '@artist' 또는 'artist' 형식을 모두 허용합니다.",
    )

    @field_validator("x_username")
    @classmethod
    def normalize_x_username(cls, value: str | None) -> str | None:
        """X username 입력값에서 앞쪽 @와 공백을 제거합니다."""
        if value is None:
            return None
        cleaned = value.strip().lstrip("@")
        return cleaned or None


class ArtistUpdate(BaseModel):
    """아티스트 정보를 부분 수정할 때 받는 입력값입니다."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    display_name: str | None = Field(default=None, max_length=120)
    artist_kind: ArtistKind | None = None
    agency: str | None = Field(default=None, max_length=120)
    show_in_spotify: bool | None = None
    show_in_lyrics: bool | None = None
    show_in_youtube_lives: bool | None = None
    notes: str | None = None
    profile_intro: str | None = None
    debut_date: str | None = Field(default=None, max_length=20)


class Artist(BaseModel):
    """DB에 저장된 아티스트 기본 정보를 API 응답으로 표현합니다."""

    id: int
    name: str
    display_name: str | None
    artist_kind: ArtistKind
    agency: str | None = None
    show_in_spotify: bool = True
    show_in_lyrics: bool = True
    show_in_youtube_lives: bool = True
    notes: str | None
    profile_intro: str | None = None
    debut_date: str | None = None
    spotify_image_url: str | None = None
    representative_youtube_url: str | None = None
    created_at: datetime
    updated_at: datetime


class SourceCreate(BaseModel):
    """아티스트에 출처를 추가할 때 받는 입력값입니다."""

    source_type: SourceType
    value: str = Field(min_length=1, max_length=500)
    label: str | None = Field(default=None, max_length=120)
    is_active: bool = True

    @field_validator("value")
    @classmethod
    def normalize_value(cls, value: str) -> str:
        """출처 URL 또는 username 앞뒤 공백을 제거합니다."""
        return value.strip()


class Source(BaseModel):
    """DB에 저장된 아티스트 출처 정보를 API 응답으로 표현합니다."""

    id: int
    artist_id: int
    source_type: SourceType
    label: str | None
    value: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ArtistWithSources(Artist):
    """아티스트 기본 정보와 연결된 출처 목록을 포함한 응답 모델입니다."""

    sources: list[Source]
    related_artist_ids: list[int] = Field(default_factory=list)
    name_aliases: list[str] = Field(default_factory=list)


class EventCandidateCreate(BaseModel):
    """수동 입력 또는 agent 추출로 만들어지는 일정 후보 입력값입니다."""

    artist_id: int | None = None
    source_id: int | None = None
    event_type: EventType = "live_event"
    event_format: EventFormat = "unknown"
    title: str = Field(min_length=1, max_length=200)
    starts_at: str | None = None
    venue: str | None = None
    ticket_opens_at: str | None = None
    ticket_closes_at: str | None = None
    ticket_url: str | None = None
    price_text: str | None = None
    capacity_text: str | None = Field(default=None, max_length=120)
    setlist_json: str | None = None
    merchandise_json: str | None = None
    source_url: str | None = None
    raw_text: str | None = None
    status: CandidateStatus = "needs_review"


class EventCandidate(EventCandidateCreate):
    """DB에 저장된 일정 후보 정보를 API 응답으로 표현합니다."""

    id: int
    created_at: datetime
    updated_at: datetime
