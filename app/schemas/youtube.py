"""YouTube 라이브 API 요청 모델이다."""

from datetime import datetime

from pydantic import BaseModel, HttpUrl


class YouTubeLiveCreate(BaseModel):
    """YouTube 라이브 등록 요청이다."""

    youtube_url: HttpUrl
    artist_name: str


class YouTubeChannelBackfillCreate(BaseModel):
    """YouTube 채널 과거 수집 요청이다."""

    channel_url: HttpUrl
    artist_name: str


class YouTubeCoverVideo(BaseModel):
    id: int
    artist_id: int
    artist_name: str
    youtube_video_id: str
    youtube_url: str
    video_title: str
    video_description: str | None = None
    published_at: datetime | None = None
    collaborators: list[dict[str, int | str]] = []
