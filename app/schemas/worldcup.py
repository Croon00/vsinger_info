"""Original-song world cup: browser submissions and public song statistics."""
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

VideoId = Annotated[str, StringConstraints(pattern=r'^[A-Za-z0-9_-]{11}$')]
RoundSize = Literal[2, 4, 8, 16, 32, 64, 128]
BracketSize = Literal[8, 16, 32, 64, 128]


class WorldcupMatchIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    round: RoundSize
    winner: VideoId
    loser: VideoId


class WorldcupSubmission(BaseModel):
    """A finished bracket. Matches are listed in play order, round by round."""
    model_config = ConfigDict(extra='forbid')
    submission_id: UUID
    client_id: UUID
    song_kind: Literal['original', 'cover'] = 'original'
    scope_kind: Literal['agency', 'artists', 'random']
    scope_label: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    size: BracketSize
    duration_seconds: int = Field(ge=0, le=604800)
    matches: list[WorldcupMatchIn] = Field(min_length=7, max_length=127)


class WorldcupSongStat(BaseModel):
    video_id: str
    title: str
    title_ko: str | None = None
    artist_name: str = ''
    appearances: int
    championships: int
    championship_rate: float | None = None
    match_wins: int
    match_losses: int
    match_win_rate: float | None = None


class WorldcupSubmitResult(BaseModel):
    run_id: int
    duplicate: bool = False
    winner: WorldcupSongStat | None = None


class WorldcupStatsPage(BaseModel):
    items: list[WorldcupSongStat]
    total: int
    offset: int
    limit: int
    total_runs: int


class PoolCount(BaseModel):
    name: str
    count: int


class ArtistPoolCount(BaseModel):
    id: int
    count: int


class WorldcupPoolSummary(BaseModel):
    """Playable songs per agency and per artist, for the setup screen."""
    song_kind: Literal['original', 'cover']
    total: int
    agencies: list[PoolCount]
    artists: list[ArtistPoolCount]
