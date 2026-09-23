# 백엔드 통합 최종 계획 — 신규 DB 일원화

확정 기준: 2026-09-22. 1~3단계 기반, X 수집·최소 Discord sender의 1차 구현, 정식 `/api` 통합을 수행했다. **전체 서비스 운영 전환 준비는 미완료다.** [서비스 검증과 보완 개발 계획](backend-service-readiness-plan.md)에 따라 X·Discord 안정화 이후 독립 YouTube와 등록된 Spotify 계정 수집기의 신규 DB 호환을 완성한 뒤 실제 상태 이전과 운영 연결을 전환한다. 단계별 실행 기록은 [1단계](backend-phase-1-baseline.md), [2단계](backend-phase-2-runtime-schema.md), [3단계](backend-phase-3-runtime-migration.md), [4단계](backend-phase-4-runtime.md), 현재 실행 경로는 [백엔드 구조](backend-architecture.md)를 따른다.

## 1. 목표와 범위

1. **신규 PostgreSQL 하나를 API·수집기·Discord 봇의 운영 DB로 사용한다.** 이미 반영된 음악 데이터와 검수 이력은 유지한다.
2. 기존 DB에서는 수집 재개와 Discord 알림에 필요한 행·필드만 선별하여 신규 DB로 이전한다. 나머지 데이터는 기존 DB에 그대로 보존하고 이전하지 않는다.
3. 기존 DB에는 DDL·DML·시드·보정·migration·권한 변경을 수행하지 않는다. 이전 도구는 읽기 전용으로 접근하며 전환 후 정상 runtime은 기존 DB에 연결하지 않는다.
4. X 수집 대상의 기준은 신규 DB의 `external_accounts`다. 별도의 독립 X 계정 명부를 만들지 않는다.
5. X 기능은 **게시글 원문 저장 + Discord에 원문 URL 전송**만 남긴다. 봇 명령·interaction·X 타입 분류·X 글의 YouTube live archive 자동 등록을 제거한다.
6. admin-web은 대규모 개편 예정이므로 이번 개발에서는 없는 것으로 취급한다. 화면·관리 API·연동을 구현하거나 의존하지 않는다. 향후 관리는 admin-web에서 별도로 설계한다.
7. Google Calendar는 데이터를 기존 DB에 그대로 보존하고 코드·설정·API를 레거시로 격리한다. 신규 DB로 Google 데이터를 옮기거나 정상 runtime에서 기능을 실행하지 않는다.
8. API는 최종적으로 `/api` 계약으로 통합한다. 백엔드 설정은 루트 `.env`와 공통 Settings로 정리한다.
9. 독립 YouTube 수집과 신규 external_accounts에 등록된 Spotify 계정의 수집·연결을 신규 모델로 전환한다. Spotify 미등록 계정은 탐색·생성·자동 연결하지 않는다. 노래방은 song_id 구축 후 TODO, 가사·번역·독음도 TODO로 남기고 이번 목표에서 제외한다. 기존 자료 조회는 유지한다.

이번 범위에는 신규 관리 화면, 신규 공연 자동화, Calendar 재구현, 과거 음악 데이터 추가 이관을 포함하지 않는다.

## 2. 신규 DB의 책임

| 영역 | 저장할 내용 | 원칙 |
| --- | --- | --- |
| 음악 정보 | 기존 아티스트·곡·녹음·앨범·가사·영상·라이브·가창·출처·검수 이력 | 신규 DB의 현재 모델과 이미 반영된 데이터를 기준으로 유지 |
| 외부 계정 | `external_accounts`, `artist_external_accounts` | 계정 정체성·수집 활성 여부의 단일 기준 |
| 수집 상태 | 계정별 cursor, 마지막 확인 외부 ID, 다음 실행·재시도·worker 상태 | 외부 계정 FK로 연결. 콘텐츠와 실행 상태 분리 |
| X 원문 | 외부 게시글 ID, 계정, 본문, 원문 URL, 게시·수집 시각 | 분류 필드 없이 중복 차단 |
| Discord 알림 | route, 필요한 guild/channel·소유권, 전송 대기·결과·재시도 | 계정별 설정 및 route별 중복 방지 |
| 독립 음악 수집 작업 | 필요한 감시 설정·미완료 작업·재시도 상태와 영상 참조 | 완료 콘텐츠를 운영 상태 이전 명목으로 복제하지 않음 |
| 이전 감사 | 원본 식별자→신규 ID 대응, 선택 사유, 실행 영수증·검증 결과 | 신규 DB에만 기록. 재실행해도 중복 생성·전송하지 않음 |

