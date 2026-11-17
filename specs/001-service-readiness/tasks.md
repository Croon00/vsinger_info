# 작업 목록 — 수집·알림 서비스 운영 전환

작성 2026-11-17 · [요구사항](spec.md) · [설계](plan.md)

과거 구현·검증은 원본 단계 문서에서 확인한다. 아래는 이번 스펙에서 추적할 남은 작업이다.

## 기준 확인과 로컬 검증

- [ ] T001 [US1] FR-001~007을 현재 코드·tests/·배포 revision과 대조하고 research.md에 근거와 미확인을 기록한다.
- [ ] T002 [US1] schema·DATABASE_URL·legacy 경계를 docs/backend-architecture.md와 docs/backend-phase-5-cutover.md에 대조한다. FR-001.
- [ ] T003 [US2] X provider NoAccountError의 현 재현 여부·원인을 조사하고 필요한 수정과 fixture 검증을 수행한다. FR-003~004.
- [ ] T004 [US2] route·권한·중복·결과 불명 전송 회귀 테스트를 실행한다. FR-003~004, SC-001.
- [ ] T005 [US3] YouTube 혼합 소유·재개와 Spotify 공동 크레딧·수동 교정 보존을 격리 DB에서 검증한다. FR-005, SC-001.
- [ ] T006 [US1] tests/의 이전→수집→실제 /api 통합 검증과 web/ 관련 계약 테스트를 실행한다. FR-001~002, SC-001.

## 운영 전환

T007부터는 운영 변경 범위와 실제 환경을 확인한 뒤 진행한다.

- [ ] T007 [US3] Railway writer·설정·provider 한도·권한·복구 경로를 docs/backend-phase-5-cutover.md에 기록한다. FR-006~007.
- [ ] T008 [US3] 요청 범위의 수정 코드를 배포하고 /ready·실제 수집·DB·웹을 관찰한다. SC-002, SC-004.
- [ ] T009 [US2] 요청 범위의 Discord 실제 URL 전송·route·중복 방지를 확인한다. SC-003.
- [ ] T010 [US1] 날짜·revision·환경·검증·관찰을 운영 기록과 docs/backend-roadmap.md에 반영한다. SC-001~004.
