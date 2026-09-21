# Agent 및 Worker 영역 작업 지침

이 문서는 `app/agents/` 아래에서 작업할 때 루트 `AGENTS.md`에 추가로 적용된다.
이 디렉터리는 수집된 게시글을 처리하는 자동화 workflow와 주기 실행 orchestration을 담당한다.

2026-09-21 목표 변경: [최종 통합 계획](../../docs/backend-consolidation-plan.md)에 따라 X 분류·추출·Calendar 및 X 글의 YouTube 자동 등록을 제거한다. X는 원문 저장·Discord URL 전송 예약만 수행하며 아래 분류 확장 순서는 X에 적용하지 않는다. 독립 음악 수집은 유지한다. 이 목표를 현재 구현 상태로 간주하지 않는다.

## 책임

- 활성 수집 소스를 순회하는 scheduler와 worker 실행
- 신규 게시글 판별과 처리 순서 제어
- LangGraph node 및 조건부 분기 구성
- 분류, 상세 추출, 캘린더, 알림 단계 연결
- 실행 건수와 실패 결과 집계

## 경계

- X, OpenAI, Google, Discord의 구체적인 API 호출은 `app/integrations/`에 둔다.
- SQL을 workflow node마다 직접 반복하지 않고 공용 DB helper를 사용한다.
- FastAPI 요청 객체나 Discord interaction 객체를 state에 넣지 않는다.
- LangGraph는 판단과 분기에 사용하고 단순 저장·조회·전송까지 억지로 node로 만들지 않는다.
- node 사이에는 직렬화 가능한 명시적 state를 전달한다.

## 현재 동작과 확장 시 처리 순서

현재 scheduler는 X 새 글을 notice로 저장하고 소스별로 알린다. music_graph.py의 분류/추출과 Calendar 생성은 이 경로에 연결되어 있지 않다. 현재 상태는 [백엔드 구조](../../docs/backend-architecture.md)를 따른다. 아래 순서는 분류·일정 자동화를 확장할 때의 설계 원칙이며 현재 구현 완료 목록이 아니다.

```text
collect
-> deduplicate
-> rule filter
-> classify
-> type-specific extraction
-> persist
-> calendar
-> notification
```

- `source_items` 중복 검사를 분류나 전송보다 먼저 수행한다.
- 모든 새 글을 저장할 수는 있지만 모든 글을 LLM에 보내지 않는다.
- 명백한 잡담과 무관한 글은 가능한 규칙 기반으로 먼저 줄인다.
- 상세 추출은 필요한 타입에만 실행한다.
- route가 없으면 오류가 아니라 알림 생략으로 처리한다.

## 안정성

- 한 소스의 실패가 다른 소스 처리를 중단시키지 않게 격리한다.
- 외부 API 실패에는 source, 단계, 재시도 가능 여부를 로그로 남긴다.
- `last_seen_external_id`는 처리 범위를 잃지 않도록 안전한 시점에 갱신한다.
- 정상 worker 실행과 수동 재전송을 구분한다.
- 수동 테스트가 정규 중복 방지 상태를 임의로 손상하지 않게 한다.
- 같은 `source_item`이 같은 route로 반복 전송되지 않도록 전송 이력을 고려한다.

## LLM 사용

- 허용된 item type 외의 값을 state에 저장하지 않는다.
- LLM 출력은 Pydantic 또는 명시적인 schema로 검증한다.
- 긴 원문 전체보다 필요한 본문과 링크 문맥만 전달한다.
- prompt 변경 시 분류 fixture와 회귀 테스트를 함께 갱신한다.
- confidence와 내부 reasoning은 디버깅 데이터로 취급하고 사용자 메시지에 그대로 노출하지 않는다.

## 사람 승인과 금지 범위

- 티켓과 굿즈는 페이지 안내 및 관심 표시까지만 자동화한다.
- 구매, 결제, 응모 제출, CAPTCHA 우회는 workflow에 추가하지 않는다.
- 외부 상태를 변경하는 고위험 단계는 명시적인 사람 승인을 요구한다.

## 테스트

- node 단위 테스트와 전체 workflow 테스트를 구분한다.
- X, OpenAI, Calendar, Discord 호출은 mock 처리한다.
- 중복 글, route 없음, LLM 오류, 부분 API 실패를 테스트한다.
- 결과 집계의 `seen`, `classified`, `created`, `sent`, `skipped`, `failed` 수가 실제 처리와 일치하는지 확인한다.
