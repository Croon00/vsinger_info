# 작업 목록 — 생방송 멀티뷰 운영 연결

작성 2026-11-17 · [요구사항](spec.md) · [설계](plan.md)

## 기존 구현 재검증

- [ ] T001 [US2] app/services/youtube_live_monitor.py와 repository의 검색·상태 확인·lease를 FR-002~004·006과 대조한다.
- [ ] T002 [US2] tests/test_holodex.py 등 monitor fixture로 예정 시각 도달·재시작·유예를 검증한다. SC-001.
- [ ] T003 [US1] tests/test_multiview.py와 조회 테스트로 예정 방송 75분·생방송 15분 만료와 관찰 시각 선택·provider 호출 금지를 확인한다. SC-002.
- [ ] T004 [US2] 격리 PostgreSQL에서 동시 claim·저장 시 계정 재검사·lease 만료를 검증한다. FR-004.
- [ ] T005 [US3] web/tests/integration/multiview.spec.ts의 환경·외부 호출 여부를 확인하고 적절한 fixture 검증과 web build를 실행한다.

## 운영 연결

T006부터는 배포·실제 provider 검증 범위를 확인한 뒤 진행한다.

- [ ] T006 [US2] API·monitor revision과 HOLODEX_POLL_SECONDS=3600, HOLODEX_LIVE_CHECK_SECONDS=180의 실제 설정·활성 대상·중복 인스턴스를 확인한다. FR-002·006~007.
- [ ] T007 [US2] 요청 범위의 API·monitor를 배포하고 실제 검색·상태 전환·실패 유예를 관찰한다. SC-003.
- [ ] T008 [US3] 배포 웹의 영상 선택·재생·채팅·자동재생 제한을 확인한다. SC-004.
- [ ] T009 [US1] 날짜·환경·revision·관찰 결과를 운영 기록과 docs/backend-roadmap.md에 반영한다.
