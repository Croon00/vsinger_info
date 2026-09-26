# 확정 서비스 검증과 보완 개발 계획

기준일: 2026-09-23 (최초 조사 2026-09-22). 조사 대상: `feat/new-front`, `24bfeea`의 코드·스키마·계획 및 로컬 테스트. 서비스 범위는 최신 사용자 결정과 [백엔드 통합 최종 계획](backend-consolidation-plan.md)을 따른다. 보완 단계 A~F를 각각 1~6단계로 실행한다. 이 문서는 실제 운영 전환 전에 완료할 보완 작업과 합격 기준이다.

**현재 판정: 로컬 보완 A~F 및 [운영 DB 선택 이전](backend-cutover-2026-09-23.md) 완료, 전체 서비스 운영 전환 미완료.** 신규 조회 API, X·Discord, 독립 YouTube·등록 Spotify 수집, 설정 경계, 이전→수집→실제 `/api` 통합을 로컬에서 검증했다. 신규 DB에서 YouTube 작업이 처리되고 있지만 X 수집에 `NoAccountError`가 다수 발생한다. 혼합 소유 업로드로 실패한 YouTube poll 9건은 코드 수정 후 배포·재검증이 필요하다. Railway 서비스별 실행 상태·Discord 전송·배포 웹의 실제 운영 검증도 남아 있다.

초기 로컬 검증은 운영 DB 변경과 실제 provider 호출 없이 진행했다. 이후 운영 DB 선택 이전과 제한된 공개 YouTube API 확인을 별도로 수행했으며, 결과는 [이전 기록](backend-cutover-2026-09-23.md)에 있다. Discord 전송과 배포된 수정 코드의 검증은 아직 수행하지 않았다. 아래에서 **테스트 재현**, **코드 확인**, **운영 미검증**을 구분한다.

## 1. 서비스 범위와 현재 판정

| 확정 서비스 | 현재 구현 / 검증 결과 | 운영 전환 전 필요한 일 |
| --- | --- | --- |
| 신규 DB 조회 API와 조회 웹 | `/api`에서 아티스트·라이브·가창·검색·통계·공연·앨범·가사 조회. 격리 DB 이전→수집→실제 API와 신규 DB 읽기 브라우저 검증 완료 | 운영 프록시·이미지 접근, 신규 DB에 없는 앨범·가사의 실제 화면 확인 |
| admin-web | 대규모 개편 예정. 이번 개발에서는 없는 것으로 취급 | 관리 화면·관리 API·연결·검증을 이번 목표에서 제외 |
| X 원문 수집 | 보완 1단계에서 기준선·계정 순환·재활성화·lease 수정, 운영 DB 상태 이전 완료 | 수집기의 `NoAccountError` 원인 확인과 새 글 수집 성공 검증 |
| Discord X URL 전송 | 보완 1단계에서 채널/route 검증·기록 장애 복구·결과 불명 격리 구현 | 실제 권한·채널 전송 운영 검증 |
| 독립 YouTube 라이브·세트리스트 수집 | 활성 신규 계정 감시, 영상/출처/가창 저장, 댓글 대기 재개, 이전 작업→가짜 provider→실제 API 통합 검증 | 운영 provider·주기·quota 검증 |
| 독립 YouTube 커버 수집 | 보완 3단계: `videos/covers` 저장. 기존 `cover_artists` 보존, 불명확한 참여자는 설명 원문/검토 후보에 유지 | 실제 provider 검증. 인물·작품 검수와 커버 조회 화면은 별도 |
| Spotify 수집·연결 | 보완 4단계: 등록된 활성 계정의 앨범·녹음·트랙 저장 및 공동 크레딧·수동 연결 보존 fixture 검증 | 실제 provider·계정 규모/쿼터·이전 상태 검증 |
| 노래방 정보 | 확정 연결에는 songs.id가 필요하며 현재 구축 전 | 후속 TODO. 이번 통합 목표와 worker 실행에서 제외 |
| 가사·번역·독음 | 기존 코드 보존 | 후속 TODO. 이번 통합 목표·자동 보완·worker 실행에서 제외 |
| 프로필 이미지 | 저장된 URL과 S3 설정 기반 크기별 URL 생성, 로컬 브라우저에서 실제 이미지 로드 확인 | 배포 환경의 이미지 URL 접근 확인, 업로드 실행 환경과 조회 환경 구분 |
| Google Calendar | 정상 API·scheduler에서 실행하지 않음 | 기존 DB 데이터를 그대로 보존하고 코드·설정·스크립트를 legacy로 격리 |

