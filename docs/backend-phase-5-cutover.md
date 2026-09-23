# 5단계 운영 전환

## 현재 상태

신규 DB 통합 조회 API와 X 수집·Discord 전송의 1차 runtime을 구현했다. 정식 조회 경로는 `/api`이며 `/api/v2`는 숨김 호환 경로로 유지한다. 기존 쓰기 API와 Google·음악 provider router는 운영 앱에 마운트하지 않는다.

**선택한 runtime 상태의 신규 DB 이전은 완료했고 운영 활성화는 미완료다.** 실제 건수·영수증·현재 장애는 [2026-09-23 운영 DB 이전 기록](backend-cutover-2026-09-23.md)에 있다. [서비스 검증과 보완 개발 계획](backend-service-readiness-plan.md)의 A~F 로컬 개발·통합 검증을 마쳤지만 X provider 오류, Discord 연결·전송과 실제 운영 검증이 남았다.

PR 대기만으로 현재 서버가 바뀌지는 않는다. 다만 같은 Railway 서비스를 새 코드로 교체하면 구 프로세스는 종료되며, `RUNTIME_CUTOVER_ENABLED=false`인 새 프로세스는 API만 실행한다. 따라서 배포 후에도 기존 수집·봇이 계속 가동된다고 해석하면 안 된다. 잠금 해제 시점까지의 중단 시간을 전환 일정에 포함한다.

현재 코드의 신규 연결 이름은 `DATABASE_URL`이다. 이전 원본은 명시적 `LEGACY_DATABASE_URL`을 받는 읽기 전용 도구에서만 사용한다. Railway의 서비스별 실제 변수·실행 프로세스는 관리자 확인이 남아 있다. `NEW_DATABASE_URL`이 남으면 새 프로세스는 충돌로 시작을 거부한다. [5단계 변수표](backend-service-step-5-migration.md)를 따른다.

선택적 `NEW_DATABASE_INSTANCE_ID`는 대상 DB의 `SELECT id FROM public.catalog_instance` 결과다. 현재 이름 통일 결정을 유지한다. 미설정이어도 schema version/revision 검사는 유지되며 `NEW_CATALOG_INSTANCE_ID`는 사용하지 않는다. 이미지·YouTube·Spotify·LLM·X·Discord 설정도 실행 경로별로 확인한다. DB 주소만으로 모든 기능의 준비가 끝나지 않는다.

## 배포 전 준비

- 보완 계획 A~F의 로컬 검증을 완료하고 최종 schema revision, 대상 instance, 선택 이전 도구 버전을 고정한다.
- 사용자가 직접 PR을 열어 변경 내용·검증·복구 방법을 검토한 뒤 병합/배포 일정을 정한다. 이전 PR #1은 병합 없이 닫혔다. 이 문서의 작성은 PR 변경이나 배포 실행을 뜻하지 않는다.
- Railway 관리자가 기존 DB writer 목록, 배포 서비스/replica, 실제 환경변수, twscrape 계정 저장소의 지속성, Discord 채널 접근과 provider 자격 증명을 확인한다.
- 조회 웹의 운영 `/api` 프록시·인증·SPA fallback·이미지 접근을 검증한다. Vite 개발 프록시와 `/health` 성공만으로 운영 준비를 판정하지 않는다.
- 신규 DB와 호환되는 API-only 복구 배포본을 지정한다. 임의의 구 배포본 재가동을 복구 절차로 삼지 않는다.

## 전환 순서

3~4의 최종 manifest 작성·DB 적용은 [이전 기록](backend-cutover-2026-09-23.md)대로 완료했다. 이를 반복하지 않는다. 현재 남은 일은 신규 DB writer의 실행 위치 확인과 5~8의 배포·실제 동작 검증이다.