같은 DB 안의 참조는 FK와 로컬 트랜잭션으로 보장한다. 계정·음악 도메인과 작업 상태는 코드 책임으로 구분하며 별도 운영 DB를 만들지 않는다.

로컬 관리자 SQLite 검수 장부와 twscrape의 계정 저장소는 해당 도구의 내부 저장소다. 이번 서비스 DB 통합을 이유로 이 도구들까지 재작성하지 않는다.

### 2.1 external_accounts 기반 수집

- 수집 대상은 `platform='x'`, `collection_enabled=true`, `archived_at IS NULL`인 계정이다. 정상 수집은 이 조건을 반드시 확인한다.
- `collection_enabled`를 활성 여부의 단일 기준으로 유지한다. 주기·cursor·재시도·lease는 계정별 수집 상태에 둔다.
- `platform_id`는 provider의 고정 계정 ID로 사용하며 일치하면 우선 연결한다. 고정 ID가 없거나 기존 값이 달라도 같은 플랫폼에서 정규화한 handle이 신규 계정 하나와 유일하게 일치하면 연결한다. 이름·아티스트 표시명만으로 병합하지 않는다.
- handle 연결은 근거를 이전 보고서에 남기고 신규 계정의 `platform_id`를 구 값으로 덮어쓰지 않는다. 같은 handle 후보가 여러 개거나 계정이 보관 상태면 보류한다. 이후 provider가 고정 ID를 확인하면 별도 검증된 변경으로 보완한다.
- 신규 계정이 없으면 미매핑 목록에 남긴다. 자동 생성·자동 활성화하거나 계정 명부 밖에서 수집하지 않는다.
- 연결된 X 계정의 `collection_enabled`는 기존 source의 `is_active`를 승계한다. 여러 source가 한 계정에 연결되면서 활성값이 다르면 자동 적용하지 않는다. 보관 상태는 기존 활성값으로 해제하지 않는다.
- 여러 구 source가 같은 신규 계정에 대응하면 수집은 계정 단위로 합치되 route·소유권·성공 전송 기록은 유지한다. 서로 다른 cursor를 무조건 최댓값으로 합치지 않는다.
- `artist_external_accounts`의 복수 아티스트 관계는 표시·음악 연결에 사용한다. 아티스트 수만큼 같은 계정을 반복 수집하지 않는다.

## 3. 선택 이전 기준

이전 단위는 테이블 전체가 아니라 **선택한 계정·route·작업과 그 참조를 성립시키는 최소 행·필드**다. 최종 허용 목록은 1단계에서 근거와 함께 만든다.

| 기존 데이터 | 이전 범위 |
| --- | --- |
| `artist_sources` | 매핑된 수집 계정의 필요한 cursor·고정 ID 대응·실행 상태. 구 아티스트 프로필은 복제하지 않음 |
| `artists`, `artist_agencies` | 음악 마스터 이전 제외. 선택 route·작업의 권한에 필요한 소유자 식별 정보만 별도 추출 |
| `notification_routes` | 선택 계정에 연결된 guild/channel·활성 상태·필요한 소유권. 타입 조건 제외 |
| `notification_deliveries` | 선택 route의 중복 전송 방지에 필요한 성공 이력·message ID. 성공 건은 sent로 승계 |
| `source_items` | 선택 delivery의 참조 원문 및 확인된 미완료 처리·cursor 경계에 필요한 원문만 이전. 분류·confidence·추출 결과 제외 |
| `youtube_channel_monitors` | 신규 YouTube 계정과 매핑된 감시 설정·수집 재개 상태 |
| `youtube_channel_videos`, `youtube_live_archives` | 수집 재개·중복 작업 방지·확인된 미완료/재시도에 필요한 외부 영상 ID와 상태만 선별. 존재하는 신규 영상은 참조 |
| 구 가창·커버·곡·가사·공연 후보 | 이전 제외. 신규 DB의 이미 반영된 음악 자료 유지 |
| 노래방 매칭·번역 cache | 기본 제외. 특정 수집 작업 재개에 꼭 필요한 항목만 별도 사유를 기록해 검토 |
| Google token·Calendar sync·기타 Google 관련 자료 | 이전 제외. 기존 DB에 변경 없이 보존 |
| 나무위키 템플릿·그 밖의 비필수 항목 | 이전 제외. 기존 DB에 변경 없이 보존 |