Discord 관리 명령, X 타입 분류, X 본문에서 YouTube 링크를 찾아 자동 등록하는 기능은 복구하지 않는다. 공연 자동 수집·새 관리 화면·추가 과거 음악 데이터 이관도 이번 보완 범위가 아니다. **admin-web은 의존 대상에서 제외한다. YouTube·Spotify 백엔드만 독립적으로 완성하며 노래방·가사·번역·독음은 이번 완료 조건에 포함하지 않는다.**

## 2. 사전 조사 결과와 후속 검증

| 검증 | 2026-09-22 결과 | 범위와 한계 |
| --- | --- | --- |
| 백엔드 전체 `pytest -q -p no:cacheprovider` | **165 passed**, 312 warnings | 격리된 로컬 PostgreSQL과 provider mock. 운영 DB/외부 전송 검증 아님 |
| 조회 웹 `vitest run` | **26 passed**, 5 files | HTTP fixture를 사용하는 테스트 포함. 운영 배포 E2E 아님 |
| 조회 웹 `vue-tsc -b`, `vite build` | 통과 | 타입·번들 검증 |
| admin-web `vue-tsc --noEmit`, `vite build` | 통과 | 타입·번들 검증 |
| 수정 전 서비스 계약 검사 | **6 xfailed** | 사전 조사 기록. 수정 후 합격 건수와 구분 |

사전 조사의 임시 검사는 `.tmp/test_service_readiness_probe.py`였다. G-D2는 로컬 audioop 미설치 조건이 섞여 있었으므로 requirements에 명시된 `audioop-lts`를 설치한 뒤 기준 commit의 실제 Discord client 코드로 cache miss의 LookupError와 REST 미호출을 별도 재현했다. 이번 보완에서는 6개 사례를 [정규 회귀 테스트](../tests/test_runtime_readiness.py)로 옮기고 timeout·취소·DB 기록 장애·권한·다중 worker 검사를 추가했다. 최신 실행 결과는 [보완 1단계 결과](backend-service-step-1-runtime.md)에 기록한다.

기존 단계 문서의 당시 테스트 기록은 이번 commit의 재검증 결과와 구분한다. 테스트 통과 건수만으로 미구현 수집기나 운영 전송의 완료를 판정하지 않는다.

### 2.1 수정 전 X·Discord 결함 — 보완 1단계에서 수정

| ID | 재현 조건과 실제 결과 | 필요한 수정 |
| --- | --- | --- |
| G-X1 | cursor 없는 신규 계정, 활성 route, 첫 응답에 과거 글 2개 → delivery 2개 생성 | 최초 조회는 알림 없는 기준선 확보. 기존 cursor 승계 계정의 새 글 처리와 구분 |
| G-X2 | 계정 3개·batch limit 2로 두 번 실행 → 앞의 2개만 계속 조회 | 다음 실행 시각·마지막 조회 시각을 갱신하고 공정하게 선점. 기본 limit 100을 넘는 구성에서도 누락 방지 |
| G-X3 | 계정 `collection_enabled=true`, 이전 상태 `disabled` → 수집 대상 0개 | 활성 여부는 계정 필드 하나로 결정. 상태의 disabled 잔재가 재활성화를 막지 않도록 수정 |
| G-D1 | Discord 전송 성공 후 `mark_delivery_sent`만 실패 → retry 후 같은 URL 다시 전송 | 외부 전송과 영수증 저장 오류를 분리. 성공 message ID 기록만 복구하고 불명확한 전송은 격리 |
| G-D2 | 준비된 client의 채널 cache가 비었고 REST 조회로는 채널 접근 가능 → `LookupError` | `get_channel` 실패 시 실제 채널 조회. guild·채널 유형·전송 권한 검증 |
| G-D3 | delivery 선점 직후 route 비활성화 → 그대로 외부 전송 | 전송 직전 route·계정·guild/channel·lease를 다시 검증하고 변경된 건 생략 |

