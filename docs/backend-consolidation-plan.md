# 백엔드 통합 최종 계획 — Operational DB + Catalog DB

작성·확정 방향 반영: 2026-09-21. **구현 전 계획서**다. 이 문서 작성으로 실행 코드, DB, Discord 등록 명령 또는 운영 설정을 변경하지 않았다. 현재 실행 구조는 [백엔드 구조](backend-architecture.md), 기존 조회 계약은 [조회 API v2](read-api-v2.md)를 따른다.

이 문서는 두 DB의 장기 역할, API 통합, 환경설정 정리, Discord 기능 축소에 대한 최종 구현 기준이다. 기존 [DB 이전 계획](db-renewal-plan.md)의 카탈로그 모델은 계승하되, 별도 환경설정·구 ID 대응 제외·운영 기능 이전 방향은 아래 계획으로 대체한다. X 분류·일정 추출을 향후 다시 연결한다는 기존 계획은 폐기한다.

## 1. 확정 목표와 범위

1. 기존 PostgreSQL을 **Operational DB**, 새 PostgreSQL을 **Catalog DB**로 장기 사용한다. 새 음악 정보의 기준은 Catalog 한 곳이다.
2. 사용자·관리 API는 최종적으로 `/api` 아래의 리소스 계약으로 통합한다. `/api/v2`는 전환 후 제거한다.
3. 백엔드 설정은 루트 `.env`와 공통 설정 로더로 통일하고 `.env.catalog`의 별도 로딩을 없앤다.
4. Discord 봇은 **X 새 게시글의 원문 링크 전송만** 담당한다. 게시글 수집·저장은 X worker가 담당한다. 둘을 합친 기능 범위는 “X 게시글 저장 + Discord 링크 알림”이다.
5. Discord의 관리·조회·검색·가사·Google 연결·수동 수집·테스트·재전송 명령과 interaction 기능을 모두 제거한다. 새 봇 명령을 대체 구현하지 않는다.
6. X 게시글 타입 분류를 전부 제거한다. 규칙 분류, LLM 분류, `notice` 고정값 기록, 타입별 필터·메시지·통계도 제거 대상이다.
7. **X 게시글 안의 YouTube 링크를 찾아 live archive 수집 대상으로 자동 등록하는 로직을 제거한다.** X 글 처리에서 YouTube 수집을 시작하지 않는다.
8. 독립적인 YouTube 채널 모니터·명시적 등록·백필, Spotify·가사 등 카탈로그 기능은 유지하고 새 모델과 호환되게 전환한다. 봇 명령 삭제를 해당 백엔드 기능 전체 삭제로 확대하지 않는다.
9. 원문, 외부 ID, 기존 소유권, cursor, 전송 이력, 이미 승인·반영한 카탈로그 자료를 보존한다.

이번 작업은 신규 공연 자동화, 자동 Calendar 생성, 가사 자동 승인, 사용자 즐겨찾기 동기화, 새 음악 화면을 추가하는 사업이 아니다. 기존 Google 토큰·동기화 기록은 Operational에 보존하고 봇/X 의존성을 제거한다. 독립 Google API는 소비자 조사 후 유지 또는 레거시 격리하며 무조건 폐기하지 않는다.

## 2. 봇 축소에 따라 단순화하는 부분

| 이전 계획의 부담 | 최종 선택 |
| --- | --- |
| 봇의 아티스트·곡·가사 명령을 새 모델로 재작성 | 명령 전체 제거. 카탈로그 조회·편집은 웹/API에 집중 |
| X 알림에도 구 아티스트→Catalog ID 대응 필요 | X는 Operational 소스 ID와 X 고정 계정 ID로 독립 동작. Catalog 연결은 선택적 표시 관계 |
| 모든 X 글을 분류·추출·검수·카탈로그 반영 흐름에 연결 | X는 저장·전송으로 종료. 카탈로그 반영은 독립 음악 수집 경로에만 필요 |
| X→YouTube→공연→Calendar의 연결 관리 | X에서 다른 수집·생성 흐름을 시작하는 연결 제거 |
| X에 두 DB 간 반영 영수증·트랜잭션 조정 필요 | X 저장·cursor·전송 대기 기록은 Operational의 로컬 트랜잭션만 사용 |
| 범용 워크플로 엔진·큐·새 메시지 브로커 선도입 | X는 일반 함수와 DB 전송 대기 기록으로 구성. LangGraph는 이 경로에서 제거 |
| 로컬 검수 SQLite를 반드시 Operational로 이전 | 기존 로컬 검수 도구 유지. 중앙 검수·다중 관리자 요구가 생길 때 별도 판단 |
| API·봇·worker를 즉시 여러 배포 서비스로 분리 | 코드 책임부터 분리. 초기에는 기존 통합 runtime도 유지 가능 |
| 모든 구형 봇 기능을 관리 웹에 일대일 복제 | 소스·route·전송 상태 등 운영에 필요한 최소 기능만 우선 이전 |

