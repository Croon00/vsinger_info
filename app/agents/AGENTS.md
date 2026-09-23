# Agent 및 Worker 영역 작업 지침

이 문서는 `app/agents/` 아래에서 작업할 때 루트 `AGENTS.md`에 추가로 적용된다. 현재 scheduler는 신규 통합 DB의 X 원문 수집과 Discord delivery 실행만 조율한다.

## 현재 책임

- `external_accounts(platform='x', collection_enabled=true)`의 수집 실행
- 계정별 실패를 격리하고 처리 건수를 집계
- 저장된 pending/retry delivery의 Discord 전송 실행
- 설정한 실행 주기에 따른 loop 유지

X 게시글 타입 분류, 공연·티켓 추출, 링크 페이지 조회, Google Calendar, X 글의 YouTube 자동 등록은 추가하지 않는다. 독립 YouTube·Spotify·노래방·가사 기능을 X 처리에서 시작하지 않는다.

## 경계와 안정성

- SQL은 `app/repositories/runtime_delivery.py`, 업무 상태 전이는 `app/services/`에 둔다.
- 신규 runtime은 `DATABASE_URL`의 identity-guarded session만 사용하고 기존 `app/core/db.py`를 import하지 않는다.
- 원문·route별 delivery·cursor를 원자적으로 반영한다.
- pagination을 끝까지 확보하지 못하면 cursor를 전진시키지 않는다.
- 한 계정 실패가 다른 계정의 수집을 중단시키지 않게 한다.
- 같은 source item과 route의 중복 저장·전송은 DB 고유 제약과 delivery 상태로 막는다.
- 실제 X·Discord 호출은 테스트에서 mock한다.