근거: [X service](../app/services/x_collection.py), [runtime repository](../app/repositories/runtime_delivery.py), [delivery service](../app/services/notification_delivery.py), [Discord adapter](../app/bots/discord_bot.py). G-X2는 작은 batch로 재현한 규모 관련 결함이며 현재 운영 계정 전부가 실제로 누락됐다고 판단한 것은 아니다. G-D2의 수정 전 client는 Intents.none()과 cache 조회에만 의존했다. 현재는 guild intent·REST fallback·권한 검증을 사용한다. 실제 서버 접근은 배포 시 확인한다.

### 2.2 코드로 확인한 나머지 부족 사항

1. **음악 작업 실행기 — 2단계 완료.** worker_jobs 선점·실행·재시도·취소·lease 갱신·원자 결과 저장과 독립 runtime loop를 구현했다. YouTube handler는 3단계, Spotify handler는 4단계에서 연결했다. 미구현 작업은 선점하지 않는다. [2단계 결과](backend-service-step-2-jobs.md)를 따른다.
2. **YouTube 신규 저장 경로 — 3단계 완료.** 신규 `youtube_catalog` adapter와 `youtube_collection` service/repository를 사용한다. [3단계 결과](backend-service-step-3-youtube.md)에 보존/검토/대기 계약을 기록한다. 다음은 최초 조사 당시 구 경로다: [채널 감시](../app/integrations/youtube_channel_monitor.py), [아카이브 수집](../app/integrations/youtube_live_archive.py)은 `get_connection()`과 구 테이블을 사용한다. 새 주소를 구 연결에 넣어 해결할 수 없다.
3. **YouTube 재개 작업 선택 누락 가능성.** [이전 도구](../scripts/migrate_runtime_state.py)는 `youtube_channel_videos.status <> 'processed'`만 작업으로 만든다. 기존 `_collect_due_videos()`는 archive 생성 뒤 채널 영상은 processed로 바꾸지만 archive는 댓글/세트리스트 pending일 수 있다. 이 대기 작업은 현재 선택 조건에서 빠질 수 있다. 실제 누락 건수는 보완된 읽기 전용 조사로 산출해야 한다.
4. **이전 작업과 새 작업의 중복 기준 불일치.** 현재 YouTube 이전 key는 `legacy:youtube_channel_videos:{id}`다. 새 poller가 같은 영상에 다른 key로 작업을 만들지 않도록 외부 영상 ID·작업 목적 기준을 통일해야 한다. 완료 콘텐츠를 이관하지 않은 영상의 재발견도 자동 과거 수집으로 이어지지 않아야 한다.
5. **주기·장애 격리 — 1단계 보완.** X와 delivery를 독립 loop로 분리했다. X의 AGENT_INTERVAL_SECONDS와 시작 지연은 유지하고 DB의 다음 조회 시각으로 호출을 제한한다. Discord 대기열은 5초마다 확인한다. 실제 Railway 값은 미확인이다.
6. **lease — 1단계 보완.** 작업을 한 건씩 선점하고 외부 호출 timeout을 lease보다 짧게 둔다. X 저장 및 delivery 결과 반영에서 고유 claim owner와 유효 기한을 확인한다. 다중 worker·만료된 결과의 차단을 fixture로 검증한다.
7. **정규화 모델과 구 저장 코드 불일치.** Spotify의 구 저장 SQL은 신규 앨범·녹음 구조로 전환해야 한다. 노래방·가사·번역·독음은 TODO로 제외한다. 남은 모듈을 연결만 하면 완료되는 상태가 아니다.
8. **배포와 복구 절차 부족.** `/health`는 liveness이며 2단계에서 읽기 전용 `/ready`를 추가했다. `railway.json`만으로 조회 웹의 운영 `/api` 프록시·SPA fallback·이미지 접근이 성립하는지 알 수 없다. 전환 잠금을 모르는 구 배포본으로 rollback하면 기존 DB writer가 다시 실행될 수 있다.

