from unittest.mock import Mock

from app.schemas.read_models import StatisticsRead
from app.services.catalog_read import CatalogRead


def test_statistics_exposes_stored_korean_names_without_inventing_missing_labels():
    service = CatalogRead.__new__(CatalogRead)
    service.repository = Mock()
    service.repository.statistic_rows.return_value = ([
        {
            "song_key": "song:1", "title": "原題", "title_ko": "한국어 제목",
            "artist": "原曲者", "artist_ko": "한국어 가수",
            "originals": [{"key": "artist:1", "name": "原曲者", "nameKo": "한국어 가수"}],
            "count": 2, "last_date": None, "search": "原題 한국어 제목 原曲者 한국어 가수",
        },
        {
            "song_key": "raw:2", "title": "Untitled", "title_ko": None,
            "artist": "Unknown", "artist_ko": None,
            "originals": [{"key": "raw:unknown", "name": "Unknown"}],
            "count": 1, "last_date": None, "search": "Untitled Unknown",
        },
    ], [])

    result = StatisticsRead.model_validate(service.statistics(1))

    assert result.songs[0].titleKo == "한국어 제목"
    assert result.songs[0].artistKo == "한국어 가수"
    assert result.artists[0].nameKo == "한국어 가수"
    assert result.songs[1].titleKo is None
    assert result.artists[1].nameKo is None
