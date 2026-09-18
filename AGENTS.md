# schedule_music 작업 지침

## 현재 기준

FastAPI + PostgreSQL 백엔드, 기존 관리 웹 `web/`, 새 조회 프론트 `front-design-draft/`, Discord 봇과 수집 worker를 함께 유지한다. 실행법과 문서 지도는 [README](README.md), 현재 처리 경로는 [백엔드 구조](docs/backend-architecture.md), 미완료 작업은 [후속 작업](docs/backend-roadmap.md)에 둔다.

- 새 프론트는 조회 전용 `/api/v2`를 사용한다. 기존 API와 관리 기능은 사용 종료가 확인되기 전 제거하지 않는다.
- scheduler의 현재 X 경로는 새 글 알림이다. LangGraph 분류와 Google 일정 생성 helper가 존재한다고 자동 연결된 것으로 간주하지 않는다.
- 세부 영역의 `AGENTS.md`도 따른다. 미구현 보안·데이터 계약은 구현된 것처럼 문서화하지 않는다.

## 구현 원칙

- HTTP 계약은 Pydantic 모델로 명시하고 router / service / repository / integration 책임을 구분한다.
- 수집·저장·전송은 일반 함수로 유지한다. LangGraph는 판단·분기가 필요한 흐름에 사용하며 정상 경로를 일괄 재작성하지 않는다.
- 원문 게시글, 외부 ID, 출처 URL, 기존 소유권을 보존한다. 이름만으로 데이터 일괄 병합·삭제를 하지 않는다.
- `source_items`로 중복을 먼저 차단하고 route별 전송 이력을 유지한다. route가 없으면 알림을 생략한다.
- 공유 SQLAlchemy 연결 풀과 요청별 Session을 사용한다. 기존 `app/core/db.py`의 증분 초기화는 마이그레이션 계획 없이 대체하지 않는다.
- 조회 API에서 수집·번역·생성·전송을 새로 시작하지 않는다. 페이지·필터·정렬 기준을 문서화한다.

## 자동화 확장

분류 경로를 추가할 때 collect → deduplicate → rule filter → classify → 필요한 타입별 extract → persist → calendar/notify 순서를 따른다. 현재 동작과 향후 설계를 구분한다.

- 허용 타입: notice, release, live_event, ticket, merch, irrelevant.
- 명백히 무관한 글은 규칙으로 제외하고 필요한 후보만 LLM에 보낸다.
- 긴 페이지는 필요한 본문·링크 문맥만 사용한다. LLM 출력은 schema로 검증한다.
- 처리 글 수, 분류/추출 호출 수, 실패·생략 수를 기록한다. 재시도는 중복 저장·전송에 안전해야 한다.
- 글 타입별 단계가 복잡해지거나 승인·부분 재시도·독립 node 테스트가 필요할 때 LangGraph 확장을 검토한다.
- 운영 주기와 X 조회량은 게시량과 API 제한으로 정한다. 제안값을 현재 설정값으로 문서화하지 않는다.

## 권한과 외부 동작

- Discord 서버 공용 설정은 `manage_guild`와 해당 서버 접근을 검증한다.
- 구매·결제·응모 제출·CAPTCHA 우회를 자동화하지 않는다. 티켓/굿즈는 원문 링크·후보 안내까지만 제공한다.
- 공식 사이트의 robots.txt·약관, provider rate limit을 존중한다.
- 키·OAuth 토큰·DB URL을 코드, 로그, 공개 문서에 노출하지 않는다.
- 테스트에서 실제 Discord·Calendar·LLM을 호출하지 않는다. DB 변경·재수집·전송은 사용자 요청의 범위를 확인한다.

## 검증과 문서

핵심 검증은 원문 중복 방지, 허용 분류, source/route 접근 권한, 전송 생략·중복 방지, 기존 API 호환성이다. 변경에 맞는 테스트를 실행하고 fixture 테스트와 실데이터 검증을 구분해 기록한다.

실행법은 README, 현재 구조·계약은 docs, 남은 작업은 roadmap에 유지한다. 폐기된 계획과 중복 SQL/타입 초안을 AGENTS에 쌓지 않는다. 테스트 통과 기록에는 날짜와 검증 범위를 명시한다.
