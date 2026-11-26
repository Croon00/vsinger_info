"""Authenticated web writes for original-song lyrics."""
from secrets import compare_digest
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Response
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.security import require_api_key
from app.db.catalog_session import CatalogIdentityError, catalog_runtime_session
from app.schemas.lyrics_edit import LyricsEdit
from app.schemas.read_models import CatalogLyricsRead
from app.services.lyrics_edit import LyricsConflict, OriginalRecordingNotFound, save_lyrics


def require_lyrics_editor(x_lyrics_editor_key: str | None = Header(default=None)) -> None:
    key = settings.lyrics_editor_key
    if not key:
        raise HTTPException(503, '가사 편집이 설정되지 않았습니다.')
    if not x_lyrics_editor_key or not compare_digest(x_lyrics_editor_key.encode(), key.encode()):
        raise HTTPException(403, '가사 편집 키가 올바르지 않습니다.')


router = APIRouter(tags=['lyrics-editor'], dependencies=[Depends(require_api_key), Depends(require_lyrics_editor)])


@router.put('/recordings/{recording_id}/lyrics', response_model=CatalogLyricsRead)
def edit_lyrics(recording_id: Annotated[int, Path(ge=1, le=2147483647)], draft: LyricsEdit, response: Response):
    try:
        with catalog_runtime_session() as session:
            saved = save_lyrics(session, recording_id, draft)
    except OriginalRecordingNotFound:
        raise HTTPException(404, '등록 가능한 오리지널 녹음을 찾을 수 없습니다.') from None
    except LyricsConflict:
        raise HTTPException(409, '가사 상태가 변경되었거나 보관되었습니다. 최신 가사를 확인해 주세요.') from None
    except (SQLAlchemyError, CatalogIdentityError):
        raise HTTPException(503, '가사를 저장할 수 없습니다. 잠시 후 다시 시도해 주세요.') from None
    response.headers['Cache-Control'] = 'private, no-store'
    return saved
