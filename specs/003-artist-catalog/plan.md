# 구현 계획 — 아티스트 명의·공유 채널·탐색 정렬

정리일 2026-11-18 · [요구사항](spec.md) · 기존 구현 구조와 후속 검증 이관

## 개요

기존 계약·실행 경로를 보존하고 FR-001~003과 SC-001~003을 검증 근거에 연결한다.

## 기술 구성

백엔드는 Python·FastAPI·Pydantic·SQLAlchemy·PostgreSQL, 관련 조회 웹은 Vue 3·TypeScript·Vite를 사용한다. 검증은 pytest·Vitest·Playwright를 사용한다. 실제 버전과 실행 환경은 검증 시 기록한다.

## 프로젝트 원칙 준수 점검

AGENTS.md와 [프로젝트 원칙](../../.specify/memory/constitution.md)을 따른다. 신규 DB 단일 설정·기존 DB 읽기 전용·출처와 수동 교정 보존·조회 중 수집 금지·외부 동작 범위를 점검한다. 원본의 legacy 경로는 현재 정상 실행 경로와 대조한다.

## 문서와 코드 구조

이 디렉터리의 spec.md·plan.md·tasks.md에서 요구사항·설계·작업을 연결한다. 상세 계약과 날짜별 원본은 docs에서 관리한다.

- `app/core/artist_identity.py`
- `app/data/artist_identities.json`
- `web/src/lib/artist-sort.ts`

## 조사와 설계

채널 통계는 collection_states의 저장 namespace에서 조회한다. scripts/refresh_youtube_channel_statistics.py와 기존 youtube_poll이 갱신하며 여러 채널 구독자를 합산하지 않는다. 공유 채널·그룹 명의의 예외는 원본의 검수 규칙을 사용한다.

원본 계약과 근거는 다음 문서를 따른다.

- [artist-names](../../docs/artist-names.md)
- [artist-sorting](../../docs/artist-sorting.md)
- [shared-youtube-channels](../../docs/shared-youtube-channels.md)

## 검증과 운영 적용

- `tests/test_artist_identity.py`
- `web/tests/unit/artist-sort.test.ts`

US1의 FR-001·FR-002·FR-003은 각각 SC-001·SC-002·SC-003과 대조한다. 기존 테스트의 실제 적용 범위를 확인한 뒤 관련 fixture를 실행한다. PostgreSQL 의존 건너뜀·mock provider·실데이터 읽기·실제 수집·배포 확인은 날짜와 환경을 구분해 기록한다. 이번 정리는 문서·참조 경로·식별자 검증에 한정한다.

## 복잡성 검토

기존 코드 경로와 계약을 이관했다. 향후 schema·인터페이스 변경 시 변경 근거와 마이그레이션·복구 계획을 기록한다.