## 3. 보완 개발 순서

아래 A~F는 기존 통합 계획을 완료하기 위한 작업 묶음이다. 실제 상태 이전·운영 활성화인 **5b는 A~F의 로컬 완료 조건을 충족한 뒤** 진행한다. 전 과정에서 기존 DB는 읽기 전용이며 정상 worker는 신규 DB만 사용한다.

### A. 1단계 — X·Discord 실행 안정화

구현과 로컬 검증을 완료했다. [실행 결과](backend-service-step-1-runtime.md)를 따른다. 아래는 구현 계약과 합격 기준이다.

- G-X1~G-D3를 정규 회귀 테스트로 만들고 수정한다. 초기 cursor 없음과 유효한 빈 조회 상태를 구분하여 첫 조회 실패/빈 응답/재시작에도 기준선이 일관되게 유지되게 한다.
- `collection_enabled`와 보관 상태를 수집 시작·저장 시 확인한다. 계정의 고정 platform ID와 handle 누락·불일치는 명시적 오류로 남기며 이름으로 임의 연결하지 않는다. 기존 승인된 매핑·활성 상태는 유지한다.
- X polling과 Discord delivery 실행 주기를 분리한다. X 조회량을 늘리지 않고도 전송·재시도가 제시간에 실행되게 하며, 특정 계정/작업 오류가 다른 실행기를 막지 않게 한다.
- 짧게 선점하거나 lease 갱신을 구현하고 결과 반영 때 owner/version을 확인한다. stale worker가 cursor·delivery 상태를 갱신하지 못하게 한다.
- 명백한 미전송, 영구 권한 오류, 일시 오류, 결과 불명확을 분리한다. DB 영수증 저장 재시도와 외부 메시지 재전송을 같은 retry로 취급하지 않는다. 결과 불명확은 `unknown`으로 격리한다.
- Discord 채널을 실제로 조회하고 route의 guild 소속·봇 접근·전송 권한을 검증한다. route 재검증 이후 외부 호출까지의 경합과 provider 응답 손실까지 포함한 exactly-once는 보장하지 않는다.

완료 조건: 6개 결함 재현 테스트 통과, offline/권한 상실/429/timeout/DB 장애/lease 만료/다중 worker 테스트 통과, 기존 성공 delivery 재전송 0. 봇 명령·X 분류·X→YouTube 호출 0.

### B. 2단계 — 독립 작업 실행기

실행기와 로컬 명령·readiness의 구현 및 검증을 완료했다. [2단계 결과](backend-service-step-2-jobs.md)에 실행 계약을 기록한다. 실제 provider handler 연결은 3·4단계다.