두 DB의 분리는 유지하지만 X 알림 서비스는 Catalog 장애와 무관하게 동작할 수 있다. 반대로 Catalog 조회도 Operational 장애에 불필요하게 종속시키지 않는다. 두 DB를 함께 사용하는 기능만 해당 연결을 요구한다.

## 3. 데이터 책임

| 데이터 | 최종 책임 | 이전·보존 원칙 |
| --- | --- | --- |
| Discord 사용자 식별·소유권, Guild/channel 설정 | Operational | 기존 권한·소유권 보존. 봇 축소만을 이유로 사용자 플랫폼을 새로 만들지 않음 |
| X source, provider 고정 계정 ID, 활성 상태, polling cursor | Operational | 구 `artists` JOIN 없이 수집 가능하도록 소유자·표시 정보 분리 |
| `source_items` 원문·게시글 ID·URL·게시/수집 시각 | Operational | 분류 없이 저장. 원문과 provider 데이터의 필요한 맥락 보존 |
| notification route, 전송 대기·delivery·재시도 | Operational | source·guild·channel 기준. item type에 의존하지 않음 |
| YouTube 감시·수집 작업·재시도·worker 상태 | Operational | 영상 콘텐츠와 실행 상태 분리 |
| Google OAuth token·기존 Calendar 동기화 이력 | Operational | X/봇에서 분리하고 기존 소비자 종료 전 보존 |
| 외부 수집 후보·임시 매칭·캐시 | Operational | 승인된 음악 마스터의 대체 저장소로 사용하지 않음 |
| 아티스트·별칭·소속사·그룹·공식 계정 | Catalog | 공용 음악 정보의 단일 기준 |
| 곡·녹음·앨범·가사·노래방 번호·커버 | Catalog | 곡 작품과 실제 녹음 버전 구분 |
| 영상·라이브·가창·공연·티켓 안내 | Catalog | 현재 자료·출처·검수 상태 보존 |
| `source_documents`, `catalog_imports`, `catalog_changes` | Catalog | 콘텐츠 변경과 같은 트랜잭션에서 근거·영수증·감사 이력 기록 |
| 로컬 가져오기 초안·승인 장부 | 기존 관리자 SQLite | 로컬 검수 도구의 명시적 저장소. 원격 서비스 운영 상태와 구분 |

### 3.1 공식 계정과 수집 설정

Catalog의 `external_accounts`는 공식 계정의 정체성과 아티스트 관계를 소유한다. 수집 활성 여부·주기·cursor는 Operational이 소유한다. 현재 `external_accounts.collection_enabled`는 소비자를 조사하고 Operational 설정으로 이전한 뒤 제거한다. 기존 false 값을 무시해 수집을 자동 활성화하지 않는다.

X source는 Catalog에 없는 계정도 등록·저장·알림할 수 있다. Catalog와의 선택적 연결 실패가 X 수집을 막지 않는다. 반면 YouTube의 영상 출처 계정·진행자 등 카탈로그 반영에 필요한 관계는 검증된 고정 ID로 연결한다.

### 3.2 ID와 레거시 데이터

- 구 DB와 Catalog의 같은 숫자 ID를 같은 엔티티로 해석하지 않는다. 필요한 참조에는 Catalog 인스턴스 식별값과 엔티티 ID를 함께 기록한다.
- 이전 ID 대응은 필요한 기능에 한해 근거와 함께 보존한다. X 작동을 위해 전체 아티스트 매핑부터 완료할 필요는 없다.
- 별도 DB 사이에 일반 FK나 단일 트랜잭션이 있다고 가정하지 않는다. 실제 참조를 사용하는 서비스가 존재·보관 상태를 검사한다.
- 기존 source·route·delivery ID와 원문 중복 키를 우선 유지한다. 사용자별 동일 X 계정을 이름만 보고 합치거나 전송 이력을 버리지 않는다.
- 구 음악 테이블은 전환 완료까지 보존한다. 최종적으로 쓰기를 중단하고 레거시로 격리한다. Operational의 정상 운영 표는 폐기 대상이 아니다.
- [2026-09-21 이관 기록](setlist-migration-report.md)에 이미 카탈로그 데이터 반영이 기록되어 있다. 빈 DB 초기화·전체 덤프 재주입을 전환 방법으로 사용하지 않는다. 과거 기록의 건수는 이번에 실DB로 재검증한 수치가 아니다.

