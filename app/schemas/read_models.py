"""Public read contracts. No collection/translation payloads or private raw text."""
from datetime import date, datetime
from typing import Generic, TypeVar
from pydantic import BaseModel, Field

T = TypeVar('T')
class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    offset: int
    limit: int

class SourceRead(BaseModel):
    source_type: str
    value: str
    label: str | None = None
    is_active: bool

class ArtistRead(BaseModel):
    id: int
    name: str
    display_name: str | None = None
    agency: str | None = None
    profile_intro: str | None = None
    spotify_image_url: str | None = None
    related_artist_ids: list[int] = Field(default_factory=list)
    name_aliases: list[str] = Field(default_factory=list)
    sources: list[SourceRead] = Field(default_factory=list)

class PerformanceRead(BaseModel):
    id: int
    song_title: str
    song_title_ko: str | None = None
    original_artist: str | None = None
    original_artist_ko: str | None = None
    start_seconds: int

class LiveRead(BaseModel):
    id: int
    artist_id: int | None = None
    artist_name: str
    youtube_url: str
    youtube_video_id: str
    video_title: str | None = None
    broadcast_at: datetime | None = None
    published_at: datetime | None = None
    duration_seconds: int | None = None
    performances: list[PerformanceRead] = Field(default_factory=list)

class SearchRead(PerformanceRead):
    archive_id: int
    artist_id: int | None = None
    artist_name: str
    youtube_url: str
    video_title: str | None = None
    performed_on: date | None = None

class SongStat(BaseModel):
    key: str
    title: str
    artist: str
    searchText: str
    count: int
    lastPerformedAt: datetime | None
    rank: int

class ArtistStat(BaseModel):
    key: str
    name: str
    count: int
    percentage: float

class MonthStat(BaseModel):
    month: str
    count: int

class StatisticsRead(BaseModel):
    archives: int
    archivesWithSetlist: int
    performances: int
    uniqueSongs: int
    uniqueArtists: int
    songs: list[SongStat]
    artists: list[ArtistStat]
    activity: list[MonthStat]

class ConcertRead(BaseModel):
    id: int
    artist_id: int
    title: str
    starts_at: str
    venue: str | None = None
    price_text: str | None = None
    source_url: str | None = None
    ticket_url: str | None = None
    status: str
    event_type: str
    event_format: str