- 기존 `worker_jobs`를 재사용하여 선점→실행→성공/재시도/실패/취소를 구현한다. YouTube 감시와 수집, Spotify만 handler로 연결한다. 스키마에 남은 karaoke_collect/lyrics_collect는 실행하지 않는다. X를 위해 별도의 작업 명부를 중복 생성하지 않는다.
- payload를 작업별 Pydantic 모델로 검증하고 버전·외부 ID·신규 ID 의미를 명시한다. 같은 작업의 재요청은 중복 실행하지 않되 명시적 재수집은 추출 버전/요청 번호로 구분한다.
- provider 호출은 DB transaction 밖에서 수행하고 결과·작업 완료를 원자 반영한다. timeout·취소·종료 신호·lease 갱신·다중 worker·일시 장애 재시도·영구 실패를 지원한다.
- 주기 작업은 `next_poll_at`, 재시도는 `next_attempt_at`에 따라 실행한다. 긴 YouTube/LLM 작업이 X 알림을 막지 않게 동시 실행 수·provider별 요청량을 제한한다. 한 프로세스 안의 독립 loop로 시작할 수 있으며 별도 서비스 분리는 필수 조건이 아니다.
- 준비 상태에 DB identity/revision, worker heartbeat, 마지막 성공·실패, 지연 작업 수를 표시한다. 토큰·원문 전체를 로그에 남기지 않는다. 기존 전환 잠금은 유지하고 새로운 중복 on/off 환경변수를 기능마다 늘리지 않는다.
- 수동 수집/재수집은 UI와 무관한 내부 service와 명시적 로컬 작업 실행 명령으로 요청하고 작업 ID·상태를 제공한다. 이는 수집 작업 실행 수단이며 계정/route를 관리하는 임시 제품을 만들지는 않는다.
- admin-web·관리 HTTP API·관리 인증/권한 화면은 만들거나 연동하지 않는다. 미래 관리자가 사용할 수 있는 타입 명시된 service 경계만 유지한다. 공개 조회 GET과 봇 명령으로 작업을 시작하지 않는다.

완료 조건: 모의 handler의 재시작·중복 요청·lease 만료·실패 후 재개 검증, GET 외부 호출 0, 다른 worker 실패 중 Discord 전송 진행. admin-web 없이 실행·검증 가능.

### C. 3단계 — YouTube 아카이브·세트리스트·커버 신규 DB 전환

정상 경로는 `external_accounts(platform=youtube, collection_enabled=true)` → 채널 변경 조회 → 영상별 작업 → 메타데이터/댓글 확보 → 세트리스트 추출 → 신규 DB 저장이다. `archived_at`이 있는 계정은 제외한다. X 게시글은 이 경로의 입력이 아니다.

| 수집 결과 | 신규 저장 대상 / 규칙 |
| --- | --- |
| 채널 감시·uploads playlist·재개 시각 | `external_accounts` 참조 + `collection_states`. 별도 채널 명부를 만들지 않음 |
| YouTube 영상 식별·제목·길이·공개 상태 | `videos`, `(platform, platform_video_id)`로 중복 차단, 업로드 계정 `source_account_id` |
| 라이브·실제 방송 시각·세트리스트 확보 상태 | `live_archives`, 영상당 한 행. 업로드 시각을 방송 시각으로 임의 복사하지 않음 |
| 진행·게스트·개별 가창자 | `archive_artists`, `performance_artists`. 업로드 계정 소유자를 모든 가창자로 단정하지 않음 |
| 순서·timestamp·곡명/아티스트 원문 | `performances`. 불명확한 작품은 `song_id=NULL`, 원문과 출처를 보존 |
| 댓글/설명·외부 comment ID·추출 근거 | `source_documents`, `archive_sources`, 필요한 검수/변경 기록 |
| 커버 영상·참여 아티스트 | `videos`, `covers`, `cover_artists`. 일반 영상·라이브·커버 판정을 구분 |