## 4. X 저장·Discord 링크 알림의 최종 계약

```text
X provider polling
  → 신규 게시글 확인
  → Operational 트랜잭션: 원문 중복 차단·저장 + route별 전송 대기 기록 + 안전한 cursor 갱신
  → Discord sender가 대기 건 처리
  → X 원문 URL 전송
  → 전송 결과·message ID 기록 / 제한된 재시도
```

### 입력과 저장

- “게시글 업로드 시”는 현재 provider의 polling으로 새 글을 발견하면 처리한다는 뜻이다. 실시간 webhook 지원이나 즉시 전송을 새로 보장하지 않는다. 조회 주기는 제공자 제한과 게시량을 보고 정하며 이번 문서에서 운영 주기를 변경하지 않는다.
- 게시글 ID·계정 ID는 문자열로 보존한다. 원문, 원문 URL, 게시 시각, 수집 시각을 저장한다. 타입·confidence·reason은 새 처리 계약에서 제외한다.
- 게시글의 주제에 따라 제외하지 않는다. 답글·재게시 등의 조회 범위는 기존 provider 계약을 먼저 기록하고 유지한다. 이를 분류 제거에 묶어 조용히 변경하지 않는다.
- 기존 cursor는 승계한다. 신규 소스의 첫 조회는 과거 글 일괄 알림을 기본으로 하지 않는다. 권장 기본값은 초기 조회 범위를 저장·기준선으로 설정하고 이후 발견한 새 글부터 알림하는 것이다. 과거 수집은 명시적 별도 작업으로 구분한다.
- pagination을 완료하지 못했을 때 미저장 구간을 건너뛰도록 cursor를 올리지 않는다. 저장과 후속 전송 예약이 내구성 있게 기록된 범위까지만 처리 완료로 본다.

### 전송과 재시도

- 애플리케이션이 보내는 메시지 본문은 **X 원문 URL 하나**다. 요약·분류 라벨·본문 복사·YouTube 링크 메시지를 만들지 않는다. Discord 자체 링크 미리보기는 애플리케이션의 분류·추출 기능과 구분한다.
- route가 없어도 원문은 저장하고 알림만 생략한다. 뒤늦게 route를 만들었다고 과거 게시글 전체를 자동 전송하지 않는다.
- 전송 대기는 별도 범용 큐를 도입하기보다 기존 `notification_deliveries`를 확장하는 방안을 우선 검토한다. `(route_id, source_item_id)` 고유성, 상태, 시도 횟수, 다음 시도 시각, lease, 결과 message ID를 둔다. 기존 성공 기록은 sent로 승계한다.
- 원문 저장 성공 후 봇이 오프라인이 되어도 대기 건이 남아 재개할 수 있어야 한다. 중복 게시글 재수집을 건너뛰는 것과 미전송 건 재시도는 별개로 처리한다.
- 여러 sender가 같은 건을 동시에 전송하지 않도록 DB에서 작업을 선점한다. route 삭제·비활성·권한 변경은 전송 시 다시 확인하고 이력은 보존한다.
- timeout·429·일시 장애는 제한적으로 재시도하고 영구 권한 오류는 자동 폭주시키지 않는다. 전송 성공 후 DB 기록 실패처럼 결과가 불확실한 경우는 별도 상태로 격리하고 가능한 범위에서 확인한다. 외부 전송의 exactly-once를 보장한다고 표현하지 않는다.
- 최소 집계는 조회 글 수, 신규 저장, 중복, 예약, 전송 성공, 생략, 재시도, 실패/결과 불명이다. 분류·추출·Calendar 건수는 X 실행 결과에서 제거한다.

### 제거할 부작용

