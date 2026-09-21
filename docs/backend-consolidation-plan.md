# 백엔드 통합 최종 계획 — 신규 DB 일원화

확정 기준: 2026-09-21. 1단계 조사, 2단계 운영 스키마·연결 기반, 3단계 선택 이전 도구·검증을 완료했다. 현재 실행 코드는 아직 신규 DB runtime으로 전환하지 않았으며 Discord 명령·X 분류·YouTube 자동 등록 제거도 4단계 대상이다. 현재 상태는 [1단계 문서](backend-phase-1-baseline.md), [2단계 결과](backend-phase-2-runtime-schema.md), [3단계 결과](backend-phase-3-runtime-migration.md), [백엔드 구조](backend-architecture.md)를 따른다.

## 1. 목표와 범위

1. **신규 PostgreSQL 하나를 API·수집기·Discord 봇의 운영 DB로 사용한다.** 이미 반영된 음악 데이터와 검수 이력은 유지한다.
2. 기존 DB에서는 수집 재개와 Discord 알림에 필요한 행·필드만 선별하여 신규 DB로 이전한다. 나머지 데이터는 기존 DB에 그대로 보존하고 이전하지 않는다.
3. 기존 DB에는 DDL·DML·시드·보정·migration·권한 변경을 수행하지 않는다. 이전 도구는 읽기 전용으로 접근하며 전환 후 정상 runtime은 기존 DB에 연결하지 않는다.
4. X 수집 대상의 기준은 신규 DB의 `external_accounts`다. 별도의 독립 X 계정 명부를 만들지 않는다.
5. X 기능은 **게시글 원문 저장 + Discord에 원문 URL 전송**만 남긴다. 봇 명령·interaction·X 타입 분류·X 글의 YouTube live archive 자동 등록을 제거한다.
6. 관리는 모두 `admin-web`에 모은다. **admin-web 개편은 별도 후속 작업**이며 이번 전환의 선행 조건으로 두지 않는다.
7. Google Calendar는 데이터를 기존 DB에 그대로 보존하고 코드·설정·API를 레거시로 격리한다. 신규 DB로 Google 데이터를 옮기거나 정상 runtime에서 기능을 실행하지 않는다.
8. API는 최종적으로 `/api` 계약으로 통합한다. 백엔드 설정은 루트 `.env`와 공통 Settings로 정리한다.
9. 독립 YouTube·Spotify·노래방·가사 기능은 신규 모델과 호환되게 전환한다. 기능 보존이 기존 음악 데이터 전체 이전을 뜻하지 않는다.

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

관리 위치는 `admin-web`으로 확정한다. 이번에는 신규 DB 전환에 필요한 저장 계약·권한 경계만 정의하고 기존 관리자 기능을 유지한다. 운영 설정·상태 화면을 추가하는 개편은 후속 작업으로 둔다. 봇 명령 삭제를 admin-web 개편 완료에 종속시키지 않는다.

초기 계정 대응·route·상태 이전은 검증된 이전 명세로 수행한다. 이는 일회성 이전 절차이며 상시 설정 파일 관리자나 새 봇 관리 명령으로 확장하지 않는다. 관리 화면이 없는 설정의 수동 변경을 정상 운영 절차로 문서화하지 않는다.

| 계약 | 최종 방향 |
| --- | --- |
| `/api/artists`, `/api/lives`, `/api/albums`, 검색·통계 등 | 현재 신규 조회 서비스와 DTO를 기반으로 통합 |
| 곡·녹음·가사 | 신규 작품/녹음 ID 기준으로 책임 분리 |
| `/api/admin/...` | admin-web의 관리 계약. 운영 화면 확장은 후속 작업 |
| `/api/v2` | 필요 기간 같은 신규 서비스의 임시 별칭, 소비자 전환 후 제거 |
| 구 API·prefix 없는 alias | 소비자와 ID 의미를 확인해 전환 또는 종료. 기존 DB 쓰기로 fallback하지 않음 |
| Google auth·Calendar | 정상 API mount에서 제거하고 legacy로 격리 |

`/api/artists` 등 충돌 경로는 prefix만 지우지 않는다. 소비자별 새 ID·응답 계약을 확인하고 신규 DB만 사용하는 한시적 adapter 또는 명시적 종료로 처리한다. GET에서 수집·생성·전송을 시작하지 않는다. Pydantic 계약과 페이지·필터·정렬 기준을 명시한다.

로컬 관리자의 loopback·세션·CSRF 보호를 유지한다. Discord 서버 공용 설정은 해당 guild 접근·manage_guild·channel 소속 검증을 요구한다. 사용자 조회와 관리 권한을 구분하며 인증 설계를 완료하지 않은 기능을 공개하지 않는다.

## 6. 설정·코드·레거시

최종 backend 설정은 루트 `.env`의 `DATABASE_URL` 하나로 신규 DB를 가리킨다. 공통 Settings, 공유 SQLAlchemy pool, 요청/작업별 session을 사용한다. 관리자·migration/import·이미지 저장 설정도 같은 로더를 사용한다. 프론트 공개 설정과 로컬 도구의 작업 파일은 용도에 맞게 분리한다.

**현재 DATABASE_URL 값부터 바꾸지 않는다.** 구 SQL과 `init_db()` 경로를 격리하고 대상 identity·revision 검사와 신규 repository 전환을 완료한 뒤 연결을 전환한다. 이전 전용 읽기 소스는 `LEGACY_DATABASE_URL` 같은 명시적 별도 입력으로 받고 정상 runtime에서는 로딩하지 않는다. 실제 URL·토큰은 문서·보고서·로그에 남기지 않는다.