선택한 행의 원문·외부 ID·URL·소유권은 보존한다. 과거 X 원문 전체를 이관하지 않더라도 제외된 원문은 원 DB에 남는다. 전체 행 수를 신규 DB에서 맞추는 것을 성공 기준으로 삼지 않는다.

구 숫자 ID를 신규 ID로 그대로 해석하지 않는다. 원본 DB 식별값·테이블·행 ID를 포함하는 대응표와 고유 키를 사용한다. 소유권 충돌, 누락 참조, cursor 충돌은 자동 추정으로 해결하지 않는다.

## 4. X 저장·Discord URL 알림 계약

```text
external_accounts의 수집 가능 X 계정
  → provider polling
  → 신규 DB 트랜잭션: 원문 중복 차단·저장 + route별 전송 대기 + cursor 갱신
  → sender가 대기 건 선점
  → Discord에 X 원문 URL 하나 전송
  → 결과·message ID 기록 또는 제한된 재시도
```

- 게시글 타입을 판단하거나 기록하지 않는다. `notice` 고정 기록도 제거한다.
- 원문에 YouTube 링크가 있어도 저장할 본문의 일부일 뿐이다. URL 추출·페이지 수집·archive 등록·공연 추출·Calendar 생성·번역을 호출하지 않는다.
- provider polling 주기와 원본 글 범위는 별도 변경 요청 없이 유지한다. 현재 답글·재게시 제외 동작을 먼저 확인하고 계약으로 기록한다.
- 기존 cursor는 검증 후 승계한다. 신규 계정의 첫 조회는 과거 글 일괄 알림 없이 기준선을 잡고 이후 새 글부터 알린다.
- pagination을 끝내기 전에 미수집 구간을 건너뛰는 cursor를 저장하지 않는다. 장애 후 이어받을 수 있는 진행 상태를 둔다.
- route가 없어도 원문은 저장한다. 새 route 생성 시 과거 게시글을 자동 전송하지 않는다.
- 전송 대기는 DB에 내구성 있게 남긴다. `(route_id, source_item_id)` 고유성, 상태·시도 횟수·다음 시도·lease·message ID를 관리한다.
- 기존 성공 건을 재전송하지 않는다. 기존 DB의 미전송 원문 전체를 pending으로 바꾸지 않고 실제 재개 대상임을 확인한 작업만 승계한다.
- sender는 route 비활성·소유권·채널 접근을 다시 확인한다. 일시 장애·429는 제한적으로 재시도하고 결과 불명 건은 격리한다. 외부 전송의 exactly-once를 보장한다고 표현하지 않는다.
- 조회·신규 저장·중복·예약·전송·생략·재시도·실패를 기록한다. X 분류·추출 통계는 제거한다.

Discord에서는 관리·조회·검색·가사·Google 연결·수동 수집·테스트·재전송 명령을 모두 제거한다. lifecycle과 URL 전송 adapter만 남긴다. 원격 slash command 정리는 배포 때 해당 애플리케이션의 global/guild 등록 범위를 확인하여 수행한다.

## 5. 관리와 API

향후 관리 위치는 admin-web이지만 이번 개발에서는 앱과 관리 API가 없는 것으로 취급한다. 백엔드 내부 service와 작업 실행 명령으로 수집·저장을 검증한다. 관리 UI·관리 HTTP 계약·권한 기능은 개편에서 별도로 설계한다. 봇 명령은 복구하지 않는다.

초기 계정 대응·route·상태 이전은 검증된 이전 명세로 수행한다. 이는 일회성 이전 절차이며 상시 설정 파일 관리자나 새 봇 관리 명령으로 확장하지 않는다. 관리 화면이 없는 설정의 수동 변경을 정상 운영 절차로 문서화하지 않는다.