X 경로는 Catalog 쓰기, YouTube URL 추출·live archive 등록, 링크 페이지 본문 수집, 규칙/LLM 분류, 공연 추출, Google Calendar 생성, 가사 생성·번역을 호출하지 않는다. X 글에 YouTube 링크가 여러 개 있어도 저장할 원문의 일부일 뿐이다.

## 5. 관리 기능과 API 통합

### 관리 위치

X 계정·소스 활성 상태, route와 대상 채널, 전송·worker 상태는 기존 `admin-web`과 관리 API에 모은다. 정상 알림을 운영하는 데 필요한 최소 관리 화면을 준비한 뒤 봇 명령을 제거한다. 기존 설정을 먼저 승계하며 새 설정 체계를 만들기 위해 소스·route를 재등록하지 않는다.

로컬 관리자의 loopback·세션·CSRF 보호를 유지한다. 서버 공용 설정 변경은 인증된 주체의 해당 guild 접근과 `manage_guild`, 대상 channel의 guild 소속을 검증한다. 필요한 인증 경계를 갖추기 전에 기존 로컬 관리 앱을 공개 API에 그대로 마운트하지 않는다. 사용자 조회 API와 관리 API의 권한을 분리한다.

### 최종 HTTP 계약

| 리소스 | 경로 예시 | 책임 |
| --- | --- | --- |
| 아티스트·라이브·앨범·공연·검색 | `/api/artists`, `/api/lives`, `/api/albums`, `/api/concerts`, `/api/search` | Catalog 조회 |
| 작품·녹음별 가사 | `/api/songs`, `/api/recordings/{id}/lyrics` | Catalog 작품/녹음 기준. 곡 상세 화면 확장과는 별도 |
| 수집 소스 | `/api/admin/collection-sources` | Operational 설정 |
| 서버 알림 route | `/api/admin/guilds/{guild_id}/notification-routes` | 길드별 접근 제어 |
| 전송·수집 상태 | `/api/admin/notification-deliveries`, `/api/admin/jobs` | 저장된 운영 상태 조회 |
| 카탈로그 검수·반영 | 기존 `/api/admin/...` 계약 정리 | 검수와 명시적 Catalog 쓰기 |
| 독립 계정 연동 | `/api/auth/...` | 실제 유지하는 소비자에 한해 보존 |

API 통합은 리소스·스키마·서비스의 통합이다. 공개 조회와 로컬 관리자의 배포 프로세스까지 강제로 합치지 않는다. 모든 GET은 저장 자료만 조회하고 수집·생성은 명시적 작업 요청으로 분리한다. 요청·응답은 Pydantic으로 정의하고 페이지·필터·정렬·ID 의미를 문서화한다.

현재 `/api/artists`와 `/api/v2/artists`의 응답 및 ID 체계는 다르므로 단순 prefix 삭제는 금지한다. 기존 소비자를 먼저 임시 `/api/legacy` 또는 별도 호환 앱으로 옮기고 전환을 확인한 뒤 `/api`를 Catalog 계약으로 교체한다. `/api/v2`는 필요한 기간 동안 같은 신규 서비스의 별칭으로만 유지한다. 소비자가 남아 있으면 해당 충돌 경로 전환을 보류하고 나머지 작업을 진행한다.

## 6. 코드·설정 정리

### 설정과 DB 연결

```dotenv
OPERATIONAL_DATABASE_URL=...
CATALOG_DATABASE_URL=...
```

루트 `.env` 한 곳에 백엔드 설정을 두고 공통 Settings에서 읽는다. 환경변수가 파일보다 우선하며, 경로는 작업 디렉터리와 무관하게 해석한다. 구 키 `DATABASE_URL`, `NEW_CATALOG_DATABASE_URL`과 `.env.catalog`는 짧은 전환 기간에만 지원한다. 구·신 설정이 충돌하면 값은 노출하지 않고 오류로 처리한다.

DB뿐 아니라 `.env.catalog`를 읽는 이미지 저장소 설정, 관리자, migration/import 스크립트도 함께 전환한다. URL 치환만으로 대상 DB를 바꾸지 않는다. DB별 공유 SQLAlchemy pool·요청/작업별 session과 명시적 읽기·쓰기 경계를 사용하고, 대상 DB의 역할·인스턴스·revision을 확인한다. 자동 초기화는 끄고 별도 migration으로 관리한다.

