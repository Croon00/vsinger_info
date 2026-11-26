# 오리지널 곡 가사 후보 설계

## 구현 경로

- 추출: `app/services/lyrics_extraction.py`의 순수 함수. 설명란은 `Lyrics`/`歌詞` 머리줄 뒤 블록, 없으면 구분선·URL·안내문(▼, 이모지 시작 줄 등)·크레딧(`이름 : 값`)으로 나눈 구간 중 가사형 줄 비율 85% 이상·12줄 이상인 가장 긴 구간을 고른다. 강희 부수(⾃ 등)는 문자로 취급한다. 댓글은 앞 3줄의 알림·곡명이 있어야 하고 12줄 이상·가사형 80% 이상이어야 한다.
- 계약: `app/schemas/lyrics_review.py`의 `LyricsReviewFile`/`LyricsEntry`. 후보·직접 입력 파일이 같은 항목 형식을 쓴다.
- 내보내기: `scripts/export_original_lyrics.py` → `CatalogRead.explore_songs(kind='original')` 전체 → `videos.list`(50개씩) → 필요 시 `commentThreads.list`(관련도순 100개). 출력은 Git 제외 경로 `db-migration/reports/original-lyrics-<날짜>/`의 `candidates.json`, `manual-with-video.json`, `manual-no-video.json`.
- 가져오기: `scripts/import_original_lyrics.py` → `app/repositories/recording_lyrics.py`. 승인 키 중복이면 중단한다. `source_documents`는 변경 불가 트리거가 있어 새 행만 추가한다.
- 웹 편집: 오리지널 곡 목록 두 곳에서 공용 `OriginalLyricsEditor`를 연다. 수정 폼은 기존 GET의 최신 가사와 버전을 읽고, 등록 폼은 빈 값으로 시작한다.
- 저장: `PUT /api/recordings/{id}/lyrics` → `app/services/lyrics_edit.py` → `app/repositories/recording_lyrics.py`. 오리지널 조회와 동일한 범위 조건으로 대상 녹음을 잠근 뒤 버전을 확인하고, 출처와 변경 이력까지 함께 커밋한다. 기존 스키마 트리거가 버전을 관리한다.

## 검증

2026-11-24 직접 판정한 표본 30개(설명란 가사 18, 댓글 가사 5~6)와 추출 결과를 비교한다. 실제 가사가 들어가지 않은 합성 fixture로 추출·계약 테스트를 작성한다. DB 쓰기는 트랜잭션 안에서 넣은 뒤 롤백해 제약 조건만 확인한다.
