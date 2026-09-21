# 5단계 운영 전환

## 현재 상태

애플리케이션 코드는 신규 DB를 사용하는 통합 조회 API와 X 수집·Discord 전송 runtime으로 정리했다. 정식 조회 경로는 `/api`이며 `/api/v2`는 기존 새 프론트 배포본을 위한 숨김 호환 경로로만 유지한다. 기존 쓰기 API, Google Calendar, Spotify, 노래방, 가사 처리 router는 운영 앱에 마운트하지 않는다.

PR 병합과 Railway 배포까지 시간이 걸려도 기존 운영에는 영향이 없다. 배포본의 `RUNTIME_CUTOVER_ENABLED` 기본값은 `false`이므로, 새 코드가 먼저 올라가도 API만 실행하고 Discord 봇과 X 수집 worker는 시작하지 않는다.

## 전환 순서

1. 기존 Railway writer를 중지한다.
2. 기존 DB를 읽기 전용으로 최종 dry-run하고 건수와 manifest를 확정한다.
3. 승인한 manifest로 `scripts/migrate_runtime_state.py --apply`를 한 번 실행한다.
4. 신규 DB의 migration receipt와 대상 테이블 건수를 확인한다.
5. Railway에 `RUNTIME_CUTOVER_ENABLED=true`를 설정한다.
6. Discord 봇만 먼저 연결되는지 확인한다.
7. `AGENT_ENABLED=true`로 X 수집을 활성화한다.
8. 첫 수집에서 과거 글을 재전송하지 않고 새 글만 저장·전송하는지 확인한다.

전환이 끝나기 전에는 migration apply를 실행하지 않는다. 기존 writer가 계속 쓰는 동안 만든 manifest는 최종본으로 사용하지 않는다.

## 확인 항목

- `/health`와 `/api/artists`가 신규 DB만 사용한다.
- `/api/v2/artists` 호환 경로가 같은 응답을 반환한다.
- 기존 쓰기 API와 Google/provider route가 노출되지 않는다.
- Discord 명령이 등록되지 않는다.
- X 원문과 URL은 한 번만 저장되고 route별 Discord 전송도 한 번만 기록된다.
- X 분류와 X 본문의 YouTube 링크 자동 등록이 호출되지 않는다.

## 롤백

문제가 생기면 `RUNTIME_CUTOVER_ENABLED=false`로 바꾸어 Discord/수집 runtime을 즉시 잠근다. 신규 DB에 이미 적용한 migration을 되돌려 기존 DB에 쓰지 않는다. API 문제는 이전 Railway 배포본으로 롤백하고, 기존 DB는 계속 읽기 전용으로 보존한다.