| 계약 | 최종 방향 |
| --- | --- |
| `/api/artists`, `/api/lives`, `/api/albums`, 검색·통계 등 | 현재 신규 조회 서비스와 DTO를 기반으로 통합 |
| 곡·녹음·가사 | 신규 작품/녹음 ID 기준으로 책임 분리 |
| 관리자 API/UI | 이번 개발에서 제외. 향후 admin-web 개편에서 설계 |
| `/api/v2` | 필요 기간 같은 신규 서비스의 임시 별칭, 소비자 전환 후 제거 |
| 구 API·prefix 없는 alias | 소비자와 ID 의미를 확인해 전환 또는 종료. 기존 DB 쓰기로 fallback하지 않음 |
| Google auth·Calendar | 정상 API mount에서 제거하고 legacy로 격리 |

`/api/artists` 등 충돌 경로는 prefix만 지우지 않는다. 소비자별 새 ID·응답 계약을 확인하고 신규 DB만 사용하는 한시적 adapter 또는 명시적 종료로 처리한다. GET에서 수집·생성·전송을 시작하지 않는다. Pydantic 계약과 페이지·필터·정렬 기준을 명시한다.

현재 관리자 앱·관리 HTTP API는 통합 개발 범위 밖이다. 향후 관리자에서는 loopback·세션·CSRF 및 Discord guild 접근·manage_guild·channel 소속 등 관리 권한을 별도로 설계한다. 이번 공개 조회 API에 관리 쓰기를 추가하지 않는다.

## 6. 설정·코드·레거시

최종 backend 설정은 루트 `.env`의 `DATABASE_URL` 하나로 신규 DB를 가리킨다. 공통 Settings, 공유 SQLAlchemy pool, 요청/작업별 session을 사용한다. 운영 migration/import·이미지 저장 설정도 같은 로더를 사용한다. 기존 admin 도구는 이번 정상 실행 경로에 포함하지 않는다. 프론트 공개 설정과 로컬 도구의 작업 파일은 용도에 맞게 분리한다.

로컬 코드는 구 SQL과 `init_db()` 연결을 차단하고 대상 identity·revision 검사를 완료했다. `DATABASE_URL`은 신규 DB를 가리키며 이전 전용 읽기 소스는 `LEGACY_DATABASE_URL`로만 받는다. Railway의 변수 전환은 새 코드 배포와 함께 [운영 전환 절차](backend-phase-5-cutover.md)에서 수행한다. 실제 URL·토큰은 문서·보고서·로그에 남기지 않는다.

`.env.catalog` 소비자를 제거했고 `NEW_DATABASE_URL`이 남으면 시작을 거부한다. 기존 DB의 baseline migration이나 revision 표를 만들지 않는다. 신규 DB의 적용된 `001/002`는 변경하지 않았다.

| 현재 위치 | 처리 |
| --- | --- |
| `artists.py`와 artist service/repository | 신규 아티스트 마스터 사용. 수집 상태·권한을 프로필 CRUD에서 분리 |
| `songs.py`와 song service/repository | Spotify에 필요한 신규 녹음·앨범 저장만 전환. 가사·번역·독음·노래방은 TODO로 격리 |
| `catalog_read.py` | 신규 조회 구현 재사용 |
| `read_catalog.py`, `read_spotify.py` | 사용 여부를 확인해 legacy 격리 또는 제거 |
| `bots/discord_bot.py` | command/interaction·음악 SQL·생성 helper 제거. 연결과 URL 전송만 유지 |
| `agents/scheduler.py` | X poller/sender와 독립 음악 worker 실행 단위 분리 |
| `agents/music_graph.py` | X 분류/공연 추출 workflow 제거 |
| `integrations/ai_extractor.py` | X 분류·추출 제거. 독립 YouTube setlist 추출은 보존 |
| `core/db.py` | 구 DDL·시드·보정 경로를 정상 시작 및 이전 도구에서 차단 |
| Google OAuth·Calendar 코드와 설정 | legacy 격리. refresh·sync·callback 등 정상 실행 연결 제거 |
| `web.bak`와 구 관리 router | 기존 DB 쓰기 경로 종료 후 legacy 격리. admin-web 개편은 별도 |

