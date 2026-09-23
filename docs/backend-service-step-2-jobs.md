# 보완 2단계 결과 — 독립 작업 실행기

실행일: 2026-09-22. [보완 개발 계획](backend-service-readiness-plan.md)의 B단계다. admin-web·관리 HTTP API 없이 작업 등록, 상태 조회, 취소, 실행, 재시작 복구를 구현했다. 기존 신규 DB의 `worker_jobs`와 `collection_states`를 사용하며 schema 변경은 없다.

**범용 실행기는 구현됐고, 실제 YouTube·Spotify 수집 handler는 각각 3·4단계에서 연결한다.** 2단계 완료 당시 registry는 비어 있었다. 이후 [3단계](backend-service-step-3-youtube.md)에서 YouTube handler, [4단계](backend-service-step-4-spotify.md)에서 등록된 Spotify 계정 handler를 연결했다. 미구현 handler의 작업을 선점하거나 성공 처리하지 않으며 시도 횟수도 소모하지 않는다. 기존 YouTube 이전 payload를 새 계약으로 변환하는 일은 선택 이전 보완 단계에 남아 있다.

## 작업 계약

| 작업 | 필수 payload | 실행 범위 |
| --- | --- | --- |
| `youtube_poll` | `channel_id`: UC로 시작하는 고정 채널 ID | 등록된 활성 YouTube 계정의 채널 조회 |
| `youtube_collect` | `channel_id`, `youtube_video_id`, `purpose`(archive/cover), `extraction_version` | 영상별 수집. 선택적 `video_id`는 신규 DB의 영상 PK |
| `spotify_collect` | `spotify_artist_id`, `link_youtube` | 등록된 활성 Spotify 계정의 명시적 수집/연결 |

모든 payload는 `version=1`, `request_run=initial`이 기본값이다. 알 수 없는 필드는 거부한다. 상위 요청에는 `job_type`, `external_account_id`, 선택적 `video_id`, `payload`, `max_attempts`가 있다. 신규 계정 PK와 provider 고정 ID는 각각 검증하며 서로 대신 사용하지 않는다.

등록·실행·결과 저장 때 `external_accounts`의 플랫폼·고정 ID·활성·보관 상태를 확인한다. 계정이 없거나 ID가 다르면 자동 검색·생성·연결하지 않는다. 특히 Spotify는 등록된 계정 범위 밖으로 확장하지 않는다. 영상 PK가 있으면 실제 외부 영상 ID와 계정 관계도 확인한다.

작업 key는 종류·신규 계정 ID·정규화한 payload hash로 계산한다. 동일 요청은 기존 작업 ID를 반환하며 성공/실패 작업을 자동 재개하지 않는다. 명시적 재수집은 새로운 `request_run`으로 구분한다. 같은 key에 다른 영상 참조나 시도 횟수를 덮어쓰지 않는다.

노래방·가사 작업 종류는 기존 schema에 남아 있지만 이번 실행기는 등록·선점·실행·취소 대상으로 사용하지 않는다. X도 이 큐로 옮기지 않는다.

## 실행·복구

- 한 번에 한 작업을 `FOR UPDATE SKIP LOCKED`로 선점하고, 고유 claim token·시도 횟수·lease를 기록한다.
- provider별 advisory transaction lock과 실행 중 작업 검사로 DB 전체에서 같은 provider의 동시 작업을 1개로 제한한다. 서로 다른 provider는 병행할 수 있다. 기본 작업 간 최소 간격은 1초다. 개별 handler 안의 HTTP 호출량·API quota 조절은 3·4단계 provider adapter의 책임이다.
- provider 조회는 transaction 밖에서 비동기로 수행한다. handler의 `collect`는 외부 읽기만 수행하고 DB 저장·메시지 전송 등 부작용을 만들지 않는 계약이다.
- 수집 결과는 `persist(session, ...)`로 전달한다. 계정/claim을 다시 검사하고 도메인 저장과 `succeeded`를 같은 transaction에서 commit한다. 중간 오류는 도메인 저장도 rollback한다.
- 기본 lease 90초, heartbeat 30초, handler timeout 120초다. 긴 수집 중에도 lease를 갱신한다. 결과 저장 전에 한 번 더 갱신하고 유효한 claim만 반영한다.
- timeout·명시적 일시 오류·일시 DB 연결 장애는 시도 한도 안에서 backoff한다. provider의 `retry_after`보다 먼저 재시도하지 않는다. payload/계정 계약 위반·영구 오류는 failed로 남긴다.
- worker 종료는 진행 중 수집을 취소하고 재개 가능한 retry로 해제한다. 강제 종료는 lease 만료 후 회수한다. 명시적 cancel은 terminal 상태로 기록하며 heartbeat가 수집 취소를 전달한다. 취소/소유권 상실 뒤의 결과는 저장하지 않는다.
- DB 작업은 별도 thread의 짧은 session에서 수행해 수집 transaction이 X/Discord event loop를 점유하지 않게 한다. 종료 시 진행 중 DB transaction은 마무리한 뒤 취소를 전달한다.
- 로그와 작업 오류에는 예외 종류만 기록한다. provider 응답·payload 전체·토큰·DB URL은 출력하지 않는다.