프론트의 공개 환경설정과 백엔드 비밀정보는 구분한다. 프론트 전용 예시 파일이나 로컬 검수 작업 파일까지 개수만 줄이기 위해 합치지 않는다. 배포에서는 같은 설정 키를 프로세스별 필요한 범위에 주입한다.

### 역할 충돌 해소

| 현재 위치 | 최종 처리 |
| --- | --- |
| `api/routers/artists.py`, `services/artist_service.py`, `repositories/artists.py` | 공용 프로필은 Catalog로 통합. 사용자 소유권·수집 설정은 Operational로 분리 |
| `api/routers/songs.py`, `services/song_service.py`, `repositories/songs.py` | 작품·녹음·가사·생성 작업으로 책임 분리. 구 song ID를 새 recording ID로 간주하지 않음 |
| `services/catalog_read.py`, `repositories/catalog_read.py` | 신규 Catalog 조회 구현을 계승 |
| `services/read_catalog.py`, `read_spotify.py` | 실제 참조 확인 후 레거시 격리 또는 제거 |
| `bots/discord_bot.py` | 사용자 명령·직접 음악 SQL·생성 helper 제거. Discord 연결과 전송 adapter만 유지 |
| `agents/scheduler.py` | X polling과 독립 음악 수집 스케줄을 분리. X에서 YouTube 등록·분류·일정 helper 호출 제거 |
| `agents/music_graph.py` | X 분류/추출 workflow 제거 |
| `integrations/ai_extractor.py` | X 분류 schema·규칙·prompt·함수 제거. 나머지 함수는 실제 소비자를 조사해 미사용이면 제거 |
| `repositories/notification_routes.py` 및 호환 import | `item_type`·분류 기록 책임 제거. 소스/길드 권한·전송 상태 책임만 유지 |
| `core/db.py` | 연결·증분 migration·시드·레거시 데이터 보정 분리. 시작 시 DDL·시드 재실행 제거 |
| `integrations/youtube_*`, Spotify·가사 파이프라인 | provider 통신과 저장을 분리하고 Catalog/Operational repository를 명시적으로 사용 |

`langgraph`는 다른 실행 소비자가 없음을 확인하고 의존성에서 제거한다. X 분류 제거를 이유로 카탈로그 수집에서 사용 중인 OpenAI·번역·가사 의존성까지 일괄 제거하지 않는다. X 분류 컬럼·enum·타입별 route 제약은 읽기/쓰기 소비자 제거 후 migration으로 정리하고 과거 감사 자료는 보존한다.

폴더는 기존 계층을 유지하면서 `services/catalog`, `services/operational`, `repositories/catalog`, `repositories/operational`, `workers`, `legacy` 정도로 정리한다. 파일 이동과 동작 변경을 가능한 별도 변경 단위로 나누고 신규 코드가 `legacy`를 import하지 않도록 검사한다. `web.bak`은 필요한 관리 기능 이전 후 `legacy/web`로 격리한다.

## 7. 구현 순서와 단계별 완료 조건

### 단계 1 — 기준선·소비자·제거 대상 확정

- 테이블/필드의 소유 DB, API/스크립트/봇의 읽기·쓰기 소비자, 설정 로더를 목록화한다.
- 현재 migration revision과 이미 적용된 데이터 이관 영수증을 확인한다. 실DB 점검은 코드/fixture 조사와 구분한다.
- X→YouTube 연결, 분류 helper, 봇 명령의 제거 목록과 독립 수집 기능의 보존 목록을 고정한다.
- 기존 global/guild Discord 명령의 등록 범위와 앱 소유권을 확인할 배포 절차를 준비한다.

완료 조건: 무엇을 제거·유지·이전하는지와 기존 소비자의 전환 경로가 명확하다. 이 단계에서 DB 재수집·삭제·전송을 실행하지 않는다.

### 단계 2 — 공통 설정·DB migration 기반

- 공통 설정 로더와 두 DB 연결 경계를 도입하고 기존 설정 별칭을 임시 지원한다.
- 기존 Operational 스키마의 기준선을 기록하고 `migrations/operational`, `migrations/catalog`를 독립 관리한다. 이미 적용된 Catalog migration 파일을 수정하지 않는다.
- 구 `init_db()`의 DDL·시드·데이터 보정은 동작을 조사해 명시적 명령으로 옮긴다.
- 잘못된 DB·누락 설정을 감지하고 필요한 서비스만 영향을 받도록 한다.

