# 백엔드 구조와 운영

기준: 2026-09-22, 저장소 코드. 실제 계정 연결·프로세스 가동 여부는 실행 환경에 따라 다르다. 설치는 [루트 README](../README.md), 새 조회 계약은 [API v2](read-api-v2.md), 미완료 사항은 [후속 작업](backend-roadmap.md)을 따른다.

> [5단계 운영 전환](backend-phase-5-cutover.md)의 코드 준비까지 구현했다. 정식 조회 API와 X/Discord 실행 코드는 신규 DB 전용이다. 실제 상태 이전과 운영 활성화는 Railway 전환 시간에 수행한다.

## 구성과 데이터 경로

```text
새 프론트 → /api → CatalogRead → CatalogReadRepository → 신규 통합 DB (읽기 전용)
기존 API router → 정상 app에서 미마운트, legacy 코드로 보존
runtime → API + Discord bot + 선택적 scheduler
```

| 위치 | 책임 |
| --- | --- |
| `app/api/main.py`, `app/api/routers/` | 앱 수명주기, 라우터 등록, HTTP 상태·입출력 |
| `app/schemas/` | Pydantic 요청·응답 모델 |
| `app/services/` | 조회·업무 처리. v2는 `catalog_read.py`, 이전 `read_catalog.py`는 레거시 구현 |
| `app/repositories/` | 기존 도메인의 DB 조회·저장과 새 v2의 catalog_read.py 조회 SQL |
| `app/db/catalog_session.py` | 신규 통합 DB 전용 공유 풀·요청별 READ ONLY Session과 worker용 쓰기 Session, `001/002`·`catalog-v2`·선택적 instance ID guard |
| `app/db/session.py` | URL별 공유 SQLAlchemy Engine/연결 풀, 요청별 Session |
| `app/core/db.py` | 기존 psycopg 연결, 증분 스키마·시드 초기화. 관리 중인 신규 통합 DB에서는 init 거부 |
| `app/integrations/` | YouTube, Spotify, X, OpenAI, Google 등 |
| `app/agents/scheduler.py` | 신규 DB X poller와 Discord delivery 실행. 다른 수집기·Google 호출 없음 |
| `app/bots/discord_bot.py` | command 없는 Discord 연결과 X 원문 URL 전송 adapter |
| `app/repositories/runtime_delivery.py` | X account/state lease, 원문·delivery 원자 저장, 전송 상태 SQL |
| `app/services/x_collection.py` | external_accounts 기반 pagination과 계정별 실패 격리 |
| `app/services/notification_delivery.py` | offline·retry·failed·unknown을 포함한 durable 전송 상태 전이 |
| `app/core/config.py` | 환경변수·루트 `.env`와 과도기 `.env.catalog` 공통 설정 |

모든 경로가 ORM이나 하나의 연결 풀로 통일된 상태는 아니다. 레거시 psycopg 직접 연결도 남아 있다. 스키마 초기화를 `Base.metadata.create_all`로 대체하지 않는다. 현재 증분 변경과 시드 동작을 먼저 마이그레이션으로 옮겨야 한다.

아티스트·소스·원문·공연 후보·알림 route/전송 이력·Google 연결/동기화·YouTube 아카이브/가창 기록·곡/가사·Spotify 연동 데이터를 PostgreSQL에 저장한다. 엔티티 매핑은 `app/db/models/`, 실제 초기화 SQL은 `app/core/db.py`를 함께 확인한다. 이 문단은 기존 서비스 구조다. 새 사용자 조회는 migrations/catalog의 정규화된 별도 스키마를 사용하며 [조회 API v2](read-api-v2.md)에 연결 기준을 정리했다.

## 현재 수집 흐름

현재 scheduler의 X 처리는 다음과 같다.

```text
신규 DB의 활성 external_accounts(platform=x) lease
→ since_id 이후 X pagination 전체 확보
→ source_items 중복 제거 + 활성 route별 pending delivery 생성 + cursor 갱신
→ Discord가 준비된 경우 pending/retry 원문 URL 전송
→ sent/message ID 또는 retry/failed/unknown 상태 기록
```

원문·delivery·cursor는 계정별 transaction으로 함께 반영한다. pagination 제한 초과나 provider 오류가 나면 cursor를 전진시키지 않는다. 봇이 offline이면 pending을 claim하지 않으며, 전송 시작 뒤 결과가 불명확한 채 lease가 만료되면 unknown으로 두어 자동 중복 전송을 막는다.

X 분류·공연/티켓 추출 workflow와 `music_graph.py`는 제거했다. X 본문의 링크를 열거나 YouTube archive를 등록하거나 Google Calendar를 호출하지 않는다. X 본문에 YouTube URL이 있어도 원문 문자열로만 보존한다.