## 주기와 runtime 연결

`python -m app.runtime`에서 기존 `RUNTIME_CUTOVER_ENABLED`와 `AGENT_ENABLED`가 모두 true일 때 음악 worker loop를 시작한다. X/Discord loop와 독립된 task이며 새 on/off 환경변수는 없다. 각 provider loop는 5초마다 실행 가능한 작업을 확인한다.

YouTube poll handler가 등록된 경우에만 `collection_states.next_poll_at`에 따라 채널 감시 작업을 만든다. 대기/실행/재시도 중인 poll을 중복 등록하지 않고, 성공 시 마지막 조회·다음 주기를 갱신한다. 기본 간격 1일은 향후 handler에서 명시한다. Spotify는 이 단계에서 전체 계정 주기 작업을 자동 생성하지 않는다.

현재 registry가 비어 있어 실제 provider는 호출하지 않으며 heartbeat 상태는 `waiting_for_handler`다. handler 등록은 코드에서만 수행하고 요청 파일로 실행 코드를 지정할 수 없다.

## 로컬 명령

프로젝트 루트에서 실행한다. `validate`는 파일의 계약만 확인하며 DB에 연결하지 않는다. `status`/`readiness`는 신규 DB 조회만 한다. `enqueue`/`cancel`은 전환 잠금이 해제돼야 하고 `run-once`는 AGENT_ENABLED도 true여야 한다. 실제 전환 전에는 검증 목적으로 운영 DB 작업을 등록하지 않는다.

```powershell
.\.venv\Scripts\python.exe scripts/music_jobs.py --help
.\.venv\Scripts\python.exe scripts/music_jobs.py validate --request path/to/request.json
.\.venv\Scripts\python.exe scripts/music_jobs.py enqueue --request path/to/request.json
.\.venv\Scripts\python.exe scripts/music_jobs.py status --id 123
.\.venv\Scripts\python.exe scripts/music_jobs.py cancel --id 123
.\.venv\Scripts\python.exe scripts/music_jobs.py readiness
.\.venv\Scripts\python.exe scripts/music_jobs.py run-once
```

요청 예시의 계정·외부 ID는 fixture이며 실제 계정으로 바꾸어 검증해야 한다.

```json
{
  "job_type": "youtube_collect",
  "external_account_id": 123,
  "payload": {
    "version": 1,
    "channel_id": "UCaaaaaaaaaaaaaaaaaaaaaa",
    "youtube_video_id": "abcdefghijk",
    "purpose": "archive",
    "extraction_version": "1",
    "request_run": "initial"
  }
}
```

상태 조회는 payload나 비밀값 없이 ID·상태·시도 횟수·다음 실행·lease 만료·오류 종류를 반환한다. 이 명령은 계정/route CRUD나 임시 관리 앱을 제공하지 않는다.

## 준비 상태

- `/health`: 기존 프로세스 liveness 유지. DB에 연결하지 않는다.
- `/ready`: DB identity/revision을 검사하고 큐 집계, 현재 프로세스 worker heartbeat·마지막 성공/실패, 미구현 handler를 반환한다. instance UUID·DB 주소·payload는 노출하지 않는다. 작업을 등록/선점하거나 provider를 호출하지 않는다.
- API-only 모드는 DB 검증 성공 시 ready다. worker 활성 모드는 필수 handler와 두 provider의 최근 heartbeat까지 요구한다. 현재처럼 handler가 미구현이면 503과 `ready=false`가 정상이다. 전체 수집 기능을 완성하기 전 `/ready`를 Railway의 필수 배포 healthcheck로 지정하지 않는다.
- CLI `readiness`는 대상 instance ID와 DB의 실행 중 lease·지연 작업·마지막 성공/실패를 표시한다. heartbeat는 프로세스 내부 정보이므로 별도 CLI 프로세스는 서버의 idle heartbeat를 알 수 없다. 실행 중 서버의 `/ready`와 함께 확인한다. DB lease와 terminal 결과는 재시작 후에도 남는다.

## 검증과 다음 단계

2026-09-22 전체 백엔드 `pytest -q -p no:cacheprovider`: **229 passed, 318 warnings**. 기존 198건에 음악 작업 검증 31건을 추가했고 runtime 잠금 테스트에 독립 음악 loop를 반영했다. warnings는 기존 Python/FastAPI/Starlette deprecation이다. 로컬 명령의 --help도 확인했다.

격리된 로컬 PostgreSQL·모의 handler만 사용했다. 핵심 검증은 중복 요청, 원자 저장/rollback, 등록되지 않은 Spotify 차단, 만료 lease 회수, stale owner 차단, heartbeat, 실행 중 cancel, 종료 후 재개, timeout/시도 한도, provider별 동시 실행 제한, 읽기 전용 readiness, 기존 runtime 잠금이다.

실제 운영 DB·provider·Discord·PR·Railway는 변경하지 않는다. 다음 단계는 **3단계 YouTube 채널 감시·아카이브·세트리스트·커버 handler와 신규 DB 저장 구현**이다. 이때도 admin-web·노래방·가사·번역·독음은 연결하지 않는다.
