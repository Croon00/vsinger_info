# 구현 계획 — 아티스트·공식 채널 등록과 자료 보완

정리일 2026-11-18 · [요구사항](spec.md) · 기존 구현 구조와 후속 검증 이관

## 개요

기존 계약·실행 경로를 보존하고 FR-001~003과 SC-001~003을 검증 근거에 연결한다.

## 기술 구성

백엔드는 Python·FastAPI·Pydantic·SQLAlchemy·PostgreSQL, 관련 조회 웹은 Vue 3·TypeScript·Vite를 사용한다. 검증은 pytest·Vitest·Playwright를 사용한다. 실제 버전과 실행 환경은 검증 시 기록한다.

## 프로젝트 원칙 준수 점검

AGENTS.md와 [프로젝트 원칙](../../.specify/memory/constitution.md)을 따른다. 신규 DB 단일 설정·기존 DB 읽기 전용·출처와 수동 교정 보존·조회 중 수집 금지·외부 동작 범위를 점검한다. 원본의 legacy 경로는 현재 정상 실행 경로와 대조한다.

## 문서와 코드 구조

이 디렉터리의 spec.md·plan.md·tasks.md에서 요구사항·설계·작업을 연결한다. 상세 계약과 날짜별 원본은 docs에서 관리한다.

- `scripts/register_missing_youtube_channels.py`
- `scripts/register_requested_vsingers.py`
- `scripts/register_mair.py`
- `scripts/register_nakamachi_arale.py`

## 조사와 설계

검수 seed와 고정 ID로 신규 DB의 기존 레코드를 재사용하고 catalog_imports/catalog_changes에 근거를 남긴다. 날짜별 문서가 배치별 등록·활성화·과거 수집 범위를 정한다. 실제 수집은 001의 공통 worker 경로를 사용한다.

원본 계약과 근거는 다음 문서를 따른다.

- [youtube-channel-coverage](../../docs/youtube-channel-coverage.md)
- [requested-vsingers-2026-10-02](../../docs/requested-vsingers-2026-10-02.md)
- [requested-channels-2026-11-14](../../docs/requested-channels-2026-11-14.md)
- [mair-2026-10-07](../../docs/mair-2026-10-07.md)
- [nakamachi-arale-2026-10-07](../../docs/nakamachi-arale-2026-10-07.md)
- [nekothe-registration-2026-11-01](../../docs/nekothe-registration-2026-11-01.md)
- [kurokumo-2026-11-07](../../docs/kurokumo-2026-11-07.md)
- [react-collection-2026-11-07](../../docs/react-collection-2026-11-07.md)
- [react-members-2026-11-07](../../docs/react-members-2026-11-07.md)

## 검증과 운영 적용

- `tests/test_register_missing_youtube_channels.py`

US1의 FR-001·FR-002·FR-003은 각각 SC-001·SC-002·SC-003과 대조한다. 기존 테스트의 실제 적용 범위를 확인한 뒤 관련 fixture를 실행한다. PostgreSQL 의존 건너뜀·mock provider·실데이터 읽기·실제 수집·배포 확인은 날짜와 환경을 구분해 기록한다. 이번 정리는 문서·참조 경로·식별자 검증에 한정한다.

## 복잡성 검토

기존 코드 경로와 계약을 이관했다. 향후 schema·인터페이스 변경 시 변경 근거와 마이그레이션·복구 계획을 기록한다.
