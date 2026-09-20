# 파일 구조와 관리 기준

분석·정리: 2026-09-20~21. 정리 전 Git 추적 파일 770개와 루트의 미추적 검수 파일 104개를 대상으로 경로·import·실행 진입점·문서 링크를 확인했다. 가상환경과 node_modules 내부는 의존성 설치물로 취급한다.

## 최상위 구조

```text
schedule_music/
├─ app/                     Python 애플리케이션
├─ web/                     사용자 조회 Vue 앱 → /api/v2
├─ admin-web/               새 카탈로그 검수 Vue 앱 → /api/admin
├─ web.bak/                 기존 관리 Vue 앱 → 기존 API
├─ scripts/                 명시적으로 실행하는 운영 도구
├─ tests/                   Python fixture·로컬 DB 회귀 테스트
├─ migrations/catalog/     버전 고정 SQL·스키마 계약·적용 보고서
├─ schemas/import/v1/       JSON 가져오기 계약·예제·사용 안내
├─ docs/                    현재 구조·API 계약·설계·후속 작업
├─ data/seeds/              등록 도구에서 사용하는 공유 시드
├─ db-migration/            로컬 입력·검수 장부·백업
├─ .tmp/                    Git 제외 일회성 분석·테스트 출력
├─ .env.example             기존 서비스 환경변수 예시
├─ requirements.txt         Python 의존성
└─ railway.json, railpack.json, runtime.txt
                           기존 런타임 배포 설정
```

`.env`, `.env.catalog`, 가상환경, 프론트 빌드/의존성, 로그, 검수 원본·백업은 Git에서 제외한다. 루트에는 프로젝트 공통 설정과 안내만 두고 임시 `check_*.py`, dump 텍스트 등을 쌓지 않는다.

## Python 경계

| 경로 | 책임 |
| --- | --- |
| `app/main.py` | 기존 `uvicorn app.main:app` 진입점 호환 |
| `app/api/main.py` | FastAPI 수명주기·CORS·라우터 조립·health |
| `app/api/routers/` | 아티스트·곡·YouTube·Spotify·Google OAuth·v2 HTTP 계약 |
| `app/schemas/`, `app/core/models.py` | Pydantic 모델. 일부 기존 모델은 호환 re-export 유지 |
| `app/services/`, `app/repositories/` | 업무 처리와 SQL 접근. 새 조회는 각각의 `catalog_read.py` |
| `app/db/` | 기존/새 카탈로그의 독립 연결 풀·Session과 기존 ORM 모델 |
| `app/core/` | 설정·보안·아티스트 식별·기존 증분 초기화 |
| `app/integrations/` | 외부 provider adapter |
| `app/agents/`, `app/bots/`, `app/runtime.py` | scheduler·LangGraph helper·Discord·통합 런타임 |
| `app/lyrics_pipeline/` | 가사 수집·변환·저장 |
| `app/admin/` | 별도 관리자 앱·검수 SQLite·승인·새 카탈로그 반영 |
| `app/data/` | 아티스트 식별 로직에서 사용하는 내장 별칭 자료 |

`services/catalog_read.py`와 `repositories/catalog_read.py`는 계층이 다르다. 기존 `services/read_catalog.py`, `read_spotify.py`는 v2 전환 전 구현과 회귀 테스트를 보존한 코드이며 현재 v2 라우터가 사용하지 않는다. 기존 API 사용 종료가 확인되기 전 이름만 비슷하다는 이유로 병합하지 않는다.

Google·Spotify 라우터가 `api/main.py`를 역으로 import하던 구조를 제거했다. 실행 중인 함수는 각 라우터로 이동했고, 기존 아티스트·곡·YouTube 라우터와 중복되던 미마운트 구현만 삭제했다. Google/Spotify의 기존 접근 제어와 DB 처리 방식은 유지하며 보안 완성이나 service/repository 분리 완료로 간주하지 않는다.

## 세 웹 앱을 유지하는 이유

| 앱 | 대상 | 개발 포트 | 코드·검증 |
| --- | --- | --- | --- |
| `web/` | 사용자 조회와 명시적 mock 모드 | 5174 / mock 5175 | `src/`, `tests/`, `scripts/`, `docs/` |
| `admin-web/` | 새 카탈로그 로컬 검수·관리 | 5176, API/정적 제공 8010 | `src/`, `tests/` |
| `web.bak/` | 기존 DB 관리·등록 | 5173 | `src/` 단위 테스트, `e2e/` |

`web.bak`은 이름과 달리 폐기된 백업이 아니다. 세 앱은 실행·배포·의존성이 독립되어 있어 각 `package.json`과 lockfile을 유지한다. 루트에는 npm 프로젝트가 없어 빈 루트 lockfile을 삭제했다.

