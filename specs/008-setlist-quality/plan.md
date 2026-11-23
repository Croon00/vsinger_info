# 구현 계획 — 세트리스트 이전·후보 선택·가창 정정과 복구

정리일 2026-11-18 · [요구사항](spec.md) · 기존 구현 구조와 후속 검증 이관

## 개요

기존 계약·실행 경로를 보존하고 FR-001~003과 SC-001~003을 검증 근거에 연결한다.

## 기술 구성

백엔드는 Python·FastAPI·Pydantic·SQLAlchemy·PostgreSQL, 관련 조회 웹은 Vue 3·TypeScript·Vite를 사용한다. 검증은 pytest·Vitest·Playwright를 사용한다. 실제 버전과 실행 환경은 검증 시 기록한다.

## 프로젝트 원칙 준수 점검

AGENTS.md와 [프로젝트 원칙](../../.specify/memory/constitution.md)을 따른다. 신규 DB 단일 설정·기존 DB 읽기 전용·출처와 수동 교정 보존·조회 중 수집 금지·외부 동작 범위를 점검한다. 원본의 legacy 경로는 현재 정상 실행 경로와 대조한다.

## 문서와 코드 구조

이 디렉터리의 spec.md·plan.md·tasks.md에서 요구사항·설계·작업을 연결한다. 상세 계약과 날짜별 원본은 docs에서 관리한다.

- `app/services/youtube_setlist_rules.py`
- `app/services/youtube_setlist.py`
- `scripts/import_legacy_setlists.py`
- `scripts/link_performance_artists.py`
- `scripts/retry_pending_youtube_setlists.py`

## 조사와 설계

2026-11-21 FR-004~005: `setlist-rules-2`에서 일반 타임스탬프 제목을 기존 SetList 제목과 무조건 동일 취급하지 않는다. 별도 추출기로 한 댓글 안의 연속 번호·시간·곡정보·종료 경계를 검증하고 기존 후보 비교를 유지한다. 곡번호만 있는 감상 댓글은 곡 정체성 충돌로 취급하지 않되, 제목·원곡자 구조가 있는 다른 후보는 계속 충돌 검사한다. `セトリ＆シーン`은 명시적 구분선 앞 구간만 기존 엄격 추출기로 검증한다. 필드의 원문 포함과 근거 행을 보존한다.

`scripts/recover_rule_setlists.py`는 기본 읽기 전용 조사다. 공개 카탈로그 전체에서 빈 방송을 조사하고, 보관 가창 존재·계정/영상 접근 불가·댓글 원문 부재·추가 형식 검토 필요를 구분한다. `--apply`는 규칙이 선택한 항목만 정확한 ID/계정·archive 잠금·typed job key·lease·snapshot을 재검증한 뒤 기존 원자 저장을 사용한다. OpenAI 호출과 YouTube 재수집은 하지 않는다. 사용자 영상만 별도로 YouTube 댓글 API로 확인한 실데이터 검증과 구분한다. 실행 보고서는 `outputs/rules-recovery-2026-11-21/`에 보존한다.

규칙 확정→필요 후보만 모델 비교→원문 행·시간·schema 검증→원자 저장 순서를 따른다. 후보 최대 3개와 원본의 제한 재시도를 적용한다. source hash·작업 키·version으로 재실행을 보호하고 source_documents/archive_sources/performances에 출처를 연결한다. 기존 DB는 읽기 전용·보존 덤프 근거로 다룬다.

원본 계약과 근거는 다음 문서를 따른다.

- [setlist-migration-report](../../docs/records/backend/setlist-migration-report.md)
- [performance-artists-2026-10-04](../../docs/records/data/performance-artists-2026-10-04.md)
- [youtube-setlist-selection](../../docs/youtube-setlist-selection.md)
- [live-5850-correction-2026-10-07](../../docs/records/data/live-5850-correction-2026-10-07.md)
- [youtube-cutover-recovery-2026-10-09](../../docs/records/backend/youtube-cutover-recovery-2026-10-09.md)
- [setlist-cleanup-2026-10-10](../../docs/records/data/setlist-cleanup-2026-10-10.md)
- [setlist-refresh-2026-10-30](../../docs/records/data/setlist-refresh-2026-10-30.md)
- [setlist-model-recovery-2026-10-31](../../docs/records/data/setlist-model-recovery-2026-10-31.md)
- [song-master-plan](../../docs/plans/song-master-plan.md)

## 검증과 운영 적용

- `tests/test_legacy_setlist_import.py`
- `tests/test_youtube_setlist_rules.py`
- `tests/test_youtube_setlist_selection.py`
- `tests/test_link_performance_artists.py`

US1의 FR-001·FR-002·FR-003은 각각 SC-001·SC-002·SC-003과 대조한다. 기존 테스트의 실제 적용 범위를 확인한 뒤 관련 fixture를 실행한다. PostgreSQL 의존 건너뜀·mock provider·실데이터 읽기·실제 수집·배포 확인은 날짜와 환경을 구분해 기록한다. 이번 정리는 문서·참조 경로·식별자 검증에 한정한다.

## 복잡성 검토

기존 코드 경로와 계약을 이관했다. 향후 schema·인터페이스 변경 시 변경 근거와 마이그레이션·복구 계획을 기록한다.