- provider/파싱 부분에서 DB 접근을 분리하고 신규 repository를 구현한다. 구 `youtube_live_archives`/`youtube_song_performances` SQL을 재사용하지 않는다.
- 기존 채널 수집의 대상 제목 규칙·완료 라이브 조건·커버 범위를 fixture로 고정한다. 기존 코드의 채널 재확인 1일, 방송 종료 후 24시간 대기, pending 댓글 재확인 동작을 출발점으로 삼되 실제 운영 설정과 provider 한도를 확인해 최종값을 문서화한다.
- 영상 발견과 세트리스트 확보를 별도 상태로 유지한다. 댓글이 늦게 달리는 경우, 댓글 비활성, 비공개/삭제, quota/통신 오류를 구분한다. 기존 archive의 최대 대기 횟수와 새 `worker_jobs`의 기본 `max_attempts=5`를 무조건 같은 의미로 매핑하지 않는다.
- 정규 파싱과 기존 setlist 추출을 보존하고 추출 모델/버전·원문 hash를 기록한다. 처리 성공이 인물·곡 연결의 검수 완료를 뜻하지 않게 한다. 기존에 저장된 한글 정보는 보존하지만 새로운 번역·독음 생성과 노래방 보완은 실행하지 않는다. 모호한 곡/인물 연결은 미확정 상태로 보존한다.
- 이미 승인된 영상·가창·인물 연결·번역을 재수집으로 일괄 삭제하거나 덮어쓰지 않는다. 수동 수정과의 version 충돌은 보류하고, 댓글 수정/추출 버전 변경은 변경 후보로 비교한다.
- 기존 신규 DB에 없는 과거 완료 영상의 자동 재발견은 수집 기준선/최소 외부 ID 상태로 차단한다. 명시적 backfill은 승인한 계정·기간/영상 범위에만 수행한다.
- 채널을 통한 자동 수집 외에 명시적 URL 등록·backfill도 같은 job/service 계약을 사용한다. admin-web 없이 내부 service/로컬 작업 명령으로 검증한다.

완료 조건: 종료 라이브 발견→대기→댓글 확보→원문/가창 저장→`/api/artists/{artist_id}/lives`·`/api/lives/{archive_id}`·`/api/search` 조회까지 로컬 통합 테스트 통과. 댓글 지연·영구 미확보·중복 영상·재시작·동일 댓글 재처리·수동 수정 보존·공동 가창·모호한 곡·커버 분리 검증. 구 DB 연결 0, X 링크로 생성한 작업 0.

### D. 4단계 — 등록된 Spotify 계정의 수집·연결

- 신규 `external_accounts`의 `platform=spotify`, `collection_enabled=true`, `archived_at IS NULL` 계정만 수집한다. `artist_external_accounts`의 기존 관계를 연결 기준으로 사용한다.
- Spotify 고정 ID가 없거나 유효하지 않으면 오류로 남기고 수집하지 않는다. 이름 검색으로 다른 계정을 찾아 연결하거나 계정을 자동 생성·활성화하지 않는다. 미등록 아티스트는 건너뛴다. 기존 아티스트의 ID는 수집과 분리된 후보 조사·검수·적용으로만 등록한다([곡 마스터 구축 계획](song-master-plan.md)).
- `albums/album_artists`, `recordings/recording_artists/recording_external_ids`, `album_tracks`에 저장한다. 작품은 근거가 있을 때만 연결하고 미확정 `song_id`를 임의 생성하지 않는다.
- 명시적 sync와 YouTube 매칭은 등록된 Spotify 계정의 작업 범위 안에서만 수행한다. 기존 수동 연결·제외를 보존하고 모호한 매칭은 보류한다. 등록되지 않은 계정을 공동 발매 관계를 이유로 자동 연결하지 않는다.
- 가사·번역·독음·노래방 보완과 admin-web 연결은 호출하지 않는다. provider 메타데이터 원문과 이미 저장된 번역은 보존한다.

완료 조건: 등록 계정만 작업 생성·저장되고 미등록/비활성/보관/ID 누락 계정의 provider 호출은 0. 같은 외부 ID 재실행 중복 0, 공동 발매·트랙 관계·수동 연결 보존, 앨범 API 조회 통과.

### 별도 TODO — 이번 통합의 완료 조건에서 제외

- **노래방:** 신규 `songs.id`를 구축하고 가창/곡 매칭을 확정한 뒤 `karaoke_numbers.song_id`로 연결한다. 지금은 노래방 수집/매칭/번호 보완을 실행하지 않는다.
- **가사·번역·독음:** 신규 녹음·곡 연결 및 검수 정책을 정한 뒤 다시 설계한다. YouTube/Spotify 수집의 자동 번역도 포함해 이번에는 새로 실행하지 않는다. 기존 데이터 조회는 유지한다.
- **admin-web:** 대규모 개편에서 계정·route·작업 관리를 별도로 설계한다. 현재 백엔드 개발은 이 앱의 존재나 관리 API를 전제로 하지 않는다.