기존 계층을 살려 collection/notification/catalog 책임과 legacy 경계를 구분한다. 신규 코드가 legacy를 import하지 않도록 검사한다. X 분류 제거 후 다른 소비자가 없으면 LangGraph를 제거하되, 독립 setlist 추출의 OpenAI 의존성은 유지한다. 가사·번역·독음은 정상 작업에서 호출하지 않는다. **구 DB의 분류 컬럼이나 테이블은 삭제·수정하지 않는다.**

## 7. 단계별 실행과 완료 조건

### 1단계 — 읽기 전용 조사와 선택 이전 명세

[1단계 문서](backend-phase-1-baseline.md)의 절차로 계정 대응, 최소 행·필드, 중복 방지 이력, cursor·소유권 충돌, 기존 DB 쓰기 소비자를 조사한다. 과거 집계는 참고 자료이며 현재 매핑 결과로 대신하지 않는다.

완료 조건: 선택/제외 사유와 참조가 명확한 이전 명세, 충돌 목록, 소비자 전환 목록이 있다. 필요한 사용자 결정이 해결되거나 해당 항목을 명시적으로 보류한다. DB 쓰기·재수집·전송은 하지 않는다.

### 2단계 — 신규 DB 스키마·공통 설정 기반

신규 DB에 추가할 계정별 상태·X 원문·route·delivery·작업·이전 영수증 schema와 후속 migration을 작성한다. 구 초기화 경로를 차단하고 신규 DB identity/revision guard와 공통 Settings를 준비한다.

완료 조건: 격리된 테스트 DB에서 migration·FK·고유 제약·연결 가드가 검증되고, 시작 시 DDL/시드가 실행되지 않는다. 실제 기존 DB에는 아무 변경도 하지 않는다.

**완료:** 2026-09-21 `002_runtime.sql`을 신규 DB에 적용하고 별도 연결에서 재검증했다. 세부 스키마·테스트·적용 범위는 [2단계 결과](backend-phase-2-runtime-schema.md)에 기록한다.

### 3단계 — 선택 이전 도구와 검증

기존 DB SELECT → 명세 검증 → 신규 DB 반영 도구를 작성한다. 계정 대응→상태/route→필요 원문/이력→미완료 작업 순서를 검증하고 dry-run·재실행·중단 복구를 테스트한다.

완료 조건: 선택 집합 일치, 제외 항목 유입 0, 참조 오류 0, 성공 알림의 pending 변환 0, 재실행 중복 0. 실제 이전 실행은 검증된 명세와 전환 시점에 맞춰 5단계에서 수행한다.

**완료:** 2026-09-21 읽기 전용 실데이터 dry-run과 로컬 PostgreSQL 적용·재실행 검증을 완료했다. 결과와 전환 시 재검증 조건은 [3단계 결과](backend-phase-3-runtime-migration.md)에 기록한다. 실제 이전은 수행하지 않았다.

### 4단계 — 수집기·최소 Discord 봇 전환

external_accounts 기반 X 수집과 durable sender를 구현한다. 봇 명령·X 분류·X→YouTube 연결을 제거한다. Discord 명령이 제공하던 YouTube·Spotify·노래방·가사 관리 진입점도 제거하고, 독립 YouTube와 등록된 Spotify 계정 수집을 신규 DB 작업 실행기와 정규화된 저장 모델로 전환한다. admin-web과 관리 API는 제외하고 내부 service·작업 실행 계약만 준비한다. 노래방·가사·번역·독음은 실행하지 않는다.

완료 조건: fixture에서 신규 글·첫 조회 기준선·중복·무 route·offline·재시도·pagination·계정 순환·lease·전송 결과 불명 처리를 검증하고 X가 다른 수집이나 Google을 호출하지 않는다. YouTube·등록된 Spotify 계정은 계정/작업→신규 DB 저장→조회까지 검증한다. admin-web은 검증에 사용하지 않는다.

**부분 구현:** 2026-09-22 external_accounts 기반 X poller와 URL sender, Discord 관리 명령·X 분류·X→YouTube 자동 등록 제거를 구현했다. [4단계 결과](backend-phase-4-runtime.md)는 당시 검증 범위다. 전체 서비스 재검증에서 발견한 X·Discord 계약 위반은 [보완 1단계](backend-service-step-1-runtime.md)에서 수정했다. [보완 2단계](backend-service-step-2-jobs.md)에서 독립 작업 실행기를 완료했다. [보완 3단계](backend-service-step-3-youtube.md)에서 YouTube handler·신규 저장을 로컬 검증했다. [보완 4단계](backend-service-step-4-spotify.md)에서 등록된 Spotify 계정 handler와 신규 DB 저장 경로를 로컬 검증했다. 실제 상태 이전과 운영 검증은 남아 있다. [보완 계획 A~D](backend-service-readiness-plan.md)에 따라 수정·개발하며 실제 상태 이전과 운영 연결 전환은 아직 수행하지 않았다.

