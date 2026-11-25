"""Review-file contract for recording lyrics. Only approved entries are imported."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SourceKind = Literal['video_description', 'youtube_comment', 'official_page', 'announcement', 'manual_note']


class LyricsEntry(BaseModel):
    model_config = ConfigDict(extra='forbid')
    key: str = Field(pattern=r'^recording:[1-9]\d*$')
    recording_ids: list[int] = Field(min_length=1)
    title: str
    title_ko: str | None = None
    artist: str = ''
    youtube_url: str | None = None
    status: str = ''  # export reason: found_in_description, found_in_comment, no_video, ...
    source_kind: SourceKind = 'manual_note'
    source_url: str | None = Field(default=None, pattern=r'^https?://\S+$')
    source_external_id: str | None = None
    source_author_is_channel_owner: bool | None = None
    extraction_method: str | None = None
    captured_at: datetime | None = None
    source_text: str | None = None
    original_lyrics: str = ''
    translation_ko: str = ''
    pronunciation_ko: str = ''
    approved: bool = False
    note: str = ''

    @field_validator('recording_ids')
    @classmethod
    def positive_unique(cls, value):
        if any(item < 1 for item in value) or len(set(value)) != len(value):
            raise ValueError('recording_ids must be unique positive IDs')
        return value

    @model_validator(mode='after')
    def approved_needs_lyrics(self):
        if self.approved and not self.original_lyrics.strip():
            raise ValueError(f'{self.key}: approved entries need original_lyrics')
        return self


class LyricsReviewFile(BaseModel):
    model_config = ConfigDict(extra='forbid')
    schema_version: Literal[1] = 1
    kind: Literal['candidates', 'manual']
    generated_at: datetime
    instructions: str
    entries: list[LyricsEntry]
