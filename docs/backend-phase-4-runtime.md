# 백엔드 통합 4단계 결과 — X 수집과 최소 Discord sender

실행일: 2026-09-22. 이 단계는 신규 통합 DB의 `external_accounts`, `collection_states`, `source_items`, `notification_routes`, `notification_deliveries`를 사용하는 실행 코드를 구현했다. 기존 DB, 실제 Discord, X provider, Google, YouTube, Spotify, LLM은 검증 중 호출하거나 변경하지 않았다. 실제 운영 상태 이전과 연결 전환은 5단계다.

**현재 판정은 부분 구현이다.** 같은 날 확인한 X·Discord 결함은 [보완 1단계](backend-service-step-1-runtime.md)에서 수정했다. [보완 2단계](backend-service-step-2-jobs.md)에서 독립 작업 실행기도 완료했으며 실제 수집 handler는 후속 단계다. 아래는 1차 구현 기록이며 운영 완료를 의미하지 않는다. 최신 결과·수정 순서·합격 기준은 [서비스 검증과 보완 개발 계획](backend-service-readiness-plan.md)을 따른다.

## 최종 실행 경로

```text
enabled external_accounts(platform=x)
  → collection_state lease
  → X pagination 전체 확보
  → source_items 중복 방지
  → 활성 route별 pending delivery 생성
  → cursor 갱신

pending/retry delivery
  → Discord client 준비 확인
  → channel에 source_url 한 줄 전송
  → sent 또는 backoff retry/failed 기록
```

`app/repositories/runtime_delivery.py`가 SQL과 lease를, `app/services/x_collection.py`가 X poll orchestration을, `app/services/notification_delivery.py`가 전송 상태 전이를 담당한다. 모든 session은 `NEW_DATABASE_URL` 전용 identity/revision guard를 통과하며 `DATABASE_URL`로 fallback하지 않는다.

X API pagination은 모든 페이지를 제한 범위 안에서 확보한 뒤 저장한다. 제한을 넘거나 provider가 실패하면 원문과 cursor를 함께 반영하지 않고 계정 상태를 backoff로 돌린다. 한 계정의 새 원문, route별 delivery, cursor는 한 transaction에서 반영된다. `(external_account_id, external_id)`와 `(route_id, source_item_id)` 제약으로 재실행 중복을 막는다.

## Discord 축소

`app/bots/discord_bot.py`의 slash command, interaction, command tree, 명령 동기화, 명령 전용 SQL·파일·외부 연동을 모두 제거했다. 남은 책임은 연결 상태 확인, 이미 설정된 channel 조회, X 원문 URL 한 줄 전송뿐이다. 아티스트·source·route·YouTube·Spotify·가사·Google 관리 명령은 없다. 원격에 과거 등록된 명령을 실제로 삭제하는 작업은 Discord 로그인과 배포 범위 확인이 필요한 6단계 운영 작업이다.

봇이 offline이면 pending delivery를 claim하지 않는다. 현재 전송 처리의 예외는 지수 backoff 후 최대 횟수까지 재시도하고, 만료된 sending lease는 `unknown`으로 바꾼다. 이 문단은 최초 구현 기록이다. 보완 1단계에서는 DB 영수증 기록 재시도를 외부 전송과 분리하고 timeout·취소 등 결과 불명확을 unknown으로 격리했다.

## 제거와 독립 경로

- X 게시글 타입 분류, 공연·티켓 추출, 링크 페이지 조회, LangGraph workflow와 의존성을 제거했다.
- X 글의 YouTube 링크 검색과 live archive 자동 등록을 제거했다. 링크는 `raw_text`에 원문 그대로 있을 수 있지만 작업을 만들지 않는다.
- 현재 scheduler는 X 수집과 Discord 전송만 실행한다. Google·독립 음악 수집 호출은 없다. 이것이 모든 독립 음악 기능의 폐기를 뜻하지는 않는다.
- 독립 YouTube setlist AI 함수와 음악 integration/lyrics 모듈은 보존했지만 구 저장 경로가 남아 있다. 당시에는 worker_jobs 실행기가 없었다. 보완 2단계에서 실행기를 구현했고 [보완 3단계](backend-service-step-3-youtube.md)에서 신규 YouTube 저장 handler를 연결했다. [보완 4단계](backend-service-step-4-spotify.md)에서 등록된 Spotify 계정 저장 handler를 로컬 검증했다. YouTube·등록된 Spotify 계정의 전환만 현재 목표다. admin-web·노래방·가사·번역·독음은 이번 개발에서 제외한다.

## 검증

로컬 PostgreSQL에 migration `001/002`를 매번 적용하는 fixture로 다음을 확인했다.

- 두 페이지의 새 글을 모두 저장하고 가장 최신 external ID로 cursor 갱신
- 같은 페이지 재실행 시 source item과 delivery 중복 0
- route가 없어도 원문 저장, delivery 0
- provider 실패 시 cursor 보존과 backoff
- X 본문의 YouTube URL이 music job을 만들지 않음
- Discord offline일 때 pending/attempt 상태 유지
- 일시 실패 후 retry, 다음 시도 성공 시 message ID와 전달 시각 기록
- 만료된 sending lease를 unknown으로 바꾸고 자동 재전송하지 않음
- 봇 command tree와 관리 surface 없음
- 독립 YouTube setlist 추출 보존

검증 결과: 2026-09-22 전체 backend `168 passed, 2 skipped`. 두 skip은 로컬 조건에 따른 기존 항목이며 실제 외부 서비스 호출은 없었다. pytest cache 경고와 Python 3.14 deprecation 경고는 검증 결과에 영향을 주지 않았다.

## 다음 단계 경계

[서비스 보완 계획](backend-service-readiness-plan.md)의 X·Discord 수정, 독립 음악 수집기, 이전 도구 보완, 통합 검증을 먼저 완료한다. 이후 [5단계](backend-phase-5-cutover.md)에서 구 writer를 정지하고 최신 snapshot으로 선택 이전을 적용한다. 현재 코드와 3단계 도구를 그대로 활성화하는 것을 최종 전환 절차로 사용하지 않는다.
