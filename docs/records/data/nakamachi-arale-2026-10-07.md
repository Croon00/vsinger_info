# 나카마치 아라레 등록 및 우타와꾸 수집

2026-10-07 사용자 요청으로 신규 통합 DB에 등록했다. 구 DB는 사용하지 않았다.

- 아티스트: 仲町あられ / 나카마치 아라레, ID `1004`
- 공식 채널: https://www.youtube.com/@arale_yumemita
- 확인한 YouTube 채널 ID: `UCWfF0DB6m_t2CE3KcOOOX7g`, 외부 계정 ID `283`
- 소속은 이번 작업에서 별도로 검증하지 않아 입력하지 않았다.
- 공개 uploads 557개 전체 페이지 조회를 완료했고, 기존 제목 규칙의 우타와꾸 후보 160개를 발견했다. 후보 수를 종료 방송 수나 수집 완료 수로 해석하지 않는다.
- 원문 조사: Git 제외 `db-migration/reports/nakamachi-arale-2026-10-07/nakamachi-arale.json`
- 아티스트와 채널 owner 연결을 감사 기록과 함께 등록하고 수집을 활성화했다.
- 요청 라벨 `nakamachi-arale-utawaku-2026-10-07`로 중복 방지 `youtube_collect` 작업 160개를 등록했다. 실제 시작·종료와 채널 소유권은 기존 수집기가 검증한다.

## 최초 검증과 수집기 대기

2026-10-07 현재 HEAD의 FastAPI TestClient와 실제 신규 DB로 `/api/artists`에서 ID 1004의 등록 및 YouTube 출처를 확인했다. `/api/artists/1004/lives`는 `total=0`이다. 프론트 화면 검증 및 배포 API 확인은 수행하지 않았다.

기존 다른 YouTube 작업의 `rate_limited` 재시도 때문에 provider 전체의 새 작업 선점이 차단되어 있었다. 조사 시 재개 시각은 **2026-10-08 07:47:47 KST**였다. 이번 작업 160개는 pending이며, 수집 완료나 세트리스트 확보로 기록하지 않는다. 해당 시각은 성공 보장이 아니며 provider quota와 운영 worker 상태에 따라 재시도될 수 있다. 이번 로컬 worker는 대기 확인 후 종료했다. 배포 worker의 실제 재개는 미확인이다.

## 재실행

```powershell
python scripts/register_nakamachi_arale.py status
python scripts/register_nakamachi_arale.py verify
python scripts/register_nakamachi_arale.py worker
python scripts/register_nakamachi_arale.py broadcasts
python scripts/register_nakamachi_arale.py broadcasts --apply
```

등록·큐 재실행은 `register --apply`, `enqueue --apply`이며 기존 소유권·이름을 보존하고 같은 라벨의 작업은 중복 생성하지 않는다. 이번 전용 worker는 해당 라벨의 YouTube 수집만 실행하며 Discord·Calendar·Spotify 작업은 실행하지 않는다.

## 2026-10-07 방송 목록 저장 완료

후속 사용자 요청에 따라 현재 `.env` 키로 후보 160개의 영상 메타데이터를 다시 조회했다. 160개 모두 조회되었고, 해당 채널 소유·공개 상태·실제 방송 시작/종료·기존 우타와꾸 제목 규칙을 만족하는 **144개**를 확인했다. 나머지 16개는 해당 조건을 만족하지 않아 방송 목록으로 저장하지 않았다.

`broadcasts --apply`는 이 요청에 한정된 최대 160개 영상의 메타데이터 가져오기로, 기존 worker의 한도 대기 기록이나 작업 상태를 변경하지 않는다. provider 오류가 발생하면 저장 전 중단한다. 검증된 방송의 원문 제목·영상 ID·시작 시각·길이·설명·출처 URL을 신규 DB에 한 transaction으로 저장하고 감사 영수증을 남겼다. 기존 영상·방송·소유권·세트리스트를 덮어쓰지 않는다. 원문 snapshot은 Git 제외 `verified-broadcasts.json`에 저장했다.

