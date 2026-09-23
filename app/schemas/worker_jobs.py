"""Versioned, UI-independent inputs for the retained music collectors."""
from __future__ import annotations

import hashlib
import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

JobType = Literal['youtube_poll', 'youtube_collect', 'spotify_collect']
ChannelId = Annotated[str, Field(pattern=r'^UC[A-Za-z0-9_-]{22}$')]


class Payload(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    version: Literal[1] = 1
    request_run: str = Field(default='initial', min_length=1, max_length=120,
                             pattern=r'^[A-Za-z0-9._:+-]+$')


class YouTubePoll(Payload):
    channel_id: ChannelId
    # Explicit, bounded historical selection. Routine polls never backfill.
    backfill_video_ids: list[Annotated[str, Field(pattern=r'^[A-Za-z0-9_-]{11}$')]] = Field(default_factory=list, max_length=200)


class YouTubeCollect(Payload):
    channel_id: ChannelId
    youtube_video_id: str = Field(pattern=r'^[A-Za-z0-9_-]{11}$')
    purpose: Literal['archive', 'cover'] = 'archive'
    extraction_version: str = Field(default='1', pattern=r'^[A-Za-z0-9._-]{1,40}$')
    wait_count: int = Field(default=0, ge=0, le=168)


class SpotifyCollect(Payload):
    spotify_artist_id: str = Field(pattern=r'^[A-Za-z0-9]{22}$')
    link_youtube: bool = False
    album_offset: int = Field(default=0, ge=0, le=1000)


PAYLOAD_MODELS = {
    'youtube_poll': YouTubePoll,
    'youtube_collect': YouTubeCollect,
    'spotify_collect': SpotifyCollect,
}


class JobRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    job_type: JobType
    external_account_id: int = Field(gt=0)
    video_id: int | None = Field(default=None, gt=0)
    payload: dict
    max_attempts: int = Field(default=5, ge=1, le=100)

    def parsed_payload(self) -> Payload:
        return PAYLOAD_MODELS[self.job_type].model_validate(self.payload)

    def key(self) -> str:
        canonical = json.dumps(self.parsed_payload().model_dump(), sort_keys=True,
                               separators=(',', ':'), ensure_ascii=True)
        digest = hashlib.sha256(canonical.encode()).hexdigest()
        return f'{self.job_type}:v1:{self.external_account_id}:{digest}'


def account_identity(job_type: str, payload: Payload) -> tuple[str, str]:
    if job_type == 'spotify_collect':
        return 'spotify', payload.spotify_artist_id
    return 'youtube', payload.channel_id


class WorkerReadiness(BaseModel):
    ready: bool
    database_verified: bool
    workers_enabled: bool
    registered_handlers: list[str] = Field(default_factory=list)
    unimplemented_handlers: list[str] = Field(default_factory=list)
    missing_credentials: list[str] = Field(default_factory=list)
    optional_features: dict[str, bool] = Field(default_factory=dict)
    active_accounts: dict[str, int] = Field(default_factory=dict)
    workers: dict = Field(default_factory=dict)
    queue: dict = Field(default_factory=dict)
