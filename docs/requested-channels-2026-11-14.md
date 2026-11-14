# 요청한 네 채널 등록·수집 (2026-11-14)

사용자가 지정한 네 채널을 YouTube channels API의 `forHandle`로 확인하고 신규 통합 DB에 등록했다.
입력과 공식 출처는 [seed](../data/seeds/requested_channels_2026_11_14.json)에 보존했다.
기존 채널 ID·이름·별칭을 확인한 결과 네 명 모두 미등록이었으며 기존 인물/소유권을 병합하지 않았다.

| 아티스트 | 아티스트 ID | YouTube 계정 ID | 확인한 공개 업로드 | 노래 방송 제목 후보 | 저장한 커버 |
| --- | --- | --- | --- | --- | --- |
| 音ノ瀬らこ / Otonose Raco | 1041 | 357 | 524 | 133 | 190 |
| 苺咲べりぃ / Maisaki Berry | 1042 | 358 | 1,185 | 818 | 25 |
| 碧生ねの / Neonoah | 1043 | 359 | 342 | 199 | 7 |
| 翠雨しの | 1044 | 360 | 297 | 158 | 101 |
| 합계 | | | 2,348 | 1,308 | 323 |

이름은 공식 채널/자기소개 표기를 사용했다. 확인된 한국어 이름이 없어 `name_ko`는 null로 유지했다.
音ノ瀬らこ는 [공식 미리프로 명단](https://milpr.com/talents), 碧生ねの는
[공식 차레파 소속 안내](https://challepa.jp/topics/detail/6a0c2a3a-94cb-46a7-b92d-7832a46e5c8d)에 따라 소속을 연결했다.
나머지 두 명은 소속을 추정하지 않고 비워두었다.

## 완료한 작업

- 기존 `register_requested_vsingers.py`로 읽기 전용 확인 후 등록. 감사 영수증 `catalog_imports.id=9363`, 변경 13건(아티스트 4·계정 4·owner 연결 4·소속 1).
- 계정 357–360의 `collection_enabled=true` 전환 및 감사 기록. 기존 전역 runtime/agent 설정은 바꾸지 않았다.
- 네 채널의 구독자 수·채널 생성일 통계를 수집했다. YouTube 통계 영상 수와 uploads 목록 수는 다를 수 있으며 같은 수치로 취급하지 않는다.
- 프로필 이미지 작업 112–115가 성공했고, API에 이미지 URL이 반영됐으며 공개 WebP 응답 4개가 모두 200이었다.
- 커버 전용 수집기가 네 채널 전체 48페이지 처리를 완료했다. 커버 323개를 저장했고 다른 채널 소유 영상은 기존 규칙대로 제외했다.
- 같은 seed로 등록 dry-run을 다시 실행해 네 명 모두 `reuse`임을 확인했다.

이미지 작업의 최초 자동 작업 108–111은 잘못된 기본 버킷 `artists-avator`에서 `NoSuchBucket`을 기록했다.
기존 문서의 `avator-image` 버킷 접근을 확인하고 **이미지 작업 프로세스에만** `AVATAR_BUCKET=avator-image`를 지정해 완료했다.
기존 자동 작업은 이미지가 생긴 뒤 `skipped_existing`으로 정리됐으며 버킷 생성·권한/.env 변경은 하지 않았다.

## 진행 중인 작업

2026-11-15 00:00 KST 무렵의 실데이터 snapshot에서는 방송 45개·가창 198개를 확인했다
(音ノ瀬らこ 방송 26/가창 0, 苺咲べりぃ 7/100, 碧生ねの 7/98, 翠雨しの 5/0).
요청 작업은 성공 48·대기 1,296이었으며 후속 작업이 추가된 진행 중 수치다.
기계 판독용 snapshot은 조사 보고서 디렉터리의 `collection-progress.json`에 보존했다.

노래 방송 제목 후보 1,308개를 `request_run=requested-channels-2026-11-14`로 등록하고 이번 요청만 처리하는 worker를 실행했다.
공개 여부·실제 방송 시작/종료·채널 소유권·댓글 세트리스트는 기존 수집기가 검증한다.
후보 수나 작업 성공 수를 최종 방송/세트리스트 수로 해석하지 않는다. 댓글 대기·판정 재시도는 별도 후속 작업이 생길 수 있다.
새 초기 대기 작업만 채널별 순환 순서로 조정해 네 명의 첫 결과가 고르게 나오도록 했고 기존 재시도·실행 중/다른 요청은 변경하지 않았다.

커버 수는 원본 저장 수다. Shorts 구분 작업을 계정 357–360에 한정해 실행했으며,
제목 표식 21개와 짧은 영상 URL 확인 267개가 대상이다. 진행 중에는 조회 가능한 일반 커버 수가 바뀔 수 있다.
수집된 방송·커버가 네 아티스트별 API에서 모두 200으로 조회되는 것을 확인했다.
장시간 작업은 로컬 PC가 실행 중일 때 계속되며 재부팅 후 자동 시작을 추가하지 않았다.

## 이어서 실행·진행 조회

조사 보고서는 Git 제외 `db-migration/reports/requested-channels-2026-11-14/`,
커버 체크포인트는 `.tmp/requested-channels-cover-backfill-2026-11-14.json`에 있다.
커버는 모든 채널의 `done=true`, `completed=4`, `paused=false`를 확인했다.

```powershell
.\.venv\Scripts\python.exe scripts/backfill_requested_utawaku.py status --request-run requested-channels-2026-11-14
```

기존 요청 worker가 종료된 경우에만 이번 요청을 재개한다. 플래그는 현재 프로세스에만 적용한다.

```powershell
$env:RUNTIME_CUTOVER_ENABLED='true'
$env:AGENT_ENABLED='true'
.\.venv\Scripts\python.exe scripts/backfill_requested_utawaku.py worker --seed data/seeds/requested_channels_2026_11_14.json --reports db-migration/reports/requested-channels-2026-11-14 --request-run requested-channels-2026-11-14
```

Shorts 확인을 재개하려면 같은 계정 범위를 사용한다. 이미 확인한 결과는 기존 정책에 따라 유지한다.

```powershell
.\.venv\Scripts\python.exe scripts/classify_youtube_cover_formats.py --account-id 357 --account-id 358 --account-id 359 --account-id 360
```

검증 범위: 실제 provider 채널·공개 업로드 목록·등록과 owner·수집 활성화·통계·프로필 공개 응답·커버 전체 순회·조회 API.
등록/수집 도구의 코드는 변경하지 않았으며 fixture 테스트 결과와 구분한다.
구 DB·Discord·Calendar·가사 생성/번역·운영 배포는 실행하지 않았다.
