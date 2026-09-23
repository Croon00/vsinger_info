# 보완 3단계 결과 — 독립 YouTube 수집

실행일: 2026-09-23. [서비스 보완 계획](backend-service-readiness-plan.md)의 C단계다. 신규 DB의 활성 YouTube 계정 → 채널 감시 → 영상별 작업 → 댓글/세트리스트/커버 저장 → 조회 API 경로를 구현했다. 기존 `001/002` 스키마를 사용하며 운영 DB 변경·실제 provider 호출·PR 변경·Railway 배포는 수행하지 않았다.

## 실행 경로

- `integrations/youtube_catalog.py`: 유한한 timeout·페이지 수·호출 간격을 가진 YouTube 읽기 adapter와 정규 파서. 구 DB 모듈을 import하지 않는다.
- `services/youtube_collection.py`: 채널/영상 ID 검증, 방송 종료 대기, 댓글 확보, 선택적 세트리스트 추출, URL 입력 계약.
- `repositories/youtube_collection.py`: 신규 영상·아카이브·원문·가창·커버와 후속 작업을 같은 transaction에서 저장한다.
- `music_jobs.HANDLERS`: `youtube_poll`, `youtube_collect` 등록. Spotify handler는 보완 4단계 대상이다. X scheduler·Discord 봇·공개 GET에서 YouTube 작업을 시작하지 않는다.

등록·선점·수집 직전·저장 시 신규 계정의 플랫폼/고정 ID/활성/보관 상태와 작업 lease를 검사한다. provider의 channel ID가 등록 계정과 다르면 저장하지 않는다. admin-web과 관리 HTTP API는 사용하지 않는다.

## 감시와 재개

| 항목 | 코드의 동작 |
| --- | --- |
| 채널 주기 | 1일. runtime 음악 loop가 due 작업을 확인하며 X/Discord loop와 독립 실행 |
| 첫 성공 조회 | `collection_states.provider_state.youtube_baseline_at` 기록. 기준선 이전에 완료된 라이브·공개된 커버를 자동 수집하지 않음. 실패한 첫 조회는 기준선을 만들지 않음 |
| uploads 조회 | 최대 4페이지/200개. 채널 응답의 uploads playlist 사용 |
| 진행/예약 방송 | 별도 ID 목록 최대 200개 유지. 최신 uploads 목록에서 빠져도 종료 여부 재확인 |
| 완료 라이브 | 기존 유효한 노래방송 제목 규칙을 적용. 실제 시작·종료가 확인된 방송만 archive 대상이며 종료 후 24시간에 작업 예약 |
| 댓글 | 관련도 순 최대 3페이지/300개 중 timestamp 가창 후보가 2개 이상인 댓글 선택. 댓글 ID·URL·원문·확보 시각 보존 |
| 댓글 없음 | 현재 확인 작업은 완료하고 1시간 후 후속 작업을 원자 등록. 기본 `wait_count=0`, 최대 168회 후속 확인. 일반 오류 재시도 기본 5회와 별개 |
| 아직 24시간 전 | 수동 URL 요청도 동일한 대기 규칙 적용. 댓글 호출 없이 예정 시각으로 후속 작업 예약 |
| 댓글 비활성 | `comments_disabled`, 신규 archive의 `setlist_state=unavailable`. 시간 재시도 없음 |
| 조회 불가 영상 | `private_or_deleted` 근거 기록. 공개 API가 구별하지 못하는 비공개/삭제를 임의로 구분하지 않음. 제목·방송 시각을 만들어 넣지 않음 |
| 통신/429/5xx/quota | 일반 작업 retry. Retry-After 반영, quota 오류는 최소 24시간 대기. 인증/기타 영구 오류는 실패로 유지 |
| HTTP/작업 제한 | HTTP 30초, adapter 내부 요청 간 최소 1초. poll 전체 600초, 영상 수집 180초. lease는 실행기가 갱신 |

