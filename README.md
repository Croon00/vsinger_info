# UtaMowa (우타모와)

VTuber·버추얼 싱어의 YouTube 라이브·세트리스트·커버·발매곡·공연 일정을 수집하고 조회하는 프로젝트다. FastAPI 백엔드, PostgreSQL(신규 DB), 조회 프론트 `web/`, X 새 글을 Discord로 알리는 봇과 수집 worker로 구성된다.

작업 규칙은 [AGENTS.md](AGENTS.md), 공통 원칙은 [constitution](.specify/memory/constitution.md), 스펙 기반 작업은 [작업 안내](docs/spec-driven-development.md)와 [기능 스펙 목록](specs/README.md)에서 시작한다.

## 빠른 시작

프로젝트 루트에서 백엔드를 준비한다. 이미 `.env`가 있으면 덮어쓰지 않는다.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
uvicorn app.main:app --reload
```

`.env` 또는 서버 환경변수의 `DATABASE_URL`에 신규 PostgreSQL 접속 정보를 설정한다. 현재 개발 데이터는 Neon PostgreSQL에 있으며 로컬 API를 실행해도 DB가 로컬로 복사되지 않는다. 이전 원본을 읽는 도구에만 `LEGACY_DATABASE_URL`을 따로 제공한다. 설정 기준은 [`app/core/config.py`](app/core/config.py)와 [`.env.example`](.env.example)이며 실제 환경변수가 우선한다.

- API http://127.0.0.1:8000, 문서 http://127.0.0.1:8000/docs
- `/health`: 프로세스 상태. DB 연결은 검사하지 않는다.
- `/ready`: 신규 DB와 음악 worker 상태. worker가 활성화됐는데 필수 provider 인증, handler 또는 heartbeat가 빠지면 `ready=false`다.

다른 터미널에서 프론트를 실행한다.

```powershell
cd web
npm install
npm run dev
```

http://localhost:5174 에서 실제 API를 사용한다. API 없이 디자인만 확인하려면 `npm run dev:mock`(http://localhost:5175)을 쓴다. 자세한 내용은 [프론트 README](web/README.md)를 따른다.

## 실행 범위

| 명령 | 역할 |
| --- | --- |
| `uvicorn app.main:app --reload` | 조회 API만 실행. Discord 로그인과 주기 수집을 시작하지 않는다. `app.main:app`과 `app.api.main:app`은 같은 API다 |
| `python -m app.runtime` | 배포 진입점(Railway). API와 공개 라이브 일정 감시를 실행하고, `RUNTIME_CUTOVER_ENABLED=true`이면 Discord 봇, 여기에 `AGENT_ENABLED=true`이면 수집 loop도 실행한다 |
| `python -m app.services.youtube_live_monitor` | 멀티뷰 생방송 확인만 단독 실행. 주기와 Holodex 설정은 [조회 API](docs/read-api.md)를 따른다 |
| `python -m app.agents.live_site_monitor` | 공개 라이브 일정을 한 번 수집. [공개 라이브 일정](docs/live-site-monitor.md) |

수집기는 DB 저장과 외부 알림을 동반하므로 화면 조회와 구분해 실행한다. Railway에는 백엔드 Variables를 따로 설정하고 코드를 배포해야 한다. 로컬 `.env`는 배포되지 않는다. 빈 작업 큐는 `WORKER_IDLE_SECONDS=900`(기본) 간격으로 확인하며 근거는 [백엔드 구조](docs/backend-architecture.md#db-유휴-대기)에 있다.

## 운영 도구

`scripts/`의 도구는 서버 시작이나 조회 API에 연결되지 않는다. 실행 전 DB 변경·외부 호출 여부를 확인한다. 전체 목록은 [scripts 안내](scripts/README.md)에 있다.

| 명령 | 용도 | 문서 |
| --- | --- | --- |
| `python scripts/refresh_youtube_video_statistics.py` | 커버·발매곡 조회수 갱신. 화면은 저장된 값만 사용 | [곡 탐색](docs/song-exploration.md) |
| `python scripts/refresh_youtube_channel_statistics.py` | 채널 구독자 수 즉시 갱신. 정상 YouTube poll도 함께 갱신 | [아티스트 정렬](docs/artist-sorting.md) |
| `python scripts/backfill_catalog_youtube_covers.py --until-complete` | 공식 채널의 과거 커버 수집 | [YouTube 커버](docs/youtube-covers.md) |
| `python scripts/avatar_jobs.py enqueue --artist-id ID` / `status ID` | 빈 프로필 이미지 작업 등록·결과 조회 | [프로필 이미지 저장](docs/avatar-storage.md) |
| `python scripts/discover_spotify_accounts.py --output outputs/spotify-discovery-배치명` | Spotify 미연결 아티스트 조사(기본 읽기 전용, `--apply --run 배치명`으로 반영) | [Spotify 이름 일치 연결](docs/spotify-exact-name-discovery.md) |
| `python scripts/music_jobs.py` | 음악 worker 작업 등록·단일 실행·readiness 확인 | [작업 실행기 기록](docs/records/backend/backend-service-step-2-jobs.md) |

## 운영 상태

2026-09-23 신규 DB로 이전했다([전환 기록](docs/records/backend/backend-cutover-2026-09-23.md)). X provider 오류 확인, Discord 활성화, 프로필 이미지 worker의 서버 저장소 설정 등 운영 확인 작업이 남아 있다. 전체 미완료 항목은 [후속 작업](docs/backend-roadmap.md), 완료 조건은 [서비스 보완 계획](docs/plans/backend-service-readiness-plan.md)을 따른다.

## 문서

| 위치 | 내용 |
| --- | --- |
| `docs/` | 현재 구조와 계약. 아래 표의 문서 |
| [`docs/plans/`](docs/plans/) | 확정 계획과 설계 근거(통합 최종 계획, 서비스 보완 계획, DB·곡 마스터·세트리스트 이관 계획) |
| [`docs/records/backend/`](docs/records/backend/) | 백엔드 통합·보완 단계별 결과, 운영 이전·복구·성능 측정 기록 |
| [`docs/records/data/`](docs/records/data/) | 날짜별 아티스트 등록·수집·세트리스트 정정 기록 |
| [`specs/`](specs/README.md) | 기능별 요구사항·설계·작업 |

| 현재 계약 문서 | 다루는 내용 |
| --- | --- |
| [백엔드 구조·운영](docs/backend-architecture.md) | 실행 경계, 수집·Discord URL 전송 흐름, 설정, 보안 |
| [조회 API](docs/read-api.md) | 프론트 계약, 페이지·통계 기준, 생방송 멀티뷰 |
| [카탈로그 테이블·필드](docs/catalog-schema.md), [마이그레이션](migrations/catalog/README.md) | 신규 DB 필드 설명, 적용 DDL |
| [저장소 구조](docs/repository-structure.md) | 디렉터리 역할과 관리 기준 |
| [후속 작업](docs/backend-roadmap.md) | 미지원 기능과 남은 작업 |
| [아티스트 식별](docs/artist-names.md), [아티스트 정렬](docs/artist-sorting.md), [공유 YouTube 채널](docs/shared-youtube-channels.md) | 아티스트 명의·정렬·공유 채널 |
| [YouTube 커버](docs/youtube-covers.md), [세트리스트 후보 비교](docs/youtube-setlist-selection.md) | YouTube 수집·분류 |
| [곡 탐색](docs/song-exploration.md), [음악 분류](docs/original-music-tags.md), [디스코그래피 YouTube 연결](docs/discography-youtube-links.md), [Spotify 이름 일치 연결](docs/spotify-exact-name-discovery.md) | 곡·발매 음원 |
| [프로필 이미지 저장](docs/avatar-storage.md), [공개 라이브 일정](docs/live-site-monitor.md) | 이미지·공연 일정 |
| [YouTube 오리지널 일일 수집](docs/youtube-original-collection.md) | 기존 하루 1회 채널 확인을 공유하는 오리지널 발매곡 연결·등록 |
| [프론트 화면 설계](web/docs/design-plan.md), [검증 가이드](web/docs/qa.md), [목업 콘텐츠 출처](web/docs/content-sources.md) | 프론트 |

현재 동작 문서와 계획을 구분하고, 계획서의 제안을 실행된 기능으로 해석하지 않는다. 코드로 확인하지 않은 운영 상태를 구현 완료로 표기하지 않는다.