완료 조건: API·관리자·스크립트·runtime이 같은 규칙으로 설정을 읽고, 조회 시작이 DB를 초기화하지 않는다.

### 단계 3 — X 운영 저장·최소 관리 화면

- X source의 소유권·고정 계정 ID·표시명·cursor를 Operational 안에서 자립시킨다. Catalog 참조는 선택적으로 둔다.
- 기존 source/route/delivery를 승계하고 전송 대기·재시도 상태를 추가한다. 기존 성공 delivery는 재전송하지 않는다.
- 소스·route·채널·전송/실행 상태의 최소 관리 화면과 권한 검사를 준비한다. 임의 알림이나 수동 재전송을 UI 진입만으로 시작하지 않는다.
- 기존 분류별 route 중복이 있다면 전송 이력과 권한 범위를 검증한 전환안을 만든다. 일반 시드 실행에서 중복을 삭제하지 않는다.

완료 조건: Discord 명령 없이 운영 설정을 관리할 수 있고 X 처리가 구 음악 마스터·Catalog에 의존하지 않는다.

### 단계 4 — X 경로·Discord 봇 축소

- 저장·전송 예약·cursor 갱신을 안전한 단위로 묶고 sender가 재시도 가능한 전송 대기 건을 처리하게 한다.
- X 분류, 고정 notice 기록, 타입별 메시지, 링크 페이지 처리, **YouTube live archive 자동 등록**, 공연·Calendar helper 연결을 제거한다.
- 봇의 모든 사용자 명령·interaction을 삭제하고 URL 전송만 남긴다. 사용하지 않는 helper/import도 정리한다.
- 배포 시 해당 Discord 애플리케이션에 이미 등록된 global/guild 명령도 명시적인 일회성 정리로 해제한다. 로컬 decorator 삭제만으로 원격 명령이 사라졌다고 간주하지 않는다. 매 시작마다 전체 guild 명령을 무차별 삭제하지 않는다.
- 테스트의 이전 분류 기대값과 UI·문서의 봇 명령 안내를 새 계약으로 교체한다.

완료 조건: X 글은 저장되고 URL만 전송된다. X에 YouTube 링크가 있어도 수집 등록·분류·추출·Calendar 호출이 0회이며 봇 명령이 남아 있지 않다.

### 단계 5 — 독립 음악 수집과 Catalog 호환

- 독립 YouTube 모니터/등록/백필부터 전환하고 Spotify·노래방·가사 순으로 진행한다. 진행 상태는 Operational, 콘텐츠는 Catalog로 분리한다.
- 필요한 계정·아티스트·영상·곡/녹음 연결만 외부 고정 ID와 검수 근거로 매핑한다. 미확정 항목은 후보 상태로 남긴다.
- 기존 관리자의 검수·manifest·`catalog_imports` 영수증을 재사용한다. 원격 수집 후보는 고정 후보 ID와 hash로 로컬 검수에 가져오고, 승인 상태의 기준은 검수 장부 한 곳으로 유지한다.
- Catalog 반영 성공 후 Operational 결과 기록이 실패하면 같은 operation ID의 영수증으로 복구한다. X 전송에는 이 두 DB 간 반영 경로를 도입하지 않는다.
- 기존 로컬 SQLite와 원본 파일 보관 구조는 유지하며 불필요한 중앙 검수 플랫폼을 새로 만들지 않는다.

완료 조건: 새 음악 수집 자료가 기존 검수 절차를 거쳐 신규 프론트에서 조회되며 X 알림과 실행·장애 경계가 분리된다.

### 단계 6 — API 계약 통합·소비자 전환

- Catalog/Operational의 Pydantic 계약과 권한을 정리하고 구·신 artist/song ID 충돌을 제거한다.
- 기존 관리 소비자를 호환 경로로 먼저 이동한 뒤 `/api`를 신규 계약으로 전환한다. `web`의 호출·캐시·mock·테스트·프록시 설정도 함께 변경한다.
- 기존 v2 DTO를 가능한 재사용해 경로 변경과 불필요한 응답 재설계를 분리한다. 새 곡 상세 등 미구현 화면은 이번 통합 완료 조건에 포함하지 않는다.
- 관리자의 로컬 보안 경계와 독립 배포 가능성을 유지한다. 문서상 하나의 API 계약이라고 공개 접근을 허용하지 않는다.