채널은 최신 200개를 감시하며 과거 전체를 자동 순회하지 않는다. 관측 창 밖 누락 가능성이 감지되면 `youtube_poll_gap=true`를 보존한다. 이 값은 이후 정상 조회만으로 지워지지 않으며 명시적 범위 조사/backfill 후 별도 확인해야 한다. `youtube_window_truncated`는 마지막 응답의 페이지 상한 여부다. 감시 중인 ID도 200개 상한을 넘으면 gap을 표시한다. 실제 운영 quota·계정 수에 맞춘 주기 확정은 배포 전 검증 대상이다.

대기 중에는 영상/출처와 후속 작업을 저장하고, 세트리스트 확보 또는 영구 미확보 판정 때 archive를 생성한다. 따라서 대기 중 영상은 라이브 목록에 먼저 노출되지 않는다. 프로세스 재시작은 DB의 예약 작업을 이어받는다. 성공한 이전 확인 작업이 아니라 현재 pending/retry 후속 작업 ID를 취소해야 대기를 중단할 수 있다.

## 저장과 기존 자료 보존

- 영상은 `(platform, platform_video_id)`로 식별하고 신규 행에 `source_account_id`, 제목, 공개 시각, 길이, 공개 상태를 저장한다. 기존 영상의 수동 메타데이터를 자동 갱신하지 않으며 새 관측값은 원문 문서의 메타데이터에 남긴다.
- `broadcast_at`에는 실제 방송 시작만 사용한다. 예정 시각이나 업로드 시각을 복사하지 않는다.
- 새 archive는 계정의 기존 `owner` 관계를 진행자(`archive_artists.host`)로 연결한다. 단일 소유자가 있을 때만 대표 표시 아티스트를 설정한다. 각 곡의 가창자로 자동 복사하지 않는다.
- 새 가창은 `performances`에 순서·초 단위 시작·원문 timestamp·곡명·명시된 원곡자·문서 ID를 저장한다. `song_id`와 불확실한 `performance_artists`는 비워 둔다. 공동 가창 표기는 댓글/원문 행에 보존한다. 이름만으로 작품·인물을 생성하거나 병합하지 않는다.
- 기존 정규 파싱의 범위 종료 시각·곡 번호·인용부호·점수 제거를 유지하고 잘못된 시간·중복 시작 시각·비가창 행을 제외한다. 선택적 기존 LLM 추출에는 댓글 최대 20,000자를 보내며 원문에 없는 timestamp·제목·원곡자를 채택하지 않는다. LLM 불가 시 정규 파싱을 사용한다.
- 자동 추출은 검수 완료를 뜻하지 않으므로 새 세트리스트는 `partial`이다. 새 번역·독음·가사·노래방 수집은 호출하지 않는다.
- `source_documents`에는 원문과 외부 ID/URL, 영상 메타데이터, 추출 방식/모델·버전, 추출 행과 처리 사유를 보존한다. hash는 kind·외부 ID·원문·메타데이터의 정렬 JSON으로 계산하며 확보 시각/검토 상태는 hash에서 제외한다. 같은 원문·추출 결과의 재처리는 중복 문서를 만들지 않는다.
- 기존 archive/가창/인물 연결은 삭제·교체하지 않는다. 변경된 댓글·추출 버전은 `review_candidate` 문서로 남긴다. 수집 도중 영상/archive/cover version이 달라졌거나 보관되면 `version_conflict` 문서를 남기고 적용을 보류한다. 검토 후보는 내부 보존 계약이며 승인 UI/API는 구현하지 않았다.
- 커버는 일반 업로드 중 기존 제목/설명 키워드를 충족하고 라이브/예약 영상이 아닌 경우에 `videos/covers`로 저장한다. 작품·가창자를 추측하지 않고 설명과 검토 후보를 남긴다. 기존 `cover_artists`와 작품 연결은 보존한다. 별도 커버 조회 화면/API는 이번 단계에 추가하지 않는다.

