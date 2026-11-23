# 2026-09-23 운영 DB 이전 기록

2026-09-23 신규 DB에 선택한 runtime 상태를 이전했다. 기존 DB는 읽기 전용으로 조회했고 변경하지 않았다. 사용자 확인에 따라 기존 writer 중지와 Railway의 `RUNTIME_CUTOVER_ENABLED=false`, `AGENT_ENABLED=false` 적용을 전제로 시작했으나, 적용 직전 신규 DB에서는 별도 X 수집기가 계속 상태를 갱신하고 있었다. 이번 적용은 기존 신규 DB 기록을 보존하는 병합 방식으로 수행했다.

## 적용 결과

- Manifest 계약 `runtime-subset-v3`, hash `76a45d24cc71c5bfa374f91d82da9227ced77d827dd1f6a91f4acac69bdc3d9d`; receipt operation ID `cc4ebf08-f863-5186-a91f-dd74f8e2f9aa`.
- 선택 집합: collection state 125, X route 51, 원문 4,709, 기존 성공 delivery 4,628, YouTube 재개 작업 755. 신규 DB의 기존 collection state 122개와 겹쳤고 기존 원문 4개의 `raw_text`만 달랐다. 겹치는 원문의 URL·게시 시각은 같았으며 본문은 신규 DB 값을 보존했다.
- 적용 후 receipt 1개가 있고 기존 성공 delivery 4,628건이 모두 `sent`였다. 이전된 source key 누락 0, 기존 X cursor보다 후퇴한 계정 0, legacy ID map에 이전 출처·대상 기록이 남았다.
- 기존 신규 DB의 X 원문·YouTube poll 이력은 보존했다. writer가 잠금 해제 후 새 원문과 작업을 추가하므로 전체 테이블 건수는 계속 변한다. 검증 직후 전체 collection state 142, route 51, 성공 delivery 4,628이었다.
- 제외 집합: 승인된 YouTube monitor에 연결되지 않은 legacy archive 537, 이미 catalog 처리된 항목 등 YouTube work 230. X 게시글의 YouTube 링크 자동 등록, X 분류, Google 데이터 이전은 실행하지 않았다.

첫 적용 명령은 최종 종료 단계에서 DB 연결 오류를 반환했지만, 신규 DB receipt와 전체 선택 집합은 커밋돼 있었다. 같은 manifest로 재확인한 결과 `applied=false`, 동일 operation ID로 중복 쓰기 없이 완료 상태가 반환됐다. 이전 도구는 완료 receipt를 먼저 확인하고 오래 열린 legacy 읽기 트랜잭션을 적용 전에 닫도록 보완했다.

적용 트랜잭션은 약 30분 지속됐다. 이 동안 수집 writer의 DB 쓰기가 잠금 대기했으며, 커밋 뒤 다시 진행했다. 이 지연과 첫 명령의 오류 코드를 숨기지 않고 receipt·실제 건수·후속 처리 상태로 적용 결과를 판정했다.

## 운영 활성화 전 남은 확인

DB 이전 재실행이나 기존 DB 수정은 남은 작업이 아니다. 아래 항목은 수정 코드 배포와 실제 서비스 동작 검증이다.

- 신규 DB에 X 수집기가 계속 접근한다. 검증 시 X 실패 64건의 오류 유형은 `NoAccountError`였고, 계정 식별자가 잘못된 상태 2건도 있었다. 수집기 실행 위치와 twscrape 계정·쿠키의 유효성을 Railway 담당자와 확인해야 한다. 오류의 원문·인증정보는 기록하지 않았다.
- 이전된 YouTube 작업 755건은 신규 DB에 있다. 검증 중 처리 성공 수가 증가했으며, 이 진행은 실제 provider 호출이 이미 발생한다는 뜻이다. 운영 담당자는 처리량·실패·중복 저장을 지속 확인한다.
- 기존 YouTube poll 실패 9건은 `PermanentJobError`였다. 계정 ID 3, 5, 12, 41, 135, 148, 150, 152, 154의 채널 ID는 모두 유효하고 공개 API에서도 채널이 존재한다. 각 최근 업로드 목록에 다른 채널 소유 영상이 1~169개 섞여 있어 기존 poller가 채널 전체를 실패 처리했다. `app/services/youtube_collection.py`는 일반 poll에서 해당 영상만 제외하고 같은 채널 영상은 계속 처리하도록 보완했다. 이 수정은 사용자 PR·Railway 재배포 전까지 운영에 반영되지 않는다. 배포 후 해당 9개 poll을 명시적으로 재요청하거나 다음 주기를 기다려 성공을 확인한다.
- 이전된 YouTube 개별 수집 작업에서 검증 시 4건이 `PermanentJobError`로 종료됐다. 그중 3건은 공개 영상의 실제 소유 채널이 작업의 등록 계정과 달라 안전하게 저장을 거절한 경우이며 실제 소유 채널은 신규 DB에 등록되지 않았다. 나머지 1건은 현재 공개 영상·댓글 API를 다시 읽을 수 있어 원래 실패를 재현하지 못했다. 실패한 작업을 다른 계정으로 추측 이전하거나 자동 재시도하지 않는다.
- 읽기 전용 worker readiness에서 활성 YouTube 계정 69개, 활성 Spotify 계정 0개를 확인했다. 현재 Spotify 작업이 없는 것은 등록된 활성 계정만 수집한다는 범위에 맞는다. Spotify 계정을 등록·활성화한 후 명시적 작업을 요청할 때 별도로 실제 provider 검증을 한다.
- Railway의 전환 잠금 변수를 변경하지 않았다. Discord 연결 및 실제 X URL 전송 확인은 `RUNTIME_CUTOVER_ENABLED`와 `AGENT_ENABLED`의 실제 서비스별 적용 상태, 중복 실행 프로세스, Discord 토큰과 채널 접근을 확인한 뒤 진행한다.
- 조회 웹의 프록시 보완은 로컬 변경이며 사용자 PR·병합·Railway 재배포 전에는 현재 사이트에 반영되지 않는다. 사용자가 PR을 직접 처리한다.

로컬 검증(2026-09-23): 전체 백엔드 `python -m pytest -q -p no:cacheprovider` 313 passed, 이후 YouTube 혼합 소유 업로드 수정의 관련 테스트 43 passed. 웹 `npm test` 27 passed 및 `npm run build` 통과, `git diff --check` 통과. 실제 Discord URL 전송·Spotify provider 호출·배포 웹 재검증은 이 로컬 테스트에 포함되지 않는다.