`web/`와 `admin-web/`의 shadcn 컴포넌트 중 같은 생성물이 있지만, 소수 중복을 없애려고 공유 패키지와 앱 간 import를 새로 만들지 않았다. 각 앱의 실제 import 연결을 확인하여 관리자에서 미참조인 `ui/table/` 10개만 제거했다. 사용 중인 컴포넌트 패밀리의 하위 구성 요소와 barrel export는 함께 유지한다. 목업·이미지·QA 캡처는 테스트와 출처 기록에 사용되므로 보존한다.

## 문서·데이터 통합

- 테이블·필드 명세는 [catalog-schema.md](catalog-schema.md), 적용 결과는 [migrations 보고서](../migrations/catalog/schema-application-report.json)로 모았다.
- `db-migration`의 문서 연결용 중복 파일 2개는 삭제하고 [로컬 자료 안내](../db-migration/README.md)로 진입점을 통합했다.
- [DB 설계](db-renewal-plan.md)와 [관리자 안내](admin-web-plan.md)의 이전 “v2 전환 미구현” 문구를 현재 코드에 맞췄다. 과거 데이터 건수는 당시 검증 기록으로 유지한다.
- 루트의 Python 91개·텍스트 13개는 앱·테스트·운영 도구에서 참조하지 않는 일회성 외부 `DB_DATA` 검수 파일이었다. 원문과 수작업 교정값을 ZIP·SHA-256 목록으로 보존한 뒤 루트에서 제거했다.
- 기존 DB dump·export ZIP·미참조 나무위키 템플릿은 [로컬 archive](../db-migration/README.md)에 보존하고 소스 트리에서 제외했다. 실제 DB와 외부 `DB_DATA` 파일은 변경하지 않았다.
- 내용이 생긴 기존 프론트 디렉터리의 `.gitkeep` 5개를 제거하고, 세 프론트에 반복되던 `.gitignore` 규칙을 공통 패턴으로 통합했다.

DDL과 JSON 계약은 중복 초안이 아니다. `001_initial.sql`은 적용 체크섬을 고정하고 `columns.json`, `expected-schema.json`은 계약·구조 drift 검증에 쓰인다. 관리자 `resources.json`과 `schemas/import/v1/`도 각 실행·입력 검증에서 사용하므로 유지한다.

## 검증

API 정리 전후 88개 경로의 메서드·응답 모델·상태·의존성과 OpenAPI 전체 일치를 확인했다. 새 라우터 회귀 테스트는 import 순서, 기존 경로와 `/api` 별칭, 외부 호출을 mock한 Google callback·Spotify 오류 처리를 확인한다.

2026-09-21 최종 검증 결과:

| 검증 | 결과·범위 |
| --- | --- |
| Python 전체 `pytest tests -q -p no:cacheprovider` | 162개 통과, 2개 건너뜀. 외부 provider mock·fixture와 로컬 임시 PostgreSQL/SQLite 사용 |
| `web` Vitest | 26개 통과 |
| `web.bak` Vitest | 13개 통과 |
| `web`, `admin-web` 빌드 | 각 앱의 vue-tsc 검사와 Vite production build 통과 |
| 라우트/OpenAPI 비교 | 기존 88개 경로 계약·전체 OpenAPI 일치 |
| 파일·문서 검사 | 104개 백업의 SHA-256, 원본 dump/ZIP 일치, 템플릿 JSON 내용 일치, 문서 상대 링크, PowerShell 구문, `git diff --check` 통과 |

테스트용 PostgreSQL은 `tests/test_catalog_migration.py`의 로컬 임시 클러스터를 사용했다. 샌드박스의 PostgreSQL 프로세스 시작 제한으로 권한 승격 후 재실행했으며 운영 Neon으로 대체하지 않았다. 기존 `tests/test_api.py` 2개는 `TEST_DATABASE_URL`을 지정하지 않아 건너뛰었다. 이번 정리에서 실데이터 검증·재수집·외부 전송·브라우저 E2E는 실행하지 않았다.

현재 셸의 npm 런처에는 활성 Node 버전이 없어, 설치된 프로젝트 의존성을 Codex 번들 Node로 직접 실행했다. 위 프론트 검증은 `package.json`의 Vitest/vue-tsc/Vite 명령과 동일한 옵션을 사용했고 전역 Node 설정이나 의존성을 변경하지 않았다. 기존 프론트 테스트의 Vue injection 경고와 Python 의존성 deprecation 경고는 남아 있다.
