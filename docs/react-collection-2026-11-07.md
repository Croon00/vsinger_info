# Re:AcT 추가 채널 영상 수집 (2026-11-07)

[앞선 등록](react-members-2026-11-07.md)에서 새로 추가한 16개 채널을 대상으로
사용자가 과거 영상 수집과 이후 수집 활성화를 요청했다.
기존에 수집 중이던 칸나기 안나·안야 쿠모리·우스와 스우·시시가미 레오나는
이번 과거 수집 대상에서 제외하고 기존 설정을 유지했다.

## 적용 범위

- [수집 seed](../data/seeds/react_collection_2026_11_07.json)의 16명.
- 아티스트 1024–1039, 공식 YouTube 계정 340–355.
- `collection_enabled=true`로 전환. 감사 영수증 `catalog_imports.id=7780`.
- 16개 채널의 통계를 갱신했고, 공개 업로드 전체 목록 9,661개를 확인했다.
- 목록에서 기존 제목 규칙에 해당하는 노래 방송 후보 2,021개를
  `request_run=react-collection-2026-11-07`로 등록했다.
  먼저 등록한 250개를 포함해 초기 작업의 영상 ID는 중복 없이 2,021개다.
  후보는 실제 방송 날짜·소유권·댓글을 기존 수집기가 확인하며,
  작업 성공을 모든 후보의 세트리스트 추출 성공으로 해석하지 않는다.
- 커버는 기존 전용 수집기로 전체 업로드를 순회한다. 계정 소유권과
  기존 출처를 보존하며 같은 영상·커버를 중복 생성하지 않는다.

## 확인한 진행 상태

2026-11-07 실데이터 검증 시 커버 93개, 방송 13개, 가창 132개를 확인했다.
커버 전체 순회는 3개 채널 완료, 4번째 채널 처리 중이었다.
요청 라벨의 작업 상태는 성공 13개, 실행 중 1개, 대기 2,012개였으며
대기에는 댓글 확인·세트리스트 판정용 후속 작업이 포함된다.
이 수치는 진행 중 snapshot이며 최종 수집 결과가 아니다.
Shorts 판정 전 저장 건수이므로 커버 93개가 모두 화면에 표시된다는 뜻도 아니다.

노래 방송 전용 worker의 실제 성공 로그, 커버 페이지별 저장 로그,
16개 계정의 활성 상태와 초기 영상 ID 중복 부재를 확인했다.
코드 변경은 없으며 fixture 테스트 실행 기록은 아니다.
기존 DB·Discord·Calendar는 이번 실행에 사용하지 않았다.
로컬 `.env`의 실행 플래그는 변경하지 않고 노래 방송 worker의 프로세스 환경에만 적용했다.

## 백그라운드 처리와 로그

노래 방송 worker는 이번 요청 라벨만 계속 처리하도록 숨김 실행했다.
커버 수집은 체크포인트로 이어받으며, 후속 숨김 프로세스가 현재 수집 종료를
기다린 뒤 같은 체크포인트로 완료를 확인하고 16개 계정의 Shorts 판정을 실행한다.
이 로컬 프로세스들은 PC가 실행 중일 때 동작하며 재부팅 후 자동 재시작은 등록하지 않았다.
운영 음악 worker도 활성 계정의 이후 poll 및 저장된 작업을 처리할 수 있다.

Git 제외 파일:

- 공개 목록·검증 snapshot: `db-migration/reports/react-collection-2026-11-07/`
- 커버 체크포인트: `.tmp/react-cover-backfill-2026-11-07.json`
- 노래 방송 로그: `.tmp/react-collection-2026-11-07-worker.stdout.log`, 같은 이름의 `stderr.log`
- 커버 완료 확인·Shorts 후속 로그: `.tmp/react-collection-2026-11-07-followup.stdout.log`, 같은 이름의 `stderr.log`
- 이번 실행의 후속 스크립트: `.tmp/react-collection-2026-11-07-followup.ps1`

노래 방송 진행 조회:

```powershell
.\.venv\Scripts\python.exe scripts/backfill_requested_utawaku.py status --request-run react-collection-2026-11-07
```

PC 재시작 등으로 전용 worker가 종료되면 이번 요청만 재개할 수 있다.
이미 실행 중인 전용 worker가 없는지 먼저 확인한다.

```powershell
$env:RUNTIME_CUTOVER_ENABLED='true'
$env:AGENT_ENABLED='true'
.\.venv\Scripts\python.exe scripts/backfill_requested_utawaku.py worker --request-run react-collection-2026-11-07
```

커버·Shorts 후속 스크립트는 프로젝트 루트에서 다음과 같이 재개한다.
동일 커버 수집이 실행 중이면 기존 프로세스가 끝난 뒤 실행한다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .tmp/react-collection-2026-11-07-followup.ps1
```