### E. 5단계 — 선택 이전·설정·legacy 경계 완성

- A~D에 필요한 schema 보완은 `001/002`를 수정하지 않고 후속 revision으로 추가한다. 운영 API·worker·이전 스크립트의 revision 검사가 현재 `001/002`에 고정되어 있으므로 함께 갱신한다. 신규 테이블 필요성은 최소화하고 기존 정규화 모델을 우선 사용한다.
- YouTube 작업 선택을 채널 미완료 영상뿐 아니라 **승인된 감시 계정에 속한 archive 댓글/세트리스트 대기 작업**까지 확장한다. 이미 처리된 채널 영상과 pending archive가 공존하는 fixture를 추가한다. 채널 근거가 없는 구 X 자동등록 후보는 포함하지 않고 보류 사유를 보고한다.
- 완료 영상은 본문/가창을 옮기지 않고 재수집 방지에 필요한 최소 외부 ID·기준선만 검토한다. 기존 신규 영상은 외부 ID로 연결하며 동일한 영상 작업 key를 사용한다. pending 대기 횟수·마지막 확인·다음 시각·오류를 새 의미에 맞게 보존한다.
- 최종 manifest에 선택/제외 이유, 계정 version, cursor, route 소유권, 성공 전송 이력, 작업별 수와 외부 ID 대응을 포함한다. 최신 snapshot으로 dry-run·원자 apply·재실행·중단 복구를 다시 검증한다. 기존 DB에는 SELECT만 수행한다.
- `artists.py`, `songs.py` 등 구 테이블/ID 의미를 가진 API·repository·수집 스크립트는 신규 service로 전환하거나 legacy로 격리한다. 정상 모듈에서 `app.core.db`·Google·구 저장 코드 import가 없어야 한다. legacy 진입점도 잘못 실행해 구 DB를 쓰는 경로가 남지 않게 차단한다.
- 그 뒤 루트 `.env`의 `DATABASE_URL`이 신규 DB를 가리키도록 설정 계약을 통합한다. `.env.catalog`·`NEW_DATABASE_URL`의 소비자를 일괄 전환하고 충돌 검사를 둔다. instance 검증 이름은 `NEW_DATABASE_INSTANCE_ID`로 통일한 현재 결정을 유지한다. 이전 원본은 별도 명시적 입력 `LEGACY_DATABASE_URL`로만 받는다.
- 이미지의 `AWS_ENDPOINT_URL_S3`·`AVATAR_BUCKET` 등 URL 설정과 업로드 자격 증명의 실행 위치를 나눈다. 조회 API의 이미지 URL 생성에는 업로드 access key가 필요하지 않으며 이미지 업로드 도구에는 필요하다. YouTube·Spotify·세트리스트 추출용 LLM 설정도 실제 실행 handler에 필요한지 시작 검사에 포함한다.
- Google OAuth/Calendar API·helper·스크립트·환경변수와 구 관리 웹을 legacy로 격리한다. 데이터는 기존 DB에 보존한다. 임시 `/api/v2` alias는 소비자 전환을 확인한 뒤 제거한다.

완료 조건: 정상 API/worker/도구가 같은 신규 DB 설정·guard를 사용하고 legacy 연결 시도 0. 기존 DB 무변경, 제외 데이터 유입 0, 필수 재개 작업 누락 0, 성공 전송 재예약 0, 반복 apply 중복 0. 설정 계약을 확정한 뒤 Railway 관리자용 변수표를 다시 작성한다.

### F. 6단계 — 통합 검증과 운영 전환 준비

