"""Public read contracts. No collection/translation payloads or private raw text."""
from datetime import date, datetime
from typing import Generic, TypeVar, Literal
from pydantic import BaseModel, Field

T = TypeVar('T')
class StreamGroupRead(BaseModel):
    key: str
    name: str
    kind: Literal['agency', 'group']
    account_ids: list[int]

class LiveStreamRead(BaseModel):
    account_id: int
    channel_id: str = Field(pattern=r'^UC[A-Za-z0-9_-]{22}$')
    artist_id: int
    artist_name: str
    video_id: str = Field(pattern=r'^[A-Za-z0-9_-]{11}$')
    title: str
    status: Literal['live', 'upcoming'] = 'live'
    started_at: datetime | None = None
    scheduled_at: datetime | None = None
    avatar_url: str = ''
    avatar_variants: dict[str, str] = Field(default_factory=dict)
    checked_at: datetime

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

class OriginalSongGroupRead(BaseModel):
    id: int
    name: str
    agency: str | None = None

class ArtistRead(BaseModel):
    original_song_group: OriginalSongGroupRead | None = None
    id: int
    name: str
    display_name: str | None = None
    name_latin: str | None = None
    birthday: str | None = None
    debut_date: date | None = None
    youtube_subscriber_count: int | None = None
    youtube_channel_created_at: datetime | None = None
    youtube_statistics_updated_at: datetime | None = None
    youtube_statistics_source: str | None = None
    theme_color: str | None = None
    agency: str | None = None
    profile_intro: str | None = None
    spotify_image_url: str | None = None
    avatar_variants: dict[str, str] = Field(default_factory=dict)
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
    performance_count: int | None = None
    performances: list[PerformanceRead] = Field(default_factory=list)

class CoverRead(BaseModel):
    id: int
    youtube_video_id: str
    youtube_url: str
    title: str
    published_at: datetime | None = None
    duration_seconds: int | None = None

class SearchRead(PerformanceRead):
    archive_id: int
    artist_id: int | None = None
    artist_name: str
    youtube_url: str
    video_title: str | None = None
    performed_on: date | None = None
    broadcast_at: datetime | None = None
    artist_name_ko: str | None = None

class SongStat(BaseModel):
    key: str
    title: str
    titleKo: str | None = None
    artist: str
    artistKo: str | None = None
    searchText: str
    count: int
    lastPerformedAt: datetime | None
    rank: int

class ArtistStat(BaseModel):
    key: str
    name: str
    nameKo: str | None = None
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
    city: str | None = None
    artist_ids: list[int] = Field(default_factory=list)
    venue: str | None = None
    price_text: str | None = None
    source_url: str | None = None
    ticket_url: str | None = None
    status: str
    event_type: str
    event_format: str

class CatalogTrackArtistRead(BaseModel):
    # Null when the credited performer is not a catalog-visible artist.
    artist_id: int | None = None
    name: str
    name_ko: str | None = None

class CatalogTrackRead(BaseModel):
    id: str
    recording_id: int
    song_id: int | None = None
    name: str
    name_ko: str | None = None
    duration_ms: int | None = None
    disc_number: int
    track_number: int
    has_lyrics: bool
    youtube_url: str | None = None
    # Performers of this track in credit order (Spotify credits first, then registered credits).
    artists: list[CatalogTrackArtistRead] = Field(default_factory=list)

class CatalogAlbumRead(BaseModel):
    id: str
    name: str
    name_ko: str | None = None
    album_type: str
    release_date: str
    image_url: str | None = None
    spotify_url: str | None = None
    total_tracks: int
    # Only on /artists/{id}/albums: True when that artist is an album-level credit,
    # False when the artist is credited on tracks only (appears on). None on /albums/{id}.
    is_primary: bool | None = None
    tracks: list[CatalogTrackRead] = Field(default_factory=list)

class CatalogLyricsRead(BaseModel):
    recording_id: int
    song_id: int | None = None
    original_title: str
    artist_name: str
    original_lyrics: str
    translation_ko: str
    pronunciation_ko: str
    lyrics_source_url: str | None = None
    lyrics_source_type: str
    needs_review: bool = False
