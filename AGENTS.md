# UtaMowa (우타모와) 작업 지침

## 현재 기준

FastAPI + PostgreSQL(신규 DB, 단일 `DATABASE_URL`) 백엔드, 조회 프론트 `web/`, Discord URL 전송 봇과 수집 worker로 구성한다. 공통 원칙은 [constitution](.specify/memory/constitution.md), 실행법은 [README](README.md), 현재 처리 경로는 [백엔드 구조](docs/backend-architecture.md), 미완료 작업은 [후속 작업](docs/backend-roadmap.md)에 둔다. 범위 결정의 근거는 [통합 최종 계획](docs/plans/backend-consolidation-plan.md)과 [서비스 보완 계획](docs/plans/backend-service-readiness-plan.md)이다.

| 구분 | 대상 |
| --- | --- |
| 운영 경로 | 조회 전용 `/api`(`/api/v2`는 임시 숨김 별칭), `python -m app.runtime`의 X 원문 저장·Discord URL 전송, 독립 YouTube 수집, `external_accounts`에 등록된 Spotify 계정 수집, Holodex 멀티뷰, 공개 라이브 일정, 프로필 이미지 작업 |
| 보존 전용 | 마운트하지 않은 구 라우터(`artists`·`songs`·`youtube`·`spotify`·`auth`), Google Calendar 연동(데이터는 기존 DB에 보존), 기존 `app/core/db.py`, 기존 DB(읽기 전용 조사만) |
| 제거 대상 | 봇 명령, X 분류, X 글의 YouTube 자동 등록 |
| 후속 TODO | 관리 도구(새로 설계, 2026-11-23 기존 `admin-web`·`web.bak` 삭제), 노래방(song_id 구축 후), 가사·번역·독음 |

- 보존 코드와 실제 실행 경로를 구분한다. helper가 존재한다고 운영 경로에 연결된 것으로 간주하지 않는다.
- 후속 TODO는 사용자 요청 없이 개발·연동하거나 worker에서 실행하지 않는다.
- 세부 영역의 `AGENTS.md`도 따른다. 미구현 보안·데이터 계약은 구현된 것처럼 문서화하지 않는다.

## 구현 원칙

- HTTP 계약은 Pydantic 모델로 명시하고 router / service / repository / integration 책임을 구분한다.
- 수집·저장·전송은 일반 함수로 유지한다. LangGraph는 판단·분기가 필요한 흐름에 사용하며 정상 경로를 일괄 재작성하지 않는다.
- 원문 게시글, 외부 ID, 출처 URL, 기존 소유권을 보존한다. 이름만으로 데이터 일괄 병합·삭제를 하지 않는다.
- `source_items`로 중복을 먼저 차단하고 route별 전송 이력을 유지한다. route가 없으면 알림을 생략한다.
- 공유 SQLAlchemy 연결 풀과 요청별 Session을 사용한다. 기존 `app/core/db.py`의 증분 초기화는 마이그레이션 계획 없이 대체하지 않는다.
- 조회 API에서 수집·번역·생성·전송을 새로 시작하지 않는다. 페이지·필터·정렬 기준을 문서화한다.

## 자동화 확장

현재 운영 경로에는 게시글 분류가 없다(X 분류는 제거 대상, 세트리스트 후보 비교는 별도 계약). X 이외의 새 분류 경로를 추가할 때 collect → deduplicate → rule filter → classify → 필요한 타입별 extract → persist → notify 순서를 따른다. 현재 동작과 향후 설계를 구분한다.

- 허용 타입: notice, release, live_event, ticket, merch, irrelevant.
- 명백히 무관한 글은 규칙으로 제외하고 필요한 후보만 LLM에 보낸다.
- 긴 페이지는 필요한 본문·링크 문맥만 사용한다. LLM 출력은 schema로 검증한다.
- 처리 글 수, 분류/추출 호출 수, 실패·생략 수를 기록한다. 재시도는 중복 저장·전송에 안전해야 한다.
- 글 타입별 단계가 복잡해지거나 승인·부분 재시도·독립 node 테스트가 필요할 때 LangGraph 확장을 검토한다.
- 운영 주기와 X 조회량은 게시량과 API 제한으로 정한다. 제안값을 현재 설정값으로 문서화하지 않는다.

## 권한과 외부 동작

- Discord 서버 공용 설정이나 관리 API를 추가할 때는 `manage_guild`와 해당 서버 접근을 검증한다. 현재 운영 경로에는 없다.
- 구매·결제·응모 제출·CAPTCHA 우회를 자동화하지 않는다. 티켓/굿즈는 원문 링크·후보 안내까지만 제공한다.
- 공식 사이트의 robots.txt·약관, provider rate limit을 존중한다.
- 키·OAuth 토큰·DB URL을 코드, 로그, 공개 문서에 노출하지 않는다.
- 테스트에서 실제 Discord·Calendar·LLM을 호출하지 않는다. DB 변경·재수집·전송은 사용자 요청의 범위를 확인한다.

## 검증과 문서

사용자가 검토하는 스펙·설계·작업 목록·점검·분석 결과는 제목과 본문을 한국어로 작성한다. 파일명, 명령어, API 경로, 코드 식별자와 FR/SC/US/T 식별자는 실제 표기를 사용한다. 인수 시나리오는 전제·동작·기대 결과로 기술한다.

Spec Kit 작업은 [작업 안내](docs/spec-driven-development.md)와 [기능 목록](specs/README.md)을 따른다. 공통 원칙은 [.specify/memory/constitution.md](.specify/memory/constitution.md)에 반영한다. 기능 변경은 해당 spec.md의 요구사항·완료 조건, plan.md의 설계, tasks.md의 작업을 연결하고 현재 계약·검증 기록·roadmap도 갱신한다. 기존 문서에서 옮긴 완료 기록은 당시 날짜와 근거를 유지한다.

핵심 검증은 원문 중복 방지, 허용 분류, source/route 접근 권한, 전송 생략·중복 방지, 기존 API 호환성이다. 변경에 맞는 테스트를 실행하고 fixture 테스트와 실데이터 검증을 구분해 기록한다.

실행법은 README, 현재 구조·계약은 `docs/` 루트, 확정 계획은 `docs/plans/`, 날짜별 작업·검증 기록은 `docs/records/`(`backend/`, `data/`), 남은 작업은 roadmap에 둔다. 새 날짜별 기록은 `docs/records/` 아래에 만들고 현재 계약 문서에는 결과 요약과 링크만 남긴다. 폐기된 계획과 중복 SQL/타입 초안을 AGENTS에 쌓지 않는다. 테스트 통과 기록에는 날짜와 검증 범위를 명시한다.
