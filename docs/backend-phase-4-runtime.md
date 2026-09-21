# 백엔드 통합 4단계 결과 — X 수집과 최소 Discord sender

실행일: 2026-09-22. 이 단계는 신규 통합 DB의 `external_accounts`, `collection_states`, `source_items`, `notification_routes`, `notification_deliveries`를 사용하는 실행 코드를 구현했다. 기존 DB, 실제 Discord, X provider, Google, YouTube, Spotify, LLM은 검증 중 호출하거나 변경하지 않았다. 실제 운영 상태 이전과 연결 전환은 5단계다.

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

봇이 offline이면 pending delivery를 claim하지 않는다. 전송 실패는 지수 backoff 후 최대 횟수까지 재시도한다. Discord가 메시지를 받았는지 확정할 수 없는 상태에서 lease가 만료된 행은 `unknown`으로 바꾸고 자동 재전송하지 않는다.

## 제거와 독립 경로

- X 게시글 타입 분류, 공연·티켓 추출, 링크 페이지 조회, LangGraph workflow와 의존성을 제거했다.
- X 글의 YouTube 링크 검색과 live archive 자동 등록을 제거했다. 링크는 `raw_text`에 원문 그대로 있을 수 있지만 작업을 만들지 않는다.
- scheduler에서 Google, YouTube, Spotify, 노래방, 가사 호출을 제거했다. X poller는 다른 수집기를 시작하지 않는다.
- 독립 YouTube setlist AI 함수와 음악 integration/lyrics 모듈은 보존했다. Discord 관리 명령이 제거되어 이 기능들은 현재 최소 runtime의 진입점이 아니다. 신규 DB의 `worker_jobs`와 정규화된 음악 ID가 독립 작업 경계이며, 관리 진입점과 기존 API 소비자의 실제 전환은 5단계 API 통합 및 별도 admin-web 후속에서 연결한다.

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

5단계 전에는 실제 runtime을 활성화하지 않는다. 전환 시 구 writer를 먼저 정지하고 최신 snapshot을 다시 검증한 뒤 3단계 도구로 선택 이전을 적용한다. 이후 API/worker/bot의 설정을 신규 DB로 확정하며 과거 성공 delivery를 재전송하지 않는지 확인한다.
