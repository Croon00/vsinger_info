from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.models import ArtistCreate, ArtistUpdate, EventCandidateCreate, SourceCreate
from app.core.artist_identity import display_artist_name, group_artists
from app.db.models import ArtistAgencyModel, ArtistModel, ArtistSourceModel, EventCandidateModel
from app.repositories.artist_agencies import ArtistAgencyRepository
from app.repositories.artist_sources import ArtistSourceRepository
from app.repositories.artists import ArtistRepository
from app.repositories.event_candidates import EventCandidateRepository


def _source_data(source: ArtistSourceModel) -> dict:
    """ORM 소스 엔터티를 API 응답용 사전으로 변환한다."""
    return {
        "id": source.id, "artist_id": source.artist_id, "source_type": source.source_type,
        "label": source.label, "value": source.value, "is_active": source.is_active,
        "created_at": source.created_at, "updated_at": source.updated_at,
    }


class ArtistService:
    """아티스트·소스·소속사·이벤트 후보 repository를 조합하는 유스케이스 계층."""
    def __init__(self, session: Session):
        """하나의 요청 트랜잭션에서 사용할 repository들을 준비한다."""
        self.artists = ArtistRepository(session)
        self.sources = ArtistSourceRepository(session)
        self.agencies = ArtistAgencyRepository(session)
        self.events = EventCandidateRepository(session)

    def list_agencies(self) -> list[ArtistAgencyModel]:
        return self.agencies.list()

    def create_agency(self, name: str) -> ArtistAgencyModel:
        return self.agencies.create(name.strip())

    def create_artist(self, payload: ArtistCreate) -> dict:
        values = payload.model_dump(exclude={"x_username"})
        values['display_name'] = display_artist_name(values['name'], values.get('display_name'), values.get('agency'))
        artist = self.artists.create(values)
        if payload.x_username:
            self.sources.create(
                artist.id,
                {"source_type": "x", "label": "Official X", "value": payload.x_username, "is_active": True},
            )
        return self._artist_data(self.artists.get(artist.id))

    def list_artists(self, grouped: bool = False) -> list[dict]:
        rows = [self._artist_data(artist) for artist in self.artists.list()]
        return group_artists(rows) if grouped else rows

    def get_artist(self, artist_id: int) -> dict:
        return self._artist_data(self.artists.get(artist_id))

    def update_artist(self, artist_id: int, payload: ArtistUpdate) -> dict:
        artist = self.artists.update(artist_id, payload.model_dump(exclude_unset=True))
        artist.display_name = display_artist_name(artist.name, artist.display_name, artist.agency)
        return self._artist_data(artist)

    def delete_artist(self, artist_id: int) -> None:
        self.artists.delete(artist_id)

    def add_source(self, artist_id: int, payload: SourceCreate) -> dict:
        self.artists.require(artist_id)
        return _source_data(self.sources.create(artist_id, payload.model_dump()))

    def list_sources(self, artist_id: int) -> list[dict]:
        self.artists.require(artist_id)
        return [_source_data(source) for source in self.sources.list_for_artist(artist_id)]

    def delete_source(self, artist_id: int, source_id: int) -> None:
        self.artists.require(artist_id)
        self.sources.delete_for_artist(artist_id, source_id)

    def create_event_candidate(self, payload: EventCandidateCreate) -> EventCandidateModel:
        return self.events.create(payload.model_dump())

    def list_event_candidates(self, **filters: object) -> list[EventCandidateModel]:
        artist_id = filters.get('artist_id')
        if artist_id is not None:
            groups = group_artists([{'id': row.id, 'name': row.name, 'display_name': row.display_name, 'agency': row.agency}
                                    for row in self.artists.list()])
            group = next((row for row in groups if artist_id in row['related_artist_ids']), None)
            if group:
                filters['artist_id'] = group['related_artist_ids']
        return self.events.list(**filters)

    def _artist_data(self, artist: ArtistModel) -> dict:
        return {
            "id": artist.id, "name": artist.name, "display_name": display_artist_name(artist.name, artist.display_name, artist.agency),
            "artist_kind": artist.artist_kind, "agency": artist.agency, "notes": artist.notes,
            "profile_intro": artist.profile_intro, "debut_date": artist.debut_date,
            "show_in_spotify": artist.show_in_spotify, "show_in_lyrics": artist.show_in_lyrics,
            "show_in_youtube_lives": artist.show_in_youtube_lives,
            "spotify_image_url": artist.spotify_image_url,
            "representative_youtube_url": self.artists.representative_youtube_url(artist),
            "created_at": artist.created_at, "updated_at": artist.updated_at,
            "sources": [_source_data(source) for source in artist.sources],
        }