독립 YouTube setlist 추출과 음악 integration은 보존했지만 최소 scheduler가 실행하지 않는다. Discord 명령 제거로 이 기능들의 관리 진입점도 없어졌으며 신규 admin-web 연결은 후속 작업이다.

## Discord 사용

Discord 봇에는 slash command, interaction, command tree가 없다. 아티스트·source·route·YouTube·Spotify·가사·Google 관리를 제공하지 않는다. 이미 신규 DB에 설정된 활성 route의 channel로 X `source_url` 한 줄만 보낸다. route가 없으면 원문만 저장하고 delivery를 만들지 않는다. 원격 Discord 애플리케이션에 과거 command가 남아 있다면 6단계 배포 검증에서 제거한다.

## 설정과 실행 경계

| 설정 | 용도 / 코드 기본값 |
| --- | --- |
| `DATABASE_URL` | 기존 API용 PostgreSQL. 신규 X/Discord runtime은 사용하지 않음 |
| `NEW_DATABASE_URL` | 통합 사용자 API·관리자·X poller·Discord sender용 신규 통합 DB. 루트 .env.catalog 또는 환경변수 |
| `DATABASE_AUTO_INIT` | 시작 시 초기화, 기본 false |
| `API_KEY` | 일부 기존 라우터와 v2의 선택적 X-API-Key 인증 |
| `RUNTIME_CUTOVER_ENABLED` | 운영 DB 전환 승인이 끝난 뒤 Discord/수집 runtime 활성화, 코드 기본 false |
| `AGENT_ENABLED` / `AGENT_RUN_ON_START` | runtime 수집 / 시작 직후 실행, 코드 기본 false / false |
| `AGENT_INTERVAL_SECONDS` | 코드 기본 86400초. 수집량과 제공자 제한을 보고 운영 환경에서 조정 |
| `DISCORD_BOT_TOKEN` | URL 전송 전용 봇 인증. `DISCORD_GUILD_ID`는 과거 command 설정으로 현재 봇이 사용하지 않음 |
| `X_PROVIDER` | auto / twscrape / x_api; 필요한 인증은 선택한 provider에 설정 |
| `YOUTUBE_API_KEY` | YouTube 수집 |
| `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET` | Spotify 조회·매칭 |
| `OPENAI_API_KEY`, `OPENAI_MODEL` | 명시적으로 호출되는 추출·번역 등 |
| `PUBLIC_BASE_URL`, `GOOGLE_CLIENT_*`, `GOOGLE_REDIRECT_URI` | 기존 Google legacy 경로 설정. X/Discord runtime은 사용하지 않음 |
| `PORT` | runtime API 포트, 기본 8000 |

`.env.example`은 운영 전환 전 실수로 외부 작업을 시작하지 않도록 `RUNTIME_CUTOVER_ENABLED=false`, `AGENT_ENABLED=false`다. 첫 값이 false이면 `python -m app.runtime`도 API만 실행하며 Discord에 연결하거나 X를 수집하지 않는다. 외부 연동 설정이 존재하는 것과 그 기능이 현재 실행 경로에 연결되어 있는 것은 별개다.

## API 호환성과 접근 제어

표준 namespace는 `/api`이며 새 프론트도 이를 사용한다. `/api/v2`는 배포 소비자 확인 기간의 숨은 조회 alias로만 남아 있고 OpenAPI에는 노출하지 않는다. prefix 없는 구 경로와 Google·Spotify·YouTube·곡/아티스트 관리 router는 정상 app에서 마운트하지 않아 기존 DB 쓰기와 외부 호출을 차단한다. legacy 모듈의 물리적 격리·삭제와 v2 alias 제거는 6단계다.

v2 GET은 새 DB에 저장된 정보만 조회한다. Spotify 등 외부 서비스 호출은 하지 않는다. 일부 기존 GET에는 번역·보완 쓰기가 남아 있다. 기존 서비스 사용 여부를 확인하기 전 일괄 삭제하거나 동작을 바꾸지 않는다.

현재 선택적 API 키는 완성된 사용자/관리자 권한 체계가 아니다. 새 프론트 개발 프록시는 서버 전용 키를 넣으며 GET/HEAD만 전달한다. 공개 배포에는 별도 API 라우팅과 읽기·쓰기 권한 검토가 필요하다. 토큰·DB URL은 로그나 프론트 번들에 넣지 않는다.

구매·결제·응모 제출·CAPTCHA 우회는 구현 범위 밖이다. 공식 소스의 이용 조건과 rate limit을 지키며 테스트의 외부 전송은 mock 처리한다.
