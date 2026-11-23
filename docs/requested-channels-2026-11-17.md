# 요청한 두 채널 등록·수집 (2026-11-17)

사용자가 지정한 `@Yurushi_nibiiro`, `@yayamugi222/streams`를 YouTube channels API의
`forHandle`로 확인해 신규 통합 DB에 등록했다. [등록 seed](../data/seeds/requested_channels_2026_11_17.json)에
입력 URL·공식 채널 ID·이름을 보존했다. 등록 전 dry-run에서 둘 다 신규임을 확인했으며
기존 아티스트·계정·소유권을 병합하지 않았다. 한국어 이름과 소속은 추정하지 않았다.

| 아티스트 | 아티스트 ID | YouTube 계정 ID | 공개 업로드 목록 | 우타와꾸 제목 후보 | 저장 커버 | 등록 오리지널 |
| --- | --- | --- | --- | --- | --- | --- |
| 鈍色聴 / Yurushi Nibiiro | 1045 | 361 | 343 | 192 | 29 | 11 |
| 稍麦 / yayamugi | 1046 | 362 | 617 | 453 | 10 | 2 |

## 완료한 작업

- 기존 등록 도구로 아티스트·계정·owner 연결 6건을 감사 이력과 함께 생성했다.
- 두 계정의 `collection_enabled=true`를 적용했다. 활성화 영수증은 `catalog_imports.id=9903`이다.
- 커버 전용 수집기로 전체 20페이지를 처리했다. 체크포인트에서 `completed=2`,
  `paused=false`, 두 채널 모두 `done=true`를 확인했다.
- Shorts 제목 표식 20개와 추가 URL 확인 3개를 처리했다. 저장 커버는 Shorts를 포함하며,
  현재 일반 커버 조회 API에는 각각 12개·7개가 표시된다.
- 공식 MV의 설명·가창 크레딧을 검토해 영상 9개와 음원 9개를 등록했다.
  [오리지널 manifest](../migrations/catalog/requested-originals-2026-11-17.json)에 영상 메타데이터와 출처를 보존했다.
  협업·피처링의 원문 제목과 전체 설명은 신규 DB의 출처 스냅샷에 보존했다.
- 鈍色聴의 [공식 앨범 페이지](https://aekanaru.netlify.app/)에서 `あえかなる唱導`의
  6곡과 실물 발매일 2025-04-27을 확인했다. 기존에 등록한 MV 2곡을 같은 음원에 연결하고,
  별도 영상이 없는 4곡을 추가했다. 영상 게시일을 발매일로 사용하지 않았다.
  앨범 1개·음원 총 13개·공식 영상 9개·출처 및 관계를 영수증 `9904`로 저장했다.
  같은 작업을 다시 실행해 `already_applied=true`를 확인했다.
- 야야무기의 두 오리지널은 [본인이 안내한 TuneCore 명단](https://www.tunecore.co.jp/artists?id=1013194)과
  공식 MV의 설명을 확인했다. 그 명단의 `プラチナ (Cover)`는 오리지널로 등록하지 않았다.
- 이미지 작업 116·117이 성공했다. 이미지 작업 프로세스에만 `AVATAR_BUCKET=avator-image`를 적용했고,
  두 채널 통계도 갱신했다. `.env`와 전역 실행 설정은 변경하지 않았다.

오리지널 등록은 이번에 검토한 자료를 반영한 일회 작업이다. 일반 YouTube worker가
오리지널 발매를 자동 판별·등록하도록 확장한 것은 아니다.

## 진행 중인 우타와꾸 수집

제목 규칙 후보 645개를 `request_run=requested-channels-2026-11-17`로 등록하고
이번 요청만 처리하는 전용 worker를 숨김 실행했다. 실제 방송 여부·시각·소유권과
댓글 세트리스트는 기존 수집기가 확인한다. 후보 수와 작업 성공 수는 최종 방송 수가 아니다.

2026-11-17 19:31 KST snapshot에서는 방송 49개(鈍色聴 44·稍麦 5)·가창 0개,
작업 성공 51·대기 645였다. API 확인과 건수 집계 사이에도 worker가 계속 저장하므로 순간 수치는 다를 수 있다.
후속 댓글 확인 작업이 추가되므로 전체 작업 수는 초기 후보 645개보다 커질 수 있다.
초기 대기 작업 중 아직 시도하지 않은 이번 요청의 작업만 두 채널 순환 순서로 조정했다.
다른 요청·실행 중인 작업·댓글 대기 후속 작업·재시도는 변경하지 않았다.
이는 진행 중 수치이며 최종 완료 기록이 아니다.

이 worker는 로컬 PC가 켜져 있을 때 실행된다. 재부팅 자동 실행은 추가하지 않았다.
일반 수집 활성화와 과거 아카이브 전체 수집 완료는 구분한다.

## 진행 조회·재개

Git 제외 파일:

- 공개 업로드 목록과 실데이터 snapshot: `db-migration/reports/requested-channels-2026-11-17/`
- 커버 체크포인트: `.tmp/requested-channels-cover-backfill-2026-11-17.json`
- 요청 worker 로그: `.tmp/requested-channels-2026-11-17-worker.stdout.log`, 같은 이름의 `stderr.log`
- 공식 원문 영상 설명: `.tmp/requested-originals-2026-11-17.json` 및 신규 DB 출처 스냅샷

```powershell
.\.venv\Scripts\python.exe scripts/backfill_requested_utawaku.py status --request-run requested-channels-2026-11-17
```

기존 요청 worker가 종료됐는지 먼저 확인한 뒤에만 재개한다. 플래그는 현재 프로세스에 적용한다.

```powershell
$env:RUNTIME_CUTOVER_ENABLED='true'
$env:AGENT_ENABLED='true'
.\.venv\Scripts\python.exe scripts/backfill_requested_utawaku.py worker --seed data/seeds/requested_channels_2026_11_17.json --reports db-migration/reports/requested-channels-2026-11-17 --request-run requested-channels-2026-11-17
```

## 검증 범위

2026-11-17 실데이터 검증: 공식 채널 ID·이름·공개 업로드 전체 목록, 기존 등록 충돌 검사,
owner 연결·수집 활성화, 커버 전체 순회·Shorts 구분, 공식 오리지널 출처·앨범 곡 목록,
감사 영수증과 오리지널 재실행 중복 방지, 이미지 작업·통계 갱신을 확인했다.
실제 신규 DB를 사용하는 읽기 전용 세션과 실제 조회 router의 TestClient에서 두 아티스트의
상세·커버·방송·앨범 및 오리지널 탐색 응답 10개가 모두 200이었다.
이는 fixture 테스트가 아닌 실데이터·HTTP 계약 확인이며 운영 서버 배포 검증은 아니다.

수집기·API 코드는 변경하지 않았다. 구 DB·Discord·Calendar·가사 생성·번역·운영 배포는 실행하지 않았다.
