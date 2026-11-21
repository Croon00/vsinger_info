# 공유 채널 멤버 연결 작업

- [x] T001 FR-001~005 공식 채널·재생목록·현재 연결 조사.
- [x] T002 FR-001~002 솔로·듀엣·공동 커버의 중복 없는 표시.
- [x] T003 FR-003~004 진행자 근거 수집·저장·감사·기존 명의 보호.
- [x] T004 FR-004 개인 라이브/통계 출처 범위 적용.
- [x] T005 SC-001~002 2026-11-22 Python 86 passed, 76 skipped 및 별도 실제 DB/HTTP 대조.
- [ ] T006 SC-001 disposable PostgreSQL 부재로 생략한 DB fixture 실행.
- [ ] T007 SC-003 운영 worker/API 배포 후 일일 poll 재대조 확인. 로컬 API 재시작·명시적 실데이터 보완과 구분한다.
- [ ] T008 SC-003 HONK 1개·NUROJUNK 2개의 진행자 미확정 방송과 향후 근거 없는 신규 방송 검토.
- [x] T009 FR-002 추가 사용자 결정 반영: HONK 커버의 MOCO/BAMBI 이름 없으면 두 멤버 표시. 본편 유지 선택을 확인했다. 관련 규칙/조회 회귀 31 passed, 19 skipped(PostgreSQL fixture). 현재 본편 수치는 MOCO 9곡·BAMBI 8곡으로 동일하며 미표기 본편이 이미 검토된 듀엣/공동 영상이었기 때문이다.