현재 방송 목록은 **144개**, 세트리스트 상태는 모두 **unprocessed**다. 세트리스트용 수집 작업 160개는 기존 큐와 provider 대기 상태를 유지한다. 현재 키 자체가 quota 초과라고 단정할 근거는 없으며 이번 메타데이터 조회는 성공했다.

2026-10-07 실제 신규 DB와 현재 HEAD FastAPI TestClient 검증:

- `/api/artists`: 나카마치 아라레 ID 1004 확인
- `/api/artists/1004/lives`: total 144, 기본 페이지 12개 정상 반환
- `/api/lives/15506`: 상세 HTTP 200
- `python -m py_compile scripts/register_nakamachi_arale.py`, `git diff --check` 통과

배포 API 및 브라우저 화면 검증은 수행하지 않았다. 실제 API·DB 검증이며 fixture 테스트 결과가 아니다.

## 2026-10-07 변경 키로 세트리스트 재개

사용자가 `.env`의 YouTube 키를 변경한 뒤 재개를 요청했다. 새 프로세스에서 키를 읽고 영상·댓글 API 조회 성공을 확인했다. `resume-setlists`는 이 검증 시각보다 오래된 한도 기록만 이번 request_run의 선점에서 제외한다. 다른 요청의 상태·재시도 시각은 변경하지 않고 새 한도 오류는 그대로 준수한다. 미래 시각이나 요청 라벨 없는 복구는 거부한다.

실제 실행 결과:

- 작업 66969 성공: 방송 1개의 세트리스트 **6곡** 저장
- 작업 66970: 새 요청에서 `rate_limited`, worker 즉시 종료
- 현재 요청 작업 상태: succeeded 1, retry 1, pending 158
- 새 재시도 가능 시각: **2026-10-08 09:23:44 KST**. 이는 수집기의 24시간 재시도 설정이며 Google quota 초기화 시각을 뜻하지 않는다.
- 방송 목록 144개 유지: partial 1, unprocessed 143
- 현재 HEAD 목록·상세 API HTTP 200 검증

이번에는 과거 기록 외에 변경 키를 사용한 실제 요청에서도 새 한도 오류가 발생했다. 자동 재개나 전체 세트리스트 완료를 확인한 상태가 아니다. 재실행은 `python scripts/register_nakamachi_arale.py resume-setlists`다.

로컬 PostgreSQL 바이너리가 없어 DB fixture 테스트는 skip되었다. 네트워크 없는 파싱/추출 테스트와 복구 옵션 입력 검증을 실행했고 실제 수집·조회 검증은 별도 기록으로 구분한다.

## 2026-10-07 두 번째 키 변경 후 재개

사용자가 키를 다시 변경한 뒤 새 프로세스에서 영상·댓글 API 조회 성공을 확인하고 이번 요청의 세트리스트 수집을 재개했다. 이전 실패 작업 66970도 성공한 새 키 검증 후 이 요청에 한해 재시도 시각을 현재로 조정했다. 다른 요청의 대기 기록은 유지했다.

진행 중 snapshot에서 **세트리스트가 있는 방송 5개, 가창 41행** 저장을 실제 DB로 확인했다. 목록 144개와 방송 상세 API HTTP 200도 확인했다. 이후 작업 성공 로그가 계속 출력되어 전체 완료로 기록하지 않는다. 로컬 worker는 이 시점에 실행 중이며 새 실패가 발생하면 중단한다.

`resume-setlists`는 앞으로도 성공한 키 검증 이전의 이번 요청 `rate_limited` 재시도 작업만 즉시 재개하며, 다른 요청·새 오류·완료 작업은 변경하지 않는다.

