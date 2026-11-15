"""Validated, version-controlled evidence catalog; no network/DB writes on reads."""
from functools import lru_cache
from pathlib import Path
from app.schemas.music_tags import MusicTagCatalog, GENRES, MOODS

CATALOG = Path(__file__).resolve().parents[2] / 'data/classification/original_music_tags.json'


@lru_cache(maxsize=2)
def _load(path: str, modified: int):
    return MusicTagCatalog.model_validate_json(Path(path).read_text(encoding='utf-8')).model_dump(mode='json')['items']


def tag_rows():
    return _load(str(CATALOG), CATALOG.stat().st_mtime_ns)


def options():
    return {key: [dict(value=value, label=label) for value, label in values.items()]
            for key, values in [('genres', GENRES), ('moods', MOODS)]}
