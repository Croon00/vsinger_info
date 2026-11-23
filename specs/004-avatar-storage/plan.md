# 구현 계획 — 프로필 이미지 저장·초기 이미지 작업

정리일 2026-11-18 · [요구사항](spec.md) · 기존 구현 구조와 후속 검증 이관

## 개요

기존 계약·실행 경로를 보존하고 FR-001~003과 SC-001~003을 검증 근거에 연결한다.

## 기술 구성

백엔드는 Python·FastAPI·Pydantic·SQLAlchemy·PostgreSQL, 관련 조회 웹은 Vue 3·TypeScript·Vite를 사용한다. 검증은 pytest·Vitest·Playwright를 사용한다. 실제 버전과 실행 환경은 검증 시 기록한다.

## 프로젝트 원칙 준수 점검

AGENTS.md와 [프로젝트 원칙](../../.specify/memory/constitution.md)을 따른다. 신규 DB 단일 설정·기존 DB 읽기 전용·출처와 수동 교정 보존·조회 중 수집 금지·외부 동작 범위를 점검한다. 원본의 legacy 경로는 현재 정상 실행 경로와 대조한다.

## 문서와 코드 구조

이 디렉터리의 spec.md·plan.md·tasks.md에서 요구사항·설계·작업을 연결한다. 상세 계약과 날짜별 원본은 docs에서 관리한다.

- `app/services/avatar_storage.py`
- `app/services/avatar_jobs.py`
- `app/repositories/avatar_jobs.py`
- `app/integrations/avatar_sources.py`
- `scripts/avatar_jobs.py`
- `web/src/lib/avatar-image.ts`

## 조사와 설계

2026-11-21 명시적 복구는 `scripts/repair_requested_profiles_20261121.py`로 수행한다. 정확한 두 ID/slug와 기존 관리 URL을 확인하고 저장된 original로 생성한 128/256px 결과가 현재 파일과 바이트 단위로 같을 때만 512px를 복구한다. 저장 대상 host와 설정 endpoint를 대조하고 IfNoneMatch=*로 기존 객체 덮어쓰기를 방지한다. 공개 내용·Cache-Control 검증 후 영수증에 복구 경로·해시·크기를 남긴다. 원본 URL·기존 사진·소유 관계는 보존하며 일반 worker나 조회 경로는 변경하지 않는다.

Neon Object Storage에 콘텐츠 해시 경로로 저장한다. migration 007 trigger가 owner 관계 변경과 같은 transaction에서 avatar_jobs를 예약한다. 독립 이미지 loop가 다운로드·가공·업로드·공개 검증을 수행하고 대표 URL과 catalog_changes를 반영한다.

원본 계약과 근거는 다음 문서를 따른다.

- [avatar-storage](../../docs/avatar-storage.md)

## 검증과 운영 적용

- `tests/test_avatar_storage.py`
- `tests/test_avatar_jobs.py`
- `tests/test_avatar_sources.py`
- `web/tests/unit/avatar-image.test.ts`

US1의 FR-001·FR-002·FR-003은 각각 SC-001·SC-002·SC-003과 대조한다. 기존 테스트의 실제 적용 범위를 확인한 뒤 관련 fixture를 실행한다. PostgreSQL 의존 건너뜀·mock provider·실데이터 읽기·실제 수집·배포 확인은 날짜와 환경을 구분해 기록한다. 이번 정리는 문서·참조 경로·식별자 검증에 한정한다.

## 복잡성 검토

기존 코드 경로와 계약을 이관했다. 향후 schema·인터페이스 변경 시 변경 근거와 마이그레이션·복구 계획을 기록한다.
