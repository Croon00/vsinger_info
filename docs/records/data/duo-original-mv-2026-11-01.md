# HONK THE HORN·NUROJUNK 오리지널 MV 추가 — 2026-11-01

2026-11-23 [곡 탐색](../../song-exploration.md) 문서에서 분리한 데이터 작업 기록이다. 수치는 기록 시점 기준이다. 표시 기준은 [곡 탐색의 그룹 표시](../../song-exploration.md#오리지널-곡의-그룹-표시)를 따른다.

사용자 요청으로 두 그룹의 기존 공식 YouTube 계정(HONK THE HORN 57, NUROJUNK 25)을 확인하고 전체 업로드 7페이지·310개를 검토했다. 공식 아티스트/발매 안내와 MV 제목·원본 설명을 대조해 HONK THE HORN 5곡(NO LEASH, SLOW FLAME, WILD SIDE, 808, DIM LIGHT), NUROJUNK 3곡(DEMOLISHER, Rising a Tide, Chase the Sun)을 등록했다. 검토 manifest는 `migrations/catalog/duo-original-videos-2026-11-01.json`이며 원본 채널 ID·영상 ID·제목·설명·등록일과 공식 출처 URL을 보존한다. 일반 로그·프로모션·커버는 등록하지 않았다.

기존 `import_reviewed_original_videos.py`의 허용 publisher에 정확한 두 채널 ID만 추가했다. 신규 DB 감사 기록 7504로 recording 8개와 그룹 명의를 추가했고, 조회수 8개를 실제 API로 연결했다. 반복 적용은 `already_applied`로 0개다. 계정 소유권·멤버 크레딧·기존 발매 행은 변경하지 않았다. 이번 실행은 검토된 MV의 명시적 수집이며 모든 신규 오리지널이 주기적으로 자동 분류되는 것으로 간주하지 않는다.

실데이터 읽기 검증에서 그룹별 5개/3개, 합집합 8개, 영상 ID 중복 없음, 8개 전부 조회수·등록일 존재, NO LEASH의 2026년 3월 영상 등록일 검색 1개를 확인했다. 조회 API fixture 2개는 통과했고 로컬 PostgreSQL이 필요한 12개는 건너뛰었다. 이 fixture 결과와 실제 신규 DB·YouTube API 검증은 별도다(2026-11-01).

```powershell
.venv\Scripts\python.exe scripts/import_reviewed_original_videos.py migrations/catalog/duo-original-videos-2026-11-01.json
```