2026-10-07 검증: 음악 작업·YouTube 수집·세트리스트 정제 테스트 **32 passed, 57 skipped**. DB fixture는 로컬 PostgreSQL 바이너리 부재로 skip됐으며 실제 수집 결과와 구분한다.

## 2026-10-07 일시적 오류 후 중단 조건 수정

이전 실행은 세트리스트 79개·가창 734행 확보 후 작업 67074의 `RetryableJobError`에서 종료됐다. 코드가 모든 retry/failed/lease_lost 결과에 종료하도록 되어 있었기 때문이다. 사용자 요청으로 `run_setlist_queue`를 수정해 일시적 오류는 큐에 등록된 재시도 시각과 횟수를 따르고 나머지 작업을 계속 처리한다. 당장 실행 가능한 작업이 없더라도 pending/retry/running이 있으면 30초 후 다시 확인한다. 새 `rate_limited` 재시도만 즉시 종료한다.

외부 API·DB 없는 runner fixture 테스트 `tests/test_nakamachi_arale_runner.py` **2 passed**: 일시적 오류와 개별 실패 뒤 배치 계속, 대기 재확인, 새 한도 오류 발생 시 추가 선점 없이 중단을 검증했다. 수정한 로컬 worker에서 현재 키의 영상·댓글 probe 성공과 재시작을 확인했다. 전체 완료는 아직 확인하지 않았다.

## 2026-10-07 남은 방송 건너뛰기 및 이번 수집 마무리

세트리스트 확보 결과는 방송 **131개**, 가창 **1,144행**이다. 남은 13개는 수집기의 제한된 댓글 조회에서 세트리스트를 확보하지 못해 주기 재확인이 이어지고 있었다. 댓글 전체에 세트리스트가 없다고 단정하지 않는다.

사용자가 해당 13개를 건너뛰도록 요청하여 `skip-missing-setlists --apply`로 이번 request_run의 해당 방송 pending 재확인 작업 13개만 취소했다. 작업 ID 67338~67350, 취소 사유는 명시적 사용자 요청이다. 방송 목록 144개와 기존 세트리스트·댓글 원문은 보존했다. 남은 pending/retry/running은 0개이며 요청 작업 상태는 succeeded 208, cancelled 13이다. succeeded 수에는 반복 조회와 세트리스트 비대상 영상 처리가 포함되어 방송 개수를 뜻하지 않는다.

건너뛴 방송·작업 ID 목록은 Git 제외 `skipped-missing-setlists.json`에 남겼다. 이는 이번 과거 수집의 재확인 취소이며 계정의 향후 신규 방송 수집 활성 상태는 유지한다.

## 2026-10-07 소속 교정과 프로필 이미지 미리보기

사용자 요청으로 아라레(ID 1004)의 소속 표시를 `BanG Dream!`, 마치타 치마(ID 991)를 기존 `にじさんじ` 소속 항목으로 수정했다. 근거는 [아라레 공식 소개](https://bang-dream.com/artist/yumemita/nakamachi-arale/)와 [치마 공식 소개](https://www.nijisanji.jp/talents/l/chima-machita)다. 아라레는 해당 프로젝트의 夢限大みゅーたいぷ 멤버다. 이번 변경은 프론트 소속 필터에 쓰이는 agency_id 교정이며 별도 법적 소속사나 그룹 관계를 추정해 추가하지 않았다.

`python -m scripts.update_requested_affiliations --apply`로 신규 DB에 공식 근거와 이전·이후 값을 감사 기록으로 저장했다. 재실행 변경 0건을 확인했고 실제 조회 API에서 두 소속이 반환되는 것을 확인했다.

아라레의 현재 YouTube 채널 프로필 이미지를 API에서 가져와 `artifacts/nakamachi-arale-profile.jpg`에 저장하고 시각적으로 확인했다. 원본 출처는 같은 위치의 JSON에 보존했다. 이번 요청의 이미지 미리보기 파일이며 DB avatar_url이나 S3 이미지 저장 완료로 기록하지 않는다.
