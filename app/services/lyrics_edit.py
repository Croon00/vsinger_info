"""Create or edit one catalog recording's lyrics, with revision checking."""
from app.repositories import recording_lyrics as repository
from app.repositories.catalog_read import CatalogReadRepository
from app.schemas.lyrics_edit import LyricsEdit
from app.schemas.lyrics_review import LyricsEntry
from app.schemas.read_models import CatalogLyricsRead


class OriginalRecordingNotFound(Exception):
    pass


class LyricsConflict(Exception):
    pass


def save_lyrics(session, recording_id: int, draft: LyricsEdit) -> CatalogLyricsRead:
    title = repository.lock_original(session, recording_id)
    if title is None:
        raise OriginalRecordingNotFound
    stored = repository.current_for_edit(session, recording_id)
    previous = stored['snapshot'] if stored else None
    old_url = stored['source_url'] if stored else None
    unchanged = previous and old_url == draft.lyrics_source_url and all(
        (previous[field] or '') == getattr(draft, field)
        for field in ('original_lyrics', 'translation_ko', 'pronunciation_ko')
    )
    if previous and previous['archived_at'] is not None:
        raise LyricsConflict
    if not unchanged:
        if draft.version != (previous['version'] if previous else None):
            raise LyricsConflict
        if previous and previous['original_lyrics'] == draft.original_lyrics and old_url == draft.lyrics_source_url:
            document_id = previous['source_document_id']
        else:
            document_id = repository.source_document(session, LyricsEntry(
                key=f'recording:{recording_id}', recording_ids=[recording_id], title=title,
                source_url=draft.lyrics_source_url, original_lyrics=draft.original_lyrics,
                extraction_method='manual_web', approved=True,
            ))
        if not repository.save_edit(session, recording_id, draft, document_id, previous):
            raise LyricsConflict
    return CatalogLyricsRead.model_validate(CatalogReadRepository(session).lyrics(recording_id))
