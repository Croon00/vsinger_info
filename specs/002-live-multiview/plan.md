# 구현 계획 — 생방송 멀티뷰 운영 연결

작성 2026-11-17 · [요구사항](spec.md)

## 기술 구성

FastAPI·PostgreSQL, 비동기 provider integration, Vue 3 멀티뷰 화면을 사용한다. 기존 tests/test_holodex.py, tests/test_multiview.py, web/tests/integration/multiview.spec.ts를 검증 출발점으로 삼는다.

## 프로젝트 원칙 준수 점검

조회와 수집의 경계, 신규 계정·공유 연결·provider lease를 적용한다. 테스트는 provider fixture를 사용한다. 운영 키는 서버 설정에서 관리하고 실제 provider 검증은 요청 범위에 따라 수행한다.

## 설계와 실행 순서

1. app/core/config.py와 app/services/youtube_live_monitor.py의 검색·상태 확인·재시작·실패 처리를 FR-002~004·006에 대조한다.
2. app/integrations/holodex.py와 app/repositories/의 monitor claim·lease·snapshot 저장을 확인한다.
3. app/api/와 조회 service·repository, web/의 /api/streams·/api/stream-groups 계약을 FR-001·005에 대조한다.
4. 관련 fixture·격리 PostgreSQL·웹 검증과 build를 실행하고 실패가 있으면 해당 계층을 보완한다.
5. 요청 범위의 배포 전에 API·monitor revision·설정·활성 대상·중복 인스턴스를 확인한다. 배포 후 SC-003~004를 기록한다.

## 데이터와 계약

기존 collection_states의 provider 상태·snapshot·lease를 우선 사용한다. API 필드·필터·만료 계약은 docs/read-api.md에서 관리한다. 후속 계약 변경이 필요하면 이 디렉터리에 변경 계약과 호환성 검증을 추가한다.

FR-008은 채널 고정 ID로 계정을 찾아 기존 그룹에 연결하고 `collection_states.provider_state.youtube_live_only`를 활성화한다. 신규 계정의 `collection_enabled`는 끈 상태로 등록한다. 멀티뷰 수집·조회 쿼리에서만 이 상태를 읽으며, 해당 계정을 소유한 그룹은 카탈로그에서 숨겨도 멀티뷰에 표시할 수 있다.

## 검증

관련 pytest fixture와 PostgreSQL 의존 테스트, 웹 멀티뷰 테스트·build를 변경 범위에 맞게 실행한다. 실제 재생은 배포 브라우저에서 확인하고 외부 플랫폼 제한을 관찰값으로 기록한다. 작업 완료 후 docs/backend-roadmap.md를 갱신한다.
