# 구현 계획 — 수집·알림 서비스 운영 전환

작성 2026-11-17 · [요구사항](spec.md) · 기존 설계 이관

## 기술 구성

Python 3.12.8, FastAPI, Pydantic, SQLAlchemy, PostgreSQL, Vue 3·Vite를 사용한다. 검증은 pytest, Vitest, Playwright를 사용한다. 처리 경로와 계약은 원본 문서를 따른다.

- [백엔드 구조](../../docs/backend-architecture.md)
- [조회 API](../../docs/read-api-v2.md)
- [카탈로그 schema](../../docs/catalog-schema.md)

## 프로젝트 원칙 준수 점검

신규 DB 단일 설정·legacy 읽기 전용, source_items·delivery·lease, 수동 교정 보존, 조회 중 외부 작업 금지 원칙을 적용한다. 운영 변경과 실제 전송은 사용자 요청 범위와 provider 한도를 확인한다.

## 설계와 실행 순서

1. app/api/, app/services/, app/repositories/, app/integrations/, app/agents/, app/bots/, app/runtime.py의 실제 경로와 배포 revision을 FR-001~007에 대조한다.
2. 기존 tests/ 회귀 검증과 보완 단계 문서를 연결한다. 실패가 재현되면 해당 계층에서 보완한다.
3. 격리 DB와 가짜 provider로 이전→수집→저장→조회 및 재실행 중복을 검증한다.
4. 기존 전환 절차에 따라 writer·설정·권한·provider 상태·revision·복구 경로를 확인한다.
5. 요청 범위의 실제 수집·전송·조회 결과를 SC-001~004에 연결하고 roadmap을 갱신한다.

## 계약과 검증

현재 API·schema·이전 계약은 원본에서 관리한다. 계약 변경이 필요할 때 이 디렉터리에 변경 계약과 마이그레이션 계획을 추가한다. tests/의 관련 fixture·PostgreSQL 검증, web/의 관련 테스트·build를 변경 범위에 따라 실행한다. 실행 날짜·환경·결과와 운영 관찰을 기록한다.

- [X·Discord](../../docs/backend-service-step-1-runtime.md)
- [작업 실행기](../../docs/backend-service-step-2-jobs.md)
- [YouTube](../../docs/backend-service-step-3-youtube.md)
- [Spotify](../../docs/backend-service-step-4-spotify.md)
- [전환 절차](../../docs/backend-phase-5-cutover.md)