## admin-web 없는 입력

기본 `validate`, `enqueue`, `status`, `cancel`, `run-once` 명령은 [2단계 계약](backend-service-step-2-jobs.md)을 따른다. URL은 지정한 활성 계정의 영상인지 실제 수집 때 검증한다. 다음은 입력 검증만 하며 DB나 provider를 호출하지 않는 예다.

```powershell
.\.venv\Scripts\python.exe scripts/music_jobs.py youtube-url --account-id 1 --channel-id UCaaaaaaaaaaaaaaaaaaaaaa --url https://youtu.be/abcdefghijk --validate-only
```

실제 등록은 `--validate-only`를 빼며 cutover guard를 통과해야 한다. `--purpose cover`로 커버를 지정하고 명시적 재수집은 새로운 `--request-run`을 사용한다. 등록만으로 즉시 provider를 호출하지 않으며 worker 실행은 `RUNTIME_CUTOVER_ENABLED`와 `AGENT_ENABLED`가 모두 필요하다.

과거 수집은 승인한 계정과 **영상 ID 최대 200개**를 명시한 `youtube_poll` 요청만 지원한다. 기간만 주고 무제한으로 채널을 훑는 backfill은 제공하지 않는다. 기존 `enqueue --request` 입력 예:

```json
{
  "job_type": "youtube_poll",
  "external_account_id": 1,
  "payload": {
    "channel_id": "UCaaaaaaaaaaaaaaaaaaaaaa",
    "request_run": "approved-batch-1",
    "backfill_video_ids": ["abcdefghijk"]
  }
}
```

backfill은 일반 감시 기준선/주기를 바꾸지 않는다. 지정 영상이 조회되지 않거나 다른 채널이면 해당 요청을 실패로 남기며 조용히 범위를 축소하지 않는다. 가용한 영상만 따로 검토해 요청할 수 있다. 이 문서 작성 중 실제 URL 등록/backfill은 실행하지 않았다.

## 검증과 다음 단계

2026-09-23 전체 `python -m pytest -q -p no:cacheprovider`: **270 passed**, 346 warnings, 116.82초. 경고는 기존 FastAPI/Starlette와 Python의 deprecated API 사용이다. 일회용 로컬 PostgreSQL과 가짜 provider/LLM을 사용했다. 마지막 제목 필터·감시 gap 보존 보완 뒤 YouTube 관련 테스트를 다시 실행해 **41 passed**, 51 warnings, 16.75초를 확인했다. URL 명령의 `--validate-only`와 `git diff --check`도 통과했다.

신규 테스트는 채널 기준선·진행 방송 추적·종료+24시간·댓글 지연과 대기 한도·quota/timeout/영구 오류·중복 원문·수동 수정/공동 가창 보존·version 충돌·모호한 곡·커버 경계·bounded pagination·URL 검증과 실제 `/api/artists/{id}/lives`, `/api/lives/{id}`, `/api/search` 응답을 확인한다. 기존 작업 실행기의 lease/취소/rollback 검증도 함께 통과했다. 신규 모듈의 legacy·X·제외 수집기 의존성 금지 검사와 기존 X→YouTube 금지 회귀 테스트를 유지한다.

다음은 **보완 4단계: 등록된 Spotify 계정 수집·연결**이다. 기존 YouTube pending archive 선택·이전 payload/중복 key 정합성은 보완 5단계, 최종 서비스 통합·실제 provider·PR/Railway 전환은 보완 6단계에 남아 있다. 이들 완료 전 전체 운영 준비를 완료로 판정하지 않는다. 3단계 완료 당시에는 Spotify handler가 없어 worker 활성 상태의 전체 `/ready`가 준비 미완료를 반환했다. 이후 [4단계](backend-service-step-4-spotify.md)에서 등록 계정 handler를 연결했다.