1. 새 배포 설정을 `RUNTIME_CUTOVER_ENABLED=false`, `AGENT_ENABLED=false`로 준비한다. 기존 환경의 AGENT_ENABLED=true가 그대로 승계되지 않게 명시한다.
2. 기존 Railway 및 로컬의 구 DB writer를 실행 설정에서 정지한다. 구 DB의 활성 플래그·권한은 변경하지 않는다.
3. 기존 DB를 읽기 전용으로 최종 dry-run하고 계정 version·cursor·route·성공 이력·YouTube 대기 작업의 manifest를 확정한다.
4. 최종 도구로 승인된 manifest를 신규 DB에 적용한다. migration receipt, 선택/제외 집합, 참조, pending/성공 상태를 확인한다.
5. 잠긴 새 배포본의 DB identity/revision, 조회 API·웹·이미지 접속을 확인한다. 신규 DB 이외 연결 시도가 없어야 한다.
6. `AGENT_ENABLED=false`를 유지한 채 `RUNTIME_CUTOVER_ENABLED=true`로 Discord 연결만 확인한다. 현재 코드에서 이 조합은 delivery 실행도 시작하지 않는다는 점을 구분한다. 원격의 과거 slash command는 해당 애플리케이션의 global/guild 범위를 확인해 정리한다.
7. 첫 실행 시각과 provider 한도를 확인한 뒤 보완된 수집/전송 실행기를 활성화한다. 명세에서 정한 제한된 대상의 신규 글·영상부터 확인하고 전체 대상으로 확대한다. 기존 loop는 AGENT_ENABLED=true와 AGENT_RUN_ON_START/주기의 영향을 받으므로 최종 코드의 실행 계약을 확인한다.
8. X 원문·URL 전송, YouTube 발견·댓글 대기·세트리스트 저장, 등록된 Spotify 계정의 명시적 작업을 실제 운영 경로에서 검증한다. 실제 호출/전송 기록은 로컬 mock 결과와 구분한다.

2026-09-23 선택 이전은 이미 적용했다. 동일 manifest를 다시 적용하지 말고 receipt를 확인한다. 현재 신규 DB writer가 실제로 동작하므로 이후 검증은 DB 건수 증가와 이전 건수를 구분한다.

## 확인 항목

- `/health`는 프로세스 상태로만 확인하고 `/ready`의 DB·음악 handler·heartbeat 준비 상태 및 `/api/artists` 조회를 확인한다. 실제 수집 handler 구현 전 worker가 활성화된 /ready는 503이다.
- `/api/v2/artists` 호환 경로가 같은 응답을 반환한다.
- 기존 쓰기 API와 Google/provider route가 노출되지 않는다.
- 봇에 관리 명령이 없고 Discord에 남아 있던 원격 명령도 제거됐다.
- X 첫 조회의 과거 글과 기존 성공 delivery를 다시 보내지 않으며 원문·route별 delivery가 중복 생성되지 않는다. 결과 불명확 건은 격리한다.
- X 분류와 X 본문의 YouTube 링크 자동 등록이 호출되지 않는다.
- 활성 YouTube 계정과 이전된 댓글 대기 작업이 처리되고 신규 영상·가창·출처가 조회 API에 나타난다.
- 등록된 Spotify 계정의 저장이 신규 모델과 일치하며 승인된 수동 자료를 덮어쓰지 않는다.
- Google 호출·기존 DB 쓰기·구 SQL 실행이 없고 각 worker의 마지막 성공·지연·실패를 확인할 수 있다.

## 롤백

문제가 생기면 현재 프로세스를 중지하거나 `RUNTIME_CUTOVER_ENABLED=false`, `AGENT_ENABLED=false`로 재배포해 새 작업을 차단한다. 환경변수 수정은 실행 중 Python 객체에 즉시 반영되는 스위치가 아니므로 프로세스 종료/재시작까지 확인한다. 진행 중 전송의 결과는 receipt·message ID·lease 기준으로 확인하고 불명확한 건 자동 재전송하지 않는다.

API 복구는 사전에 지정한 **신규 DB 호환 API-only 배포본**을 사용한다. 전환 잠금 변수를 모르는 구 배포본은 기존 DB writer를 다시 시작할 수 있으므로 그대로 되돌리지 않는다. 신규 DB migration이나 데이터를 일괄 삭제하지 않고 이전 영수증과 실제 적용 범위에 따라 복구한다. 기존 DB와 제외 데이터는 계속 변경 없이 보존한다.
