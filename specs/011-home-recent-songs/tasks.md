# 홈 최근 곡 작업 목록

- [x] T001 FR-001~006 요구·설계·완료 조건 연결.
- [x] T002 FR-002·006 선택 게시 영상 필터와 프론트 조회 limit 구현.
- [x] T003 FR-001·003~005 두 캐러셀·영상 다이얼로그·전체 보기·상태 처리 구현.
- [x] T004 SC-001·002 fixture 추가, 빌드·단위 테스트·실데이터 읽기 확인.
- [x] T005 계약·화면 설계·QA·roadmap 갱신.
- [ ] T006 SC-002 PC·모바일 화면·수동 이동·전체 보기·다이얼로그 검수. 내장 브라우저 연결 불가, 기존 Chrome 창 접근은 자동 승인 검토에서 사적 콘텐츠 접근 위험으로 거부됨.
- [ ] T007 SC-002 로컬 PostgreSQL 바이너리를 갖춘 환경에서 건너뛴 fixture 실행.

## 2026-11-21 검증 기록

- `npm run build` 통과(TypeScript 및 Vite). sandbox의 esbuild spawn EPERM은 허용된 실행으로 재시도해 해결.
- `npm run test`: 11개 파일, 62개 테스트 통과.
- `.venv/Scripts/python.exe -m pytest tests/test_song_explore.py -q --disable-warnings --tb=short`: 2 passed, 14 skipped. 로컬 PostgreSQL 바이너리 부재로 skip이며 원격 DB로 대체하지 않았다.
- 실데이터 읽기 전용 GET: 두 종류 각 10개·중복 영상 0개·게시일 내림차순. 당시 적격 수 오리지널 695, 커버 4,538. 최신 게시일은 각각 2026-10-17, 2026-11-20. 수집·DB 변경·배포 없음.
- API `http://127.0.0.1:8000/health`, 프론트 `http://localhost:5174/` 및 프론트 곡 조회 프록시 200 확인.
