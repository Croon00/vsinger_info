# schedule_music

아티스트·YouTube 라이브·세트리스트·공연 정보를 수집하고 조회하는 프로젝트다. FastAPI 백엔드, PostgreSQL, 기존 관리 웹(`web.bak/`), 새 조회 프론트(`web/`), Discord 봇과 수집 worker로 구성된다.

## 시작하기

프로젝트 루트에서 백엔드를 준비한다. 이미 `.env`가 있으면 덮어쓰지 않는다.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
uvicorn app.main:app --reload
```

`.env`의 `DATABASE_URL`에 PostgreSQL 접속 정보를 설정한다. 현재 개발 데이터는 Neon PostgreSQL에 있으며, 로컬 API를 실행해도 DB가 로컬로 복사되지는 않는다. 주 서비스 DB는 SQLite가 아니다. `data/twscrape_accounts.db`는 X 수집 도구의 별도 계정 저장소다.

- API: http://127.0.0.1:8000
- API 문서: http://127.0.0.1:8000/docs
- 프로세스 상태: http://127.0.0.1:8000/health — DB 연결까지 검사하는 주소는 아니다.
- `app.main:app`과 `app.api.main:app`은 같은 API다.
- `DATABASE_AUTO_INIT=false`가 코드 기본값이다. 기존 스키마가 준비된 DB를 사용한다. `true`는 시작 시 `app/core/db.py`의 스키마·시드 초기화를 수행하므로 단순 조회 검증 때 켜지 않는다.

다른 터미널에서 새 프론트를 실행한다.

```powershell
cd web
npm install
npm run dev
```

http://localhost:5174 에서 실제 API를 사용한다. API 없이 디자인만 확인하려면 `npm run dev:mock`으로 http://localhost:5175 를 연다. 상세 환경변수·빌드·프록시는 [새 프론트 README](web/README.md)를 따른다.

사용자 조회 `/api/v2`는 루트 `.env.catalog`의 `NEW_CATALOG_DATABASE_URL`로 새 DB를 읽습니다. 기존 `DATABASE_URL`은 수집기·Discord 봇·기존 API용으로 유지하며 교체하지 않습니다. 앨범과 가사를 포함한 조회는 외부 수집 없이 저장된 자료만 사용합니다.

## 새 DB 관리자

`admin-web`에서 `npm ci`, `npm run build` 후 프로젝트 루트에서 `.\.venv\Scripts\python.exe scripts/run_admin.py`를 실행하고 http://127.0.0.1:8010 을 연다. 새 DB 설정은 `.env.catalog`의 `NEW_CATALOG_DATABASE_URL`만 사용한다. [사용 안내](docs/admin-web-plan.md)를 따른다.

## 실행 범위

| 명령/디렉터리 | 역할 |
| --- | --- |
| `uvicorn app.main:app --reload` | API만 실행. Discord 로그인과 주기 수집 loop는 시작하지 않음 |
| `python -m app.runtime` | API + Discord 봇, `AGENT_ENABLED=true`이면 수집 loop도 실행 |
| `web/` | 새 사용자 조회 화면. 기본 `/api/v2`, 별도 mock 모드 |
| `admin-web/` / `python scripts/run_admin.py` | 새 카탈로그 로컬 관리자. 빌드 후 127.0.0.1:8010, 초기 데이터는 명시적 검수·반영 |
| `web.bak/` | 기존 관리 웹. 유지 중이며 새 프론트의 시각 구현과 분리 |
| `scripts/` | 정규화, 수집, 등록 등 운영 도구. 실행 전 조회/변경 여부 확인 |

설정은 [`app/core/config.py`](app/core/config.py)와 [`.env.example`](.env.example)를 기준으로 한다. Python 코드 기본값과 예시 환경변수가 다를 수 있으며 실제 환경변수가 우선한다. DB·외부 서비스 키는 백엔드에 보관한다. 수집기 실행은 DB 저장·외부 알림을 동반하므로 화면 조회와 구분한다.

## 문서 안내

| 문서 | 다루는 내용 |
| --- | --- |
| [백엔드 구조·운영](docs/backend-architecture.md) | 실행 경계, 실제 수집 흐름, Discord 명령, 설정, 보안 |
| [조회 API v2](docs/read-api-v2.md) | 새 프론트 계약, 페이지·통계 기준, 성능 측정 |
| [프로필 이미지 저장](docs/avatar-storage.md) | Neon 이미지 이전, 크기 최적화, 캐시·교체와 복구 |
| [백엔드 후속 작업](docs/backend-roadmap.md) | 미지원 기능, 기존 미사용 API, 데이터 정제·곡 중심 확장 |
| [새 DB 구조·이전 계획](docs/db-renewal-plan.md) | 원격 스키마와 사용자 v2 연결 완료, 데이터 검수·운영 기능 이전은 별도 |
| [새 DB 마이그레이션](migrations/catalog/README.md) | 실제 적용 DDL, 전용 접속 설정, 실행·검증 범위 |
| [로컬 카탈로그 관리자](docs/admin-web-plan.md) | 실행·JSON 검수·승인 후 반영·수동 관리·백업 |
| [아티스트 식별](docs/artist-names.md) | 별칭·그룹 ID 보존, 이름 정규화 도구 |
| [YouTube 채널 보완](docs/youtube-channel-coverage.md) | 시드 등록 절차와 당시 확인 결과 |
| [새 프론트 실행](web/README.md) | 실제/mock 실행, 환경변수, 디렉터리, 배포 |
| [새 프론트 화면 설계](web/docs/design-plan.md) | 현재 화면·반응형·접근성·디자인 기준 |
| [검증 가이드](web/docs/qa.md) | 테스트 실행법, 검증 범위, 최근 결과 |
| [목업 콘텐츠 출처](web/docs/content-sources.md) | 공식 자료와 합성 데이터의 출처·한계 |
| [기존 관리 웹](web.bak/README.md) | 기존 프론트 실행과 유지 범위 |

`AGENTS.md`는 작업 규칙, README는 실행 안내를 다룬다. 현재 동작 문서와 미구현 계획을 구분하고, 계획서의 제안을 실행된 기능으로 해석하지 않는다. 검수 이력은 검증 문서에 모으고 폐기된 계획을 현재 사양과 나란히 유지하지 않는다. 코드로 확인하지 않은 운영 상태를 구현 완료로 표기하지 않는다.