1. 격리된 PostgreSQL에 최종 migration을 적용하고 가짜 provider로 **계정→작업→신규 저장→실제 `/api` 응답**을 한 번에 검증한다. 웹의 mocked HTTP 테스트와 구분한다. 기존 승인 데이터·수동 수정과 worker의 version 충돌을 DB fixture로 검증한다. admin-web은 사용하지 않는다.
2. X/Discord의 장애 주입과 YouTube·Spotify 처리 회귀 테스트를 전체 실행한다. legacy import/연결·X의 다른 수집 호출·조회 요청의 외부 호출을 금지하는 경계 검사를 실행한다.
3. 조회 웹을 빌드하고 로컬 브라우저에서 라이브 상세/영상 연결/가창/이미지와 빈 데이터를 확인한다. 신규 DB에 앨범·가사 행이 없으므로 해당 내용·실패 화면은 HTTP fixture 브라우저 테스트와 격리 DB API 테스트로 구분한다. [6단계 결과](backend-service-step-6-validation.md)에 실제 범위를 기록한다.
4. 보존/제거 기능, migration revision, 설정 변경, 테스트 결과, 실제 운영 미검증 항목을 PR 검토 자료에 기록한다. 기존 PR은 병합 없이 닫혔으며 사용자가 PR을 직접 처리하기로 했다. Agent는 PR 생성·재개·push를 하지 않는다.
5. Railway 관리자는 배포 서비스·기존 writer·환경변수·디스크의 twscrape 계정 저장소·봇 권한·웹 프록시를 확인한다. worker 수·주기·provider 한도와 첫 실행 시점을 확정한다. 코드 기본값을 운영값으로 간주하지 않는다.
6. 선택 이전과 읽기 검증은 완료했다. 남은 [5단계 전환 절차](backend-phase-5-cutover.md)에 따라 실제 writer 위치·X provider 상태를 확인하고, 수정 코드를 배포한 뒤 봇 연결과 수집/전송을 단계적으로 검증한다. 로컬 mock 성공으로 운영 검증을 대체하지 않는다.

운영 최종 합격: 모든 활성 대상이 설정한 주기 안에 처리되고, 신규 영상/음악 정보가 신규 DB와 조회 화면에 나타나며, X 새 글 URL이 올바른 route로 전달된다. 과거 성공 알림·첫 조회의 과거 글 재전송이 없고, 구 DB 쓰기·Google 호출·봇 명령·X 분류·X→YouTube 작업 생성이 없다. 실제 관찰값과 담당자 확인을 전환 기록에 남긴다.

## 4. 완료 판정과 남은 외부 확인

- [x] 확정 범위와 현재 실행 경로 대조, 기본 테스트·빌드 실행
- [x] X·Discord 계약 위반 6건을 로컬에서 재현
- [x] A. X·Discord 안정화 — [보완 1단계 결과](backend-service-step-1-runtime.md)
- [x] B. 독립 YouTube·Spotify 작업 실행기 — [2단계 결과](backend-service-step-2-jobs.md)
- [x] C. YouTube 신규 DB 수집·저장·재개 — [3단계 결과](backend-service-step-3-youtube.md)
- [x] D. 등록된 Spotify 계정만 신규 DB 수집·연결 — [4단계 결과](backend-service-step-4-spotify.md)
- [x] E. 선택 이전 보완·환경설정 통합·legacy 격리 — [5단계 결과](backend-service-step-5-migration.md)
- [x] F. 전체 경로 로컬 통합 검증·PR 검토 자료·배포 준비 — [6단계 결과](backend-service-step-6-validation.md). PR은 사용자가 직접 처리
- [x] 최종 manifest 적용·receipt 및 재실행 중복 0 확인 — [운영 DB 이전 기록](backend-cutover-2026-09-23.md)
- [ ] 실제 X·YouTube·Discord·조회 웹 운영 검증과 Railway 실행 상태 정리

개발 계획을 시작하기 위해 서비스 범위를 다시 결정할 필요는 없다. 실제 계정/작업 매핑에서 새 충돌이 발견되거나 과거 수집 범위·비용이 기존 확정을 넘어야 한다면 대상과 근거를 제시해 결정받는다. Railway 접근·현재 설정·실제 봇 권한·provider 한도는 운영 활성화 전에 관리자와 확인해야 한다.
