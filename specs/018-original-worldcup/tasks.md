# 오리지널 곡 월드컵 작업 목록

- [x] T001 FR-001~006 요구·설계 연결.
- [x] T002 대진·진행 로직과 단위 테스트(`web/tests/unit/worldcup.test.ts`).
- [x] T003 월드컵 화면·메뉴·라우트.
- [x] T004 브라우저 통합 테스트(`web/tests/integration/worldcup.spec.ts`)와 내비게이션 e2e 갱신.
- [x] T007 FR-008~010 결과 저장·통계 API, migration 008, 프록시 쓰기 경로, 결과 통계·랭킹 화면(2026-11-26).
- [x] T009 FR-012 커버 월드컵, 곡 수 요약 API, 종류별 통계·랭킹(2026-11-26). migration 008에 `song_kind`를 추가했다(미적용 상태에서 수정).
- [x] T010 FR-007 월드컵 소속사 복수 선택과 영상 합집합 조회. [2026-11-26 검증](../../docs/records/backend/worldcup-agencies-2026-11-26.md)
- [ ] T008 배포 순서: 008 지원 백엔드·프론트 배포 → `migrate_catalog.py --apply`(008) → `--verify` → 운영 제출·랭킹 확인.
- [ ] T005 배포 후 실제 MV 재생·모바일 사용성 확인.
- [ ] T006 2단계(통계·공유·커버 월드컵) 범위 결정.

## 2026-11-26 검증 기록

- `npm run build` 통과, `vitest` 77 passed(월드컵 11개 포함, 대진 배치는 시드 30개에서 같은 아티스트 짝 0).
- 통합(Playwright, 가짜 API 40곡, 데스크톱·모바일): 소속사 후보 요청 파라미터, 64·128강 비활성, 재생 임베드, 선택·되돌리기, 새로고침 후 이어하기, 16강 완료 후 결과, 아티스트 선택 시 `artist_ids` 요청 — 2 passed.
- e2e `navigation.spec.ts`를 메뉴 6개 기준으로 고치고 탐색 이동 대기 경쟁 조건을 수정해 2 passed. 같은 실행의 `app.spec.ts` 2개·`statistics.spec.ts` 1개(×2 화면) 실패는 변경 전 코드에서도 동일하게 실패하는 기존 문제다.
- 실데이터 후보 수(2026-11-25 읽기 전용): 전체 746, KAMITSUBAKI 291, RK Music 198, ホロライブ 100, Re:AcT 44, RIOT MUSIC 33.

## 2026-11-26 통계 기능 검증 기록

- `pytest tests/test_worldcup.py` 13 passed(대진 검증 16~128강, 변조 5종, 속도·주소 제한, 저장·중복·로컬 표시, 거부 응답, 통계 파라미터·503). 전체 646 passed, 272 skipped(로컬 PostgreSQL 부재), 1 failed(기존 `test_song_catalogs` User-Agent 기대값 불일치).
- 통계 SQL: 운영 DB 트랜잭션 안에서 008과 같은 임시 테이블을 만들고 KAMITSUBAKI 실제 MV 16곡으로 3판(1판 로컬)을 넣어 우승·비율·승패·로컬 제외·소속사 필터·영상 지정을 확인한 뒤 롤백. 롤백 후 임시·공개 테이블 없음.
- `vitest` 78 passed(`server.test.ts`: 월드컵 POST 전달·API 키·X-Forwarded-For·다른 POST 405·64KB 초과 413, 종료 대기로 EBUSY 해소 4회 반복 통과).
- 통합(Playwright, 가짜 API): 완료 시 1회 제출·경기 라운드 순서·우승 통계 표시·새로고침 시 재제출 없이 통계 조회·랭킹 탭·정렬 변경 시 `min_appearances=3` — 데스크톱·모바일 통과.
- migration 008은 아직 운영 DB에 적용하지 않았다.

## 2026-11-26 커버 월드컵 검증 기록

- `pytest tests/test_worldcup.py` 15 passed(커버 제출·종류별 검증 호출·잘못된 종류 422, 곡 수 집계 순수 함수, 요약 API 종류별 캐시). 전체 648 passed, 272 skipped, 1 failed(기존 `test_song_catalogs`).
- 실데이터 읽기 전용: 곡 수 요약 오리지널 747곡·아티스트 79명, 커버 4,571곡·아티스트 129명(16곡 이상 72명), 커버 소속사 KAMITSUBAKI 1,448·RK Music 897·Re:AcT 417. 커버 통계 SQL은 임시 테이블 삽입 후 롤백으로 확인.
- 로컬 브라우저(실데이터): 커버 소속사 목록·곡 수, 무작위 섞기 "4,571곡 중 2,000곡 표본", KAMITSUBAKI 커버 32강 시작·고화질 썸네일.
- 통합(가짜 API, 데스크톱·모바일): 요약 API 종류별 요청, 종류 전환 시 아티스트 초기화, 커버 후보 `kind=cover` 요청, 커버 라벨 — 2 passed. `vitest` 78 passed.
