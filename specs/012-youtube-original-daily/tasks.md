# YouTube 오리지널 일일 수집 작업

- [x] T001 FR-001~006 요구·범위·완료 조건 정리.
- [x] T002 FR-001·005 typed purpose 및 기존 일일 poll/collect 연결, 기존 작업 키 유지.
- [x] T003 FR-002~004 키워드 없는 발매 연결·새 곡/명의 근거 검증 구현.
- [x] T004 FR-005~006 원문·검토 후보·중복/수동 수정 보호·원자 감사 저장 구현.
- [x] T005 SC-001~003 fixture·기존 회귀 실행, 계약과 roadmap 갱신.
- [ ] T006 SC-002 disposable PostgreSQL/CI에서 건너뛴 DB fixture 실행. 생성/연결·중복·기존 분류·소유 변경·기준선/감사/조회 확인.
- [ ] T007 SC-003 poll·collect worker 모두 새 코드 적용/재시작 후 일일 작업과 실제 신곡 조회 확인.
- [ ] T008 FR-006 남은 근거 부족 후보·미등록 유통 채널 검토. 138개 활성 공식 계정 과거 보완은 아래 실제 검증 기록 참고.

화면 FR-007~010·T009~011은 [추가 화면 작업](ui.md)에 연결한다.
- [x] T012 사용자 요청 범위의 과거 채널 조사·명시적 반영·감사 재조회. [실제 결과](../../docs/youtube-original-backfill-2026-11-22.md): 138채널, 신규 40곡·기존 영상 연결 14건. 모든 보류 후보의 오리지널 확정 완료를 뜻하지 않는다.

## 2026-11-22 검증

`python -m pytest tests/test_youtube_original.py tests/test_youtube_catalog_collection.py tests/test_music_jobs.py tests/test_youtube_setlist_selection.py tests/test_recording_youtube_match.py tests/test_spotify_catalog_collection.py -q --disable-warnings --tb=short`: 122 passed, 106 skipped. skip은 disposable PostgreSQL 바이너리 부재다. 실제 provider·모델·Discord 호출은 없다.

신규 DB 읽기 전용 세션에서 실제 계정 scope SELECT의 owner/별칭/기존 녹음·발매 조회를 확인했다. 원격 DB를 fixture DB로 사용하지 않았고 데이터 변경·재수집·worker 활성화·운영 배포는 하지 않았다.

기존 세트리스트 규칙·댓글 형식까지 포함한 최종 회귀: 241 passed, 106 skipped. git diff --check 통과. PostgreSQL 의존 생략과 실제 운영 적용 한계는 동일하다.

후속 사용자 요청으로 실제 과거 수집·DB 반영을 수행했다. 위의 '실제 반영하지 않음'은 최초 구현 검증 시점 기록이다. 최종 정책 3의 관련 Python 회귀는 83 passed, 44 skipped. 실제 결과와 홍보 영상 9건 보관 정정 감사는 T012 문서를 따른다. 일일 worker 운영 배포는 여전히 미완료다.