완료 조건: 신규 소비자는 `/api`를 사용하고 동일 리소스의 ID·응답 의미가 일관된다. GET은 외부 수집·생성·전송을 시작하지 않는다.

### 단계 7 — 레거시 격리·호환 제거·운영 전환

- 사용 종료를 확인한 구 API·prefix 없는 별칭·`/api/v2`·임시 호환 경로를 제거한다.
- 구 음악 테이블의 신규 쓰기를 중단하고 코드/도구/웹을 레거시로 격리한다. 보관 데이터 삭제는 별도 판단하며 이번 구조 정리에 묶지 않는다.
- `.env.catalog`, 구 설정 키, 개별 설정 파서, 미사용 분류 의존성을 제거한다. 백엔드 `.env.example`과 실행 도구를 갱신한다.
- 대표 소스로 전환을 검증하고 소스별 활성 worker/sender를 하나로 제한한다. 구·신 경로를 비교할 때 새 경로의 외부 전송은 끈다.
- README·현재 구조·API 계약·roadmap·영역별 AGENTS를 실제 구현 상태로 갱신한다.

완료 조건: 레거시 코드를 실행하지 않아도 조회·관리·독립 음악 수집·X 링크 알림이 동작한다. Operational과 Catalog는 각각 장기 운영 가능한 역할을 갖는다.

## 8. 검증·전환·복구 기준

| 범위 | 반드시 확인할 항목 |
| --- | --- |
| X 원문·cursor | 중복 수집, 여러 페이지, 저장 실패, 재시작, 초기 수집, 미저장 구간 건너뛰기 방지 |
| 전송 | route 없음, 비활성, 봇 오프라인, 중복 worker, 재시도, channel 누락/권한 오류, 성공 후 기록 실패 |
| 기능 제거 | 메시지는 URL 하나, X 분류/LLM 호출 없음, YouTube 링크 등록 없음, 이벤트/Calendar 쓰기 없음 |
| 격리 | Catalog 연결 없이 X 동작, Operational 연결 없이 Catalog 조회 가능, X 제거가 독립 YouTube 수집을 막지 않음 |
| 권한 | 다른 guild/source/route 접근 거부, manage_guild, channel 소속 검증, 서버 비밀정보 미노출 |
| 카탈로그 | 기존 반영 데이터·원문 보존, 작품/녹음 ID 분리, 승인·영수증 재시도·참조 무결성 |
| 계약 | 경로 충돌 없음, OpenAPI/DTO/페이지 기준, 구 소비자 전환 확인, GET 부작용 없음 |
| 설정·레거시 | 설정 충돌/누락, 잘못된 DB 대상, 신규 코드의 legacy import, 자동 초기화·시드 미실행 |

테스트는 로컬 fixture/임시 DB와 mock provider를 사용한다. 실제 Discord·Calendar·LLM은 호출하지 않는다. 실DB 읽기 검증·소수 소스 운영 전환·Discord 원격 명령 해제는 배포 작업으로 구분하고 날짜·대상·결과를 기록한다. 테스트 통과를 실계정 전송 확인으로 표기하지 않는다.

스키마는 추가 → 이관 → 검증 → 소비자 전환 → 정리 순서로 적용한다. 되돌리기는 신규 worker/sender를 멈추고 cursor·대기·완료 기록을 대조한 뒤 호환 가능한 처리 경로를 재개한다. 완료 delivery나 Catalog 영수증을 삭제해 재실행하지 않는다. 구 버전이 읽지 못하는 대기 상태는 먼저 변환·복구하며 무조건 바이너리만 되돌리지 않는다. 폐기한 X 분류·YouTube 연결·봇 명령은 자동 재활성화하지 않는다.

## 9. 문서화 시점의 검증 범위

2026-09-21: 저장소 코드와 기존 이관 문서를 정적으로 확인해 작성했다. 실제 DB 내용·계정·실행 중인 프로세스·Discord 원격 명령을 이번에 조회하지 않았다. 구현 테스트·실제 수집·전송·DB migration은 실행하지 않았다. 본문의 단계와 검증표는 앞으로 수행할 작업이며 완료 기록이 아니다.

같은 날 변경 문서·작업 지침 8개의 로컬 Markdown 링크 57개가 존재함을 확인했고 `git diff --check`를 통과했다. 이 검증은 문서 연결·공백 오류 범위이며 실행 기능의 검증이 아니다.
