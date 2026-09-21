# 백엔드 구조와 운영

기준: 2026-09-20, 저장소 코드. 실제 계정 연결·프로세스 가동 여부는 실행 환경에 따라 다르다. 설치는 [루트 README](../README.md), 새 조회 계약은 [API v2](read-api-v2.md), 미완료 사항은 [후속 작업](backend-roadmap.md)을 따른다.

> 2026-09-21 확정한 변경 방향은 [백엔드 통합 최종 계획](backend-consolidation-plan.md)에 있다. 아래는 아직 변경하지 않은 실행 코드 설명이다. 목표는 신규 DB 단일 운영이며 기존 DB는 변경하지 않고 수집·알림 필수 항목만 선별 이전한다. X는 external_accounts 기반 원문 저장·Discord URL 알림만 남기고 명령·분류·YouTube 자동 등록을 제거한다. Google Calendar는 데이터 보존 후 legacy로 격리하며 admin-web 개편은 후속 작업이다.

## 구성과 데이터 경로

```text
새 프론트 → /api/v2 → CatalogRead → CatalogReadRepository → 새 Neon 카탈로그 (읽기 전용)
기존 웹·관리 API → router → service → repository → PostgreSQL / 외부 연동
runtime → API + Discord bot + 선택적 scheduler
```

| 위치 | 책임 |
| --- | --- |
| `app/api/main.py`, `app/api/routers/` | 앱 수명주기, 라우터 등록, HTTP 상태·입출력 |
| `app/schemas/` | Pydantic 요청·응답 모델 |
| `app/services/` | 조회·업무 처리. v2는 `catalog_read.py`, 이전 `read_catalog.py`는 레거시 구현 |
| `app/repositories/` | 기존 도메인의 DB 조회·저장과 새 v2의 catalog_read.py 조회 SQL |
| `app/db/catalog_session.py` | 새 카탈로그 전용 공유 풀·요청별 READ ONLY Session |
| `app/db/session.py` | URL별 공유 SQLAlchemy Engine/연결 풀, 요청별 Session |
| `app/core/db.py` | 기존 psycopg 연결, 증분 스키마·시드 초기화 |
| `app/integrations/` | YouTube, Spotify, X, OpenAI, Google 등 |
| `app/agents/scheduler.py` | 주기 수집과 소스별 실패 격리 |
| `app/bots/discord_bot.py` | Discord slash 명령과 전송 |
| `app/core/config.py` | 환경변수·루트 `.env` 설정 |

모든 경로가 ORM이나 하나의 연결 풀로 통일된 상태는 아니다. 레거시 psycopg 직접 연결도 남아 있다. 스키마 초기화를 `Base.metadata.create_all`로 대체하지 않는다. 현재 증분 변경과 시드 동작을 먼저 마이그레이션으로 옮겨야 한다.

아티스트·소스·원문·공연 후보·알림 route/전송 이력·Google 연결/동기화·YouTube 아카이브/가창 기록·곡/가사·Spotify 연동 데이터를 PostgreSQL에 저장한다. 엔티티 매핑은 `app/db/models/`, 실제 초기화 SQL은 `app/core/db.py`를 함께 확인한다. 이 문단은 기존 서비스 구조다. 새 사용자 조회는 migrations/catalog의 정규화된 별도 스키마를 사용하며 [조회 API v2](read-api-v2.md)에 연결 기준을 정리했다.

## 현재 수집 흐름

현재 scheduler의 X 처리는 다음과 같다.

```text
활성 X 소스 조회 → 신규 게시글 수집 → source_items 중복 제거
→ notice로 기록 → 포함된 YouTube 라이브 링크 등록
→ 해당 source의 Discord route로 새 글 알림 → 마지막 조회 ID 갱신
```

주기 실행에서는 J-POP Playlist 인덱스 갱신·매칭, 기존 YouTube 라이브 갱신, 채널 모니터 수집도 수행한다. X 설정/소스가 없어도 YouTube 관련 처리는 진행할 수 있다.

`music_graph.py`에는 분류 → live_event/ticket 추출 workflow와 LangGraph 미설치 시 순차 fallback이 구현되어 있다. **현재 scheduler는 이 함수를 호출하지 않는다.** 따라서 X 글이 자동 분류되어 공연 후보·Google 일정으로 이어진다고 안내하지 않는다. Google OAuth·일정 생성 helper와 관련 테이블은 존재하지만, 현재 X loop의 자동 Calendar 생성 경로는 연결되어 있지 않다.

기존 분류·일정 처리 재연결 계획은 2026-09-21 폐기했다. 현재 코드의 여섯 타입과 관련 helper는 구현 정리 대상이며 향후 X 계약이 아니다. 제거 범위와 독립 음악 수집의 보존 기준은 최종 통합 계획을 따른다.

