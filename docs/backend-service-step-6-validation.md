# 백엔드 보완 6단계 — 통합 검증과 배포 준비

기준: 2026-09-23. 운영 DB 이전·수집기 활성화·Railway 배포는 수행하지 않았다. 기존 DB는 변경하지 않았다.

## 로컬 통합 검증

- 격리 PostgreSQL에 `001/002` schema를 적용하고, 승인된 선택 이전 manifest로 X cursor·route·기존 성공 전송·YouTube 대기 작업을 원자 적용했다. 가짜 YouTube provider로 이전 작업을 처리한 뒤 정식 `/api/artists/{id}/lives`와 `/api/lives/{id}`에서 신규 archive와 가창 2개를 확인했다. `/api/v2` 숨김 별칭은 동일 응답을 냈다. 이전한 성공 전송은 새 `pending` 전송으로 예약되지 않았다. 이 검증은 [통합 테스트](../tests/test_stage6_integrated_flow.py)에 있다.
- 전체 백엔드 회귀 **311개 통과**. X 첫 조회·중복·cursor 보존, Discord 전송 불명확/중복·route 변경·권한, YouTube 댓글 대기·재시도·수동 자료·version 충돌, 등록된 Spotify 계정만 수집·연결, legacy 연결 차단과 제외 작업 경계를 포함한다. 외부 provider·Discord는 테스트 더블을 사용했다.
- 조회 웹 TypeScript 검사와 프로덕션 빌드 통과. 웹 단위 테스트 **26개**, 실제 모드 HTTP fixture 브라우저 테스트 PC·모바일 **4개** 통과. fixture 테스트는 실제 DB와 별개다.
- 로컬 API를 실제 신규 DB에 연결한 브라우저 점검: `/api/artists` 200, 아티스트 70명 탐색, HACHI 상세의 라이브 266개, 라이브 상세의 YouTube 연결·가창 9곡, 프로필 이미지 256px 로드를 확인했다. 신규 DB를 읽기만 했고 수집·전송 작업은 시작하지 않았다. `/ready`는 200, DB 검증 성공, worker 비활성 상태를 보고했다.
- 실제 신규 DB에는 이 점검 시점에 `album_artists`와 활성 `recording_lyrics` 행이 0개였다. 앨범 화면의 빈 상태를 확인했고, 앨범·가사 내용/오류 상태는 HTTP fixture 브라우저 테스트와 격리 DB API 테스트로 검증했다. 실제 데이터가 생긴 뒤 운영 화면에서 다시 확인해야 한다.

## PR 검토 자료

변경 범위는 단일 `DATABASE_URL`/신규 DB guard, X 원문·Discord URL 전송, 독립 YouTube/등록 Spotify 수집, `runtime-subset-v2` 선택 이전과 legacy 격리다. Discord 관리 명령, X 분류, X→YouTube 자동 등록, 정상 scheduler의 Google·노래방·가사 작업을 제거/격리했다. Schema는 기존 `001/002` 그대로이며 신규 revision이 없다. `NEW_DATABASE_URL`은 제거하고 `LEGACY_DATABASE_URL`은 이전 도구에만 쓴다. Railway 변수와 적용 순서는 [5단계 결과](backend-service-step-5-migration.md), [운영 전환](backend-phase-5-cutover.md)에 있다.

기존 [PR #1](https://github.com/Croon00/vsinger_info/pull/1)은 2026-09-22 병합 없이 종료됐다. 사용자는 PR을 직접 처리하기로 결정했다. 이 점검에서 PR을 다시 열거나 새 PR을 만들거나 원격 branch에 push하지 않았다. 변경 내용은 로컬 작업 트리에 있다. 사용자가 PR을 열 때 이 검증 결과와 운영 미검증 항목을 본문에 반영한다.

**사용자가 PR을 열 시점은 로컬 변경을 검토한 뒤, Railway 배포 조정 전에다.** 아직 로컬 변경은 commit/push하지 않았다. 사용자는 `.env`·manifest가 포함되지 않았는지 확인하고, 변경 파일을 commit/push한 다음 닫힌 PR #1을 재개하거나 새 PR을 연다. 본문에는 위 변경 범위·검증 건수와 함께 “운영 이전·실제 수집/전송·Railway 미검증”을 명시한다. PR 병합이 Railway 자동 배포를 시작할 수 있으므로 관리자가 새 DB 설정과 `RUNTIME_CUTOVER_ENABLED=false`, `AGENT_ENABLED=false`를 준비하고 배포 일정을 합의하기 전에는 병합하지 않는다.

## 운영 전환 선행 조건

Railway 관리자는 기존 writer와 replica, `DATABASE_URL`·컷오버 잠금 변수, X/twscrape 저장소, Discord 채널 권한, YouTube/Spotify 자격 증명·한도, 조회 웹의 운영 `/api` 프록시·SPA fallback·이미지 공개 접근을 확인해야 한다. 신규 DB 호환 API-only 복구 배포본과 최초 실행 시각을 정한다. 실제 provider 호출·Discord 전송·운영 주기·배포 웹 검증은 로컬 테스트로 대체하지 않는다.

운영 writer를 중지한 다음에만 구 DB를 읽기 전용으로 다시 snapshot하고 최종 manifest를 승인·적용한다. 이후 읽기 검증, 봇 연결, 제한된 수집/전송 활성화 순으로 진행한다. 현재 dry-run manifest는 운영 writer가 계속 쓰는 동안 생성됐으므로 최종 적용에 사용하지 않는다.