`.env.catalog`와 `NEW_DATABASE_URL`은 소비자를 모두 전환한 뒤 제거한다. 과도기 별칭이 있으면 충돌 시 오류를 내고 암묵적으로 DB를 선택하지 않는다. 기존 DB의 baseline migration이나 revision 표를 만들지 않는다. 신규 DB의 적용된 `001`은 변경하지 않고 후속 revision만 추가한다.

| 현재 위치 | 처리 |
| --- | --- |
| `artists.py`와 artist service/repository | 신규 아티스트 마스터 사용. 수집 상태·권한을 프로필 CRUD에서 분리 |
| `songs.py`와 song service/repository | 신규 작품·녹음·가사 계약으로 전환. 기존 곡/가사 추가 이전은 제외 |
| `catalog_read.py` | 신규 조회 구현 재사용 |
| `read_catalog.py`, `read_spotify.py` | 사용 여부를 확인해 legacy 격리 또는 제거 |
| `bots/discord_bot.py` | command/interaction·음악 SQL·생성 helper 제거. 연결과 URL 전송만 유지 |
| `agents/scheduler.py` | X poller/sender와 독립 음악 worker 실행 단위 분리 |
| `agents/music_graph.py` | X 분류/공연 추출 workflow 제거 |
| `integrations/ai_extractor.py` | X 분류·추출 제거. 독립 YouTube setlist 추출은 보존 |
| `core/db.py` | 구 DDL·시드·보정 경로를 정상 시작 및 이전 도구에서 차단 |
| Google OAuth·Calendar 코드와 설정 | legacy 격리. refresh·sync·callback 등 정상 실행 연결 제거 |
| `web.bak`와 구 관리 router | 기존 DB 쓰기 경로 종료 후 legacy 격리. admin-web 개편은 별도 |

기존 계층을 살려 collection/notification/catalog 책임과 legacy 경계를 구분한다. 신규 코드가 legacy를 import하지 않도록 검사한다. X 분류 제거 후 다른 소비자가 없으면 LangGraph를 제거하되, 독립 setlist·가사·번역에서 쓰는 OpenAI 의존성은 유지한다. **구 DB의 분류 컬럼이나 테이블은 삭제·수정하지 않는다.**

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

external_accounts 기반 X 수집과 durable sender를 구현한다. 봇 명령·X 분류·X→YouTube 연결을 제거하고 독립 YouTube·Spotify·노래방·가사 경로를 신규 DB와 호환되게 전환한다.

완료 조건: fixture에서 신규 글·중복·무 route·offline·재시도·pagination을 검증하고 X가 다른 수집이나 Google을 호출하지 않는다. admin-web 개편은 요구하지 않는다.

### 5단계 — API 통합·실제 이전·runtime 전환

구 쓰기 프로세스를 배포/실행 설정에서 정지한 뒤 최종 읽기 스냅샷과 명세를 재검증한다. 구 DB의 활성 플래그를 변경해 정지하지 않는다. Google callback·refresh·sync와 구 DB를 사용하는 API/script의 실행 연결도 이 시점까지 차단한다. 신규 DB에 선택 이전을 반영·검증하고 API/worker/bot의 연결과 신규 프론트를 전환한다.

완료 조건: 정상 runtime은 신규 DB만 사용하고 구 DB 쓰기 경로는 실행되지 않는다. 기존 성공 알림 재전송과 과거 글 대량 알림 없이 계정별 수집을 재개한다. 연결 변경만으로 구 SQL이 신규 DB에서 실행되지 않는다.

### 6단계 — 레거시·환경설정·배포 정리

Google과 구 API/UI를 격리하고 임시 v2/호환 alias·중복 env 로딩을 종료한다. 해당 bot의 원격 slash command 제거를 검증하고 운영·복구 문서를 갱신한다.

완료 조건: 신규 실행 경로에 legacy import·Google 호출·기존 DB 접속·X 분류·YouTube 자동 등록이 없다. 기존 DB와 제외 데이터는 변경 없이 보존된다.

### 별도 후속 — admin-web 개편

외부 계정 수집 설정, route, 작업/전송 상태와 재시도 관리 화면을 추가한다. 봇 명령의 일대일 복제는 하지 않으며 이미 정의한 서비스·권한 계약을 사용한다.

## 8. 전환 검증과 복구

- 이전 시점의 source snapshot과 신규 DB revision·대응 계정 version을 확인한다. 조사 후 변경된 계정·cursor·route는 재검토한다.
- 기존 DB에는 SELECT만 실행한다. 읽기 전용 트랜잭션을 사용하고 권한 변경이나 초기화 함수를 호출하지 않는다.
- fixture와 실제 DB 검증 결과를 구분한다. 실제 Discord·Calendar·LLM 호출을 테스트에 사용하지 않는다.
- 선택된 원문·소유권·참조 보존, 계정 매핑, route별 전송 중복 방지와 제외 데이터 비이전을 확인한다.
- 이미 승인된 신규 음악 자료·출처·검수 이력을 덮어쓰지 않는다. 전체 덤프 재주입이나 DB 초기화를 하지 않는다.
- 전환 실패 시 신규 worker/sender를 정지하고 신규 DB의 이전 영수증·작업 상태를 기준으로 복구한다. 기존 DB에 다시 쓰는 구 runtime 재가동을 자동 복구로 삼지 않는다.
- 전송 결과가 불명확한 건은 무조건 다시 보내지 않는다. 신규 DB 반영의 되돌리기도 다른 변경과 의존성이 없는 이번 이전 범위에 한해 검토한다.
