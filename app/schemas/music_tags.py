"""Recording/version-specific, source-backed music tags; never broad market genres."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

GenreTag = Literal['pop', 'ballad', 'rock', 'alternative-rock', 'hard-rock', 'metal',
                   'jazz', 'rnb', 'folk', 'electronic', 'funk', 'disco',
                   'acoustic', 'piano', 'band', 'orchestral']
MoodTag = Literal['calm', 'healing', 'warm', 'upbeat', 'powerful',
                  'melancholic', 'dreamy', 'dark', 'grand', 'bright']
GENRES = dict(zip(GenreTag.__args__, ['팝', '발라드', '록', '얼터너티브 록', '하드 록', '메탈',
    '재즈', 'R&B', '포크', '일렉트로닉', '펑크(Funk)', '디스코', '어쿠스틱', '피아노 중심', '밴드', '오케스트라']))
MOODS = dict(zip(MoodTag.__args__, ['잔잔한', '치유되는', '따뜻한', '신나는', '힘찬',
    '애절한', '몽환적인', '어두운', '웅장한', '밝은']))


class MusicTagSource(BaseModel):
    model_config = ConfigDict(extra='forbid')
    dimension: Literal['genre', 'mood']
    tag: str
    source_url: HttpUrl
    excerpt: str = Field(min_length=1, max_length=240)

    @model_validator(mode='after')
    def known_tag(self):
        if self.tag not in (GENRES if self.dimension == 'genre' else MOODS):
            raise ValueError('Unknown tag for this dimension')
        return self


class OriginalMusicTags(BaseModel):
    model_config = ConfigDict(extra='forbid')
    youtube_video_id: str | None = Field(default=None, pattern=r'^[A-Za-z0-9_-]{11}$')
    recording_key: str | None = Field(default=None, pattern=r'^recording:[1-9]\d*$')
    recording_title: str | None = None
    recording_artist: str | None = None
    genres: list[GenreTag] = Field(default_factory=list, max_length=8)
    moods: list[MoodTag] = Field(default_factory=list, max_length=8)
    sources: list[MusicTagSource] = Field(min_length=1, max_length=20)

    @model_validator(mode='after')
    def evidence_required(self):
        if bool(self.youtube_video_id) == bool(self.recording_key):
            raise ValueError('Exactly one stable recording or video identity is required')
        if self.recording_key and (not self.recording_title or not self.recording_artist):
            raise ValueError('Recording identities require title and artist guards')
        for dimension, tags in [('genre', self.genres), ('mood', self.moods)]:
            if len(set(tags)) != len(tags):
                raise ValueError('Duplicate tags')
            if any(not any(s.dimension == dimension and s.tag == tag for s in self.sources) for tag in tags):
                raise ValueError('Every published tag requires its own source')
        if not self.genres and not self.moods:
            raise ValueError('An entry must have at least one supported tag')
        return self


class MusicTagCatalog(BaseModel):
    model_config = ConfigDict(extra='forbid')
    schema_version: Literal[1] = 1
    policy: str
    reviewed_on: str
    items: list[OriginalMusicTags]

    @model_validator(mode='after')
    def unique_videos(self):
        if len({(item.youtube_video_id, item.recording_key) for item in self.items}) != len(self.items):
            raise ValueError('Duplicate video identity')
        return self


class MusicTagOption(BaseModel):
    value: str
    label: str


class MusicTagOptions(BaseModel):
    genres: list[MusicTagOption]
    moods: list[MusicTagOption]
