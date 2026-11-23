# 파일 구조와 관리 기준

2026-11-23 현행화. 2026-09-20~21 정리 당시의 구조·검증은 [정리 기록](records/backend/repository-cleanup-2026-09-21.md)에 있다. 실행 경로와 데이터 흐름은 [백엔드 구조](backend-architecture.md)를 따른다.

## 최상위 구조

```text
schedule_music/
├─ app/                  Python 애플리케이션(API·runtime·수집)
├─ web/                  사용자 조회 Vue 앱 → /api
├─ scripts/              명시적으로 실행하는 운영 도구
├─ tests/                Python fixture·로컬 DB 회귀 테스트
├─ migrations/catalog/   신규 DB의 버전 고정 SQL·스키마 계약·적용 보고서
├─ docs/                 현재 구조·계약 (plans/, records/ 하위 포함)
├─ specs/                기능별 spec·plan·tasks (Spec Kit)
├─ .specify/             Spec Kit 원칙·템플릿·스크립트
├─ data/                 등록 도구의 시드(seeds/)와 분류 자료(classification/)
├─ artifacts/            작업 기록이 참조하는 소수의 원본 자료
├─ db-migration/         로컬 입력·보고서·이전 백업(README만 추적)
├─ requirements.txt, runtime.txt, railway.json, railpack.json
└─ .env.example          환경변수 예시
```

Git에서 제외: `.env`·`.env.*`, 가상환경, `node_modules`·빌드 결과, `*.log`, `.tmp/`, `exports/`, `outputs/`, `data/*.db`(X 수집 도구 계정 저장소 등), `db-migration/`의 입력·작업·보고서·archive. 루트에 임시 `check_*.py`나 dump를 쌓지 않고 `.tmp/` 또는 `outputs/`를 사용한다.

## Python 경계

| 경로 | 책임 | 상태 |
| --- | --- | --- |
| `app/main.py`, `app/api/main.py` | FastAPI 앱. `routers/read_api.py`만 `/api`·`/api/v2`에 마운트하고 `/health`·`/ready` 제공 | 운영 |
| `app/runtime.py` | 배포 진입점. API와 X scheduler, Discord 봇, 음악·이미지 worker, 생방송·공개 라이브 일정 감시를 설정에 따라 실행 | 운영 |
| `app/api/routers/` 중 `artists`·`songs`·`youtube`·`spotify`·`auth` | 구 API | 보존 전용(미마운트) |
| `app/schemas/` | Pydantic 요청·응답·작업 모델 | 운영 |
| `app/services/`, `app/repositories/` | 업무 처리와 SQL. 조회는 각각의 `catalog_read.py` | 운영. `services/read_catalog.py`, `read_spotify.py`는 v2 전환 전 보존 코드 |
| `app/db/catalog_session.py` | 신규 DB의 identity-guarded 연결 풀·Session | 운영 |
| `app/db/session.py`, `app/core/db.py` | 기존 DB 연결과 증분 초기화. 호출 시 오류를 내도록 차단 | 보존 전용 |
| `app/core/` | 설정·API 키 검사·아티스트 식별·곡 키 | 운영 |
| `app/integrations/` | 외부 provider adapter. 목록은 [영역 지침](../app/integrations/AGENTS.md) | 일부 보존 전용(Google Calendar, 노래방) |
| `app/agents/` | X scheduler, 공개 라이브 일정 감시 | 운영 |
| `app/bots/` | 명령 없는 Discord URL sender | 운영 |
| `app/legacy/` | Google helper 전용 설정 | 보존 전용 |
| `app/lyrics_pipeline/` | 가사 수집·변환 | 후속 TODO, worker에서 실행하지 않음 |
| `app/data/` | 아티스트 식별용 내장 별칭 자료 | 운영 |

이름이 비슷한 보존 코드와 운영 코드는 사용 종료를 확인하기 전 병합하지 않는다. 보존 전용 코드는 사용자 요청 없이 운영 경로에 다시 연결하지 않는다.

## 프론트

`web/`만 유지한다. 실행·검증은 [프론트 README](../web/README.md)와 [QA](../web/docs/qa.md)를 따른다. 기존 관리 웹 `web.bak/`과 로컬 관리자 `admin-web/`(+ `app/admin/`, `scripts/run_admin.py`, `scripts/export_admin_contract.py`, `schemas/import/v1/`)은 운영 경로와 연결되지 않아 2026-11-23 삭제했다. 코드는 Git 이력에 있고 당시 계약은 [관리자 기록](records/backend/admin-web-plan.md)에 있다. 관리 기능은 후속으로 새로 설계한다.

## 문서 배치

| 위치 | 내용 | 규칙 |
| --- | --- | --- |
| `README.md` | 실행법과 문서 진입점 | 상세 계약·작업 기록을 넣지 않는다 |
| `AGENTS.md`, 영역별 `AGENTS.md` | 에이전트 작업 지침 | 현재 경계만 유지한다 |
| `.specify/memory/constitution.md` | 공통 원칙 | 변경 시 버전을 올린다 |
| `docs/` 루트 | 현재 구조·계약 | 현재 동작만 쓴다. 날짜별 경과는 records로 보내고 요약·링크만 남긴다 |
| `docs/plans/` | 확정 계획과 설계 근거 | 계획을 구현 완료로 해석하지 않는다 |
| `docs/records/backend/` | 백엔드 단계별 결과, 운영 이전·복구·성능·정리 기록 | 당시 날짜·수치를 보존한다 |
| `docs/records/data/` | 날짜별 아티스트 등록·수집·세트리스트 정정 기록 | 파일명에 날짜를 넣는다 |
| `docs/backend-roadmap.md` | 전체 미완료 작업 | 완료 항목은 근거 링크와 날짜를 남긴다 |
| `specs/` | 기능별 요구사항·설계·작업 | [스펙 작업 안내](spec-driven-development.md)를 따른다 |
| `web/docs/` | 프론트 화면 설계·QA·목업 출처 | `web/AGENTS.md`를 따른다 |

## 스키마 계약

`migrations/catalog/`의 SQL은 적용 체크섬을 고정하며 `columns.json`, `expected-schema.json`은 계약·구조 drift 검증에 쓰인다. 중복 초안이 아니므로 유지한다. 필드 설명은 [catalog-schema.md](catalog-schema.md)에 있다.
