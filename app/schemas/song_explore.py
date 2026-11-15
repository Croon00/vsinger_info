from datetime import datetime
from pydantic import BaseModel, Field
from app.schemas.music_tags import GenreTag, MoodTag, MusicTagSource


class SongPerformerRead(BaseModel):
    id: int
    name: str
    display_name: str | None = None


class SongExploreRead(BaseModel):
    genres: list[GenreTag] = Field(default_factory=list)
    moods: list[MoodTag] = Field(default_factory=list)
    music_tag_sources: list[MusicTagSource] = Field(default_factory=list)
    key: str
    title: str
    title_ko: str | None = None
    artist_name: str
    youtube_video_id: str | None = None
    view_count: int | None = None
    views_updated_at: datetime | None = None
    performance_count: int | None = None
    artist_count: int | None = None
    archive_id: int | None = None
    start_seconds: int | None = None
    published_at: datetime | None = None