## Discord 사용

현재 `route_add`는 특정 X 소스의 모든 새 글을 채널로 연결한다. 과거 README의 `item_type` 인수나 source 생략 기본 route 예시는 현재 slash 명령과 맞지 않는다.

```text
/artist_add name:RKMusic x_username:RKMusic_inc
/artist_list
/source_list
/route_add source_id:3 channel:#공지
/route_list
/route_list source_id:3
/route_delete route_id:5
/route_test route_id:5
/source_disable source_id:3
/source_enable source_id:3
/google_connect
```

source/route ID는 실제 목록 결과를 사용한다. route 관리는 서버의 `manage_guild` 권한을 확인한다. route가 없거나 봇이 준비되지 않았으면 전송을 건너뛴다. `route_test`, `source_test`, `route_replay`는 실제 메시지를 보낼 수 있는 운영 명령이다. `route_replay`는 저장된 미전송 게시글을 대상으로 전송 이력을 기록한다.

Google 연결은 Discord 사용자별 OAuth다. 서버 공용 연결이나 웹 사용자 로그인과 동일하지 않다. 연결했다고 현재 X 수집 loop의 자동 일정 생성이 활성화되는 것은 아니다. 전체 slash 명령과 매개변수는 `app/bots/discord_bot.py`가 기준이다.

## 설정과 실행 경계

| 설정 | 용도 / 코드 기본값 |
| --- | --- |
| `DATABASE_URL` | 기존 API·수집기·봇용 PostgreSQL |
| `NEW_CATALOG_DATABASE_URL` | 사용자 v2·관리자용 새 카탈로그. 루트 .env.catalog 또는 환경변수 |
| `DATABASE_AUTO_INIT` | 시작 시 초기화, 기본 false |
| `API_KEY` | 일부 기존 라우터와 v2의 선택적 X-API-Key 인증 |
| `AGENT_ENABLED` / `AGENT_RUN_ON_START` | runtime 수집 / 시작 직후 실행, 코드 기본 false / false |
| `AGENT_INTERVAL_SECONDS` | 코드 기본 86400초. 수집량과 제공자 제한을 보고 운영 환경에서 조정 |
| `DISCORD_BOT_TOKEN`, `DISCORD_GUILD_ID` | 봇 인증과 명령 등록 범위 |
| `X_PROVIDER` | auto / twscrape / x_api; 필요한 인증은 선택한 provider에 설정 |
| `YOUTUBE_API_KEY` | YouTube 수집 |
| `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET` | Spotify 조회·매칭 |
| `OPENAI_API_KEY`, `OPENAI_MODEL` | 명시적으로 호출되는 추출·번역 등 |
| `PUBLIC_BASE_URL`, `GOOGLE_CLIENT_*`, `GOOGLE_REDIRECT_URI` | OAuth 공개 주소와 Google 연결 |
| `PORT` | runtime API 포트, 기본 8000 |

`.env.example`은 AGENT_ENABLED=true를 제안하므로 복사 후 실제 활성화 여부를 확인한다. API만 실행하는 uvicorn 명령은 agent loop를 시작하지 않는다. 외부 연동 설정이 존재하는 것과 그 기능이 현재 실행 경로에 연결되어 있는 것은 별개다.

## API 호환성과 접근 제어

표준 namespace는 `/api`, 새 프론트는 `/api/v2`다. 기존 접두사 없는 경로도 호환용으로 남아 있다. `app/api/main.py`는 수명주기·CORS·라우터 등록만 담당하고, Google/Spotify endpoint도 각 라우터에 정의한다. 2026-09-20 미마운트 중복 handler를 제거했으며 HTTP 경로와 OpenAPI 계약은 유지했다. Spotify 라우터의 기존 직접 DB 처리는 남아 있으며 service/repository로의 추가 분리는 별도 작업이다.

v2 GET은 새 DB에 저장된 정보만 조회한다. Spotify 등 외부 서비스 호출은 하지 않는다. 일부 기존 GET에는 번역·보완 쓰기가 남아 있다. 기존 서비스 사용 여부를 확인하기 전 일괄 삭제하거나 동작을 바꾸지 않는다.

현재 선택적 API 키는 완성된 사용자/관리자 권한 체계가 아니다. 새 프론트 개발 프록시는 서버 전용 키를 넣으며 GET/HEAD만 전달한다. 공개 배포에는 별도 API 라우팅과 읽기·쓰기 권한 검토가 필요하다. 토큰·DB URL은 로그나 프론트 번들에 넣지 않는다.

구매·결제·응모 제출·CAPTCHA 우회는 구현 범위 밖이다. 공식 소스의 이용 조건과 rate limit을 지키며 테스트의 외부 전송은 mock 처리한다.