### 5단계 — API 통합·실제 이전·runtime 전환

구 쓰기 프로세스를 배포/실행 설정에서 정지한 뒤 최종 읽기 스냅샷과 명세를 재검증한다. 구 DB의 활성 플래그를 변경해 정지하지 않는다. Google callback·refresh·sync와 구 DB를 사용하는 API/script의 실행 연결도 이 시점까지 차단한다. 신규 DB에 선택 이전을 반영·검증하고 API/worker/bot의 연결과 신규 프론트를 전환한다.

완료 조건: 정상 runtime은 신규 DB만 사용하고 구 DB 쓰기 경로는 실행되지 않는다. 기존 성공 알림 재전송과 과거 글 대량 알림 없이 계정별 수집을 재개한다. 연결 변경만으로 구 SQL이 신규 DB에서 실행되지 않는다.

**API 통합·잠금 구현, 운영 전환 보류:** 2026-09-22 정식 조회 경로를 `/api`로 통합하고 legacy 쓰기/provider router를 운영 앱에서 분리했다. `RUNTIME_CUTOVER_ENABLED=false`일 때 새 runtime은 API만 실행한다. [보완 계획 A~F](backend-service-readiness-plan.md)의 구현·통합 검증과 이전 작업 선택 보완이 선행 조건이다. 그 뒤 최종 snapshot, migration apply, Railway runtime 활성화를 [5단계 운영 전환](backend-phase-5-cutover.md) 순서로 수행한다.

### 6단계 — 레거시·환경설정·배포 정리

Google과 구 API/UI를 격리하고 임시 v2/호환 alias·중복 env 로딩을 종료한다. 정상 runtime의 구 DB 접근 차단과 설정 통합은 보완 계획 E에서 실제 운영 전환 전에 완료한다. alias 제거는 소비자 전환 확인 후 수행한다. 해당 bot의 원격 slash command 제거를 검증하고 운영·복구 문서를 갱신한다.

완료 조건: 신규 실행 경로에 legacy import·Google 호출·기존 DB 접속·X 분류·YouTube 자동 등록이 없다. 기존 DB와 제외 데이터는 변경 없이 보존된다.

### 별도 후속 — admin-web 개편

외부 계정·route·작업 관리는 대규모 개편에서 다시 설계한다. 이번 개발에서는 관리자 앱이 없는 것으로 취급한다. 노래방은 song_id 구축 후, 가사·번역·독음도 별도 TODO이며 이번 통합 완료 조건에서 제외한다.

## 8. 전환 검증과 복구

- 이전 시점의 source snapshot과 신규 DB revision·대응 계정 version을 확인한다. 조사 후 변경된 계정·cursor·route는 재검토한다.
- 기존 DB에는 SELECT만 실행한다. 읽기 전용 트랜잭션을 사용하고 권한 변경이나 초기화 함수를 호출하지 않는다.
- fixture와 실제 DB 검증 결과를 구분한다. 실제 Discord·Calendar·LLM 호출을 테스트에 사용하지 않는다.
- 선택된 원문·소유권·참조 보존, 계정 매핑, route별 전송 중복 방지와 제외 데이터 비이전을 확인한다.
- 이미 승인된 신규 음악 자료·출처·검수 이력을 덮어쓰지 않는다. 전체 덤프 재주입이나 DB 초기화를 하지 않는다.
- 전환 실패 시 신규 worker/sender를 정지하고 신규 DB의 이전 영수증·작업 상태를 기준으로 복구한다. 기존 DB에 다시 쓰는 구 runtime 재가동을 자동 복구로 삼지 않는다.
- 전송 결과가 불명확한 건은 무조건 다시 보내지 않는다. 신규 DB 반영의 되돌리기도 다른 변경과 의존성이 없는 이번 이전 범위에 한해 검토한다.
