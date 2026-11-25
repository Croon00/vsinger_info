# 발매 커버 제외 작업 목록

- [x] T001 FR-001~004 공용 규칙과 오리지널 쿼리 적용.
- [x] T002 가사 내보내기 제외 목록.
- [x] T003 fixture 갱신과 규칙 fixture 테스트 추가(`test_released_covers_are_not_originals`).
- [ ] T004 로컬 PostgreSQL이 있는 환경에서 DB fixture 실행(로컬 바이너리 없음으로 skip).
- [ ] T005 배포 후 오리지널 탭 확인.
- [ ] T006 `トウキョウ・シャンディ・ランデヴ`(花譜 피처링, 원곡자 MAISONdes만 등록) 12개 녹음의 원곡자 연결 검토. 현재 규칙으로 제외되며 대부분 키 변경 버전이다.

## 2026-11-25 검증 기록

- 실데이터 읽기 전용: 오리지널 2,471 → 2,141항목(330 제외). 제외 녹음 331개(제목 표기 294, 원곡자 기준 37). 제외 항목은 모두 공식 영상이 없는 Spotify 음원이었다. 제목에 `cover`가 남은 항목은 `discover` 2곡(오리지널)뿐이다. 원곡자 기준 37개를 직접 확인해 위 T006 외에는 실제 커버였다.
- 조회 시간: 오리지널 첫 페이지 369ms, 홈 최근 오리지널(`published_only`) 223ms, 746항목.
- `pytest` 전체: 631 passed, 271 skipped(로컬 PostgreSQL 부재), 1 failed. 실패 `test_song_catalogs.py::test_vocadb_parses_originals_and_credit_roles`는 User-Agent 문자열 기대값 불일치로 이번 변경과 무관한 기존 실패다.
