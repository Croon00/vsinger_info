# UtaMowa 프로젝트 원칙

버전 1.1.0 · 제정 2026-11-17 · 최종 수정 2026-11-23

## 근거와 적용

루트와 영역별 AGENTS.md, 통합 최종 계획, 서비스 보완 계획의 확정 사항을 적용한다. 사용자 결정이 우선한다. 과거 문서와 코드 기본값만으로 현재 운영 상태를 확정하지 않는다.

## 핵심 원칙

### I. 스펙과 검증 근거

기능 변경은 specs/<번호-기능명>/spec.md에 사용자 시나리오·요구사항 ID·범위·완료 조건을 기록한다. plan.md에 구현 경로·계약·검증 방법을, tasks.md에 요구사항과 연결된 작업을 기록한다. 구현·fixture 검증·실데이터 검증·배포·운영 확인에 각각 날짜와 근거를 남긴다. 미구현 보안·데이터 계약을 구현된 것처럼 기술하지 않는다.

### II. 데이터와 출처 보존

정상 서비스는 신규 PostgreSQL과 공통 DATABASE_URL을 사용한다. 기존 DB는 읽기 전용으로 조사하고 schema·데이터·권한을 변경하지 않는다. 원문·외부 ID·출처 URL·기존 소유권·수동 교정을 보존한다. 이름만으로 일괄 병합·삭제하지 않는다. 공유 SQLAlchemy 연결 풀과 요청별 Session을 사용한다. app/core/db.py의 증분 초기화는 마이그레이션 계획 없이 대체하지 않는다.

### III. 조회와 수집 경계

조회 웹은 /api를 사용한다. /api/v2는 임시 숨김 별칭이고 구 API는 정상 앱에 마운트하지 않는다. HTTP 계약은 Pydantic 모델로 명시하며 router / service / repository / integration 책임을 지킨다. 조회 요청에서 수집·번역·생성·전송을 시작하지 않는다. 페이지·필터·정렬 기준을 문서화한다.

### IV. 중복 방지와 최소 알림

source_items로 원문 중복을 차단하고 route별 전송 이력을 유지한다. route가 없으면 알림을 생략한다. 재시도·동시 실행에서 중복 저장·전송을 방지한다. X는 신규 external_accounts 기준으로 원문을 저장하고 Discord에 원문 URL을 전송한다. X 분류·봇 명령·X 글의 YouTube 자동 등록은 제거 대상이다. Google Calendar 데이터는 기존 DB에 보존하고 실행 코드는 legacy로 격리한다.

### V. 확정 서비스 범위

현재 통합은 독립 YouTube 수집과 신규 external_accounts에 등록된 Spotify 계정을 대상으로 한다. 관리 도구와 관리 API는 후속 범위이며 새로 설계한다. 2026-11-23 운영 경로와 무관한 기존 admin-web·web.bak은 삭제했다. 노래방은 song_id 구축 후 TODO이고 가사·번역·독음도 이번 목표·worker 실행에서 제외한다. 이후 확정된 기능별 계약은 해당 범위에서 참조한다.

### VI. 외부 동작과 권한

Discord 공용 설정이나 관리 API를 도입하면 manage_guild와 해당 서버 접근을 검증한다. 구매·결제·응모 제출·CAPTCHA 우회를 자동화하지 않는다. 공식 사이트의 robots.txt·약관과 provider 한도를 준수한다. 키·토큰·DB URL을 코드·로그·공개 문서에 노출하지 않는다. DB 변경·재수집·실제 전송은 사용자 요청 범위를 확인한다. 테스트에서 실제 Discord·Calendar·LLM을 호출하지 않는다.

### VII. 필요한 자동화

수집·저장·전송은 일반 함수로 유지하고 LangGraph는 판단·분기가 필요한 흐름에 사용한다. X 이외의 새 분류 경로는 collect → deduplicate → rule filter → classify → 타입별 extract → persist → calendar/notify 순서를 따른다. 허용 타입은 notice, release, live_event, ticket, merch, irrelevant다. LLM 출력은 schema로 검증하고 처리·호출·실패·생략 수를 기록한다. 운영 주기는 게시량과 provider 한도로 정한다.

## 개발 흐름

사용자가 검토하는 문서의 제목·본문·표·분석 결과는 한국어로 작성한다. 파일명·명령어·API 경로·코드 식별자와 추적 ID는 실제 표기를 사용한다. 인수 시나리오는 전제·동작·기대 결과로 작성한다.

specify → clarify → plan → tasks → analyze → implement 순서로 작업한다. 모호성이 없는 단계는 기존 근거로 채울 수 있다. 변경에 맞는 테스트로 원문 중복·source/route 접근·전송 생략과 중복·API 호환성을 확인한다. 실행한 테스트의 날짜·환경·검증 범위를 기록한다.

## 원칙 관리

실행법과 진입점은 README, 현재 구조와 계약은 docs 루트, 확정 계획은 docs/plans, 날짜별 기록은 docs/records, 전체 남은 작업은 roadmap에 유지한다. 기능별 specs는 요구사항·설계·작업을 연결한다. 역사 기록은 당시 날짜와 근거를 보존한다. 원칙 변경 시 근거와 버전을 갱신하고 영향받는 스펙을 점검한다. 새 범위는 사용자 결정 또는 기존 확정 문서의 근거를 기록한다.

1.1.0(2026-11-23): 기존 admin-web·web.bak 삭제, Discord 관리 권한 원칙을 도입 시 조건으로 변경, docs 위치 규칙(plans·records) 추가.

## 참조

- [작업 지침](../../AGENTS.md)
- [통합 최종 계획](../../docs/plans/backend-consolidation-plan.md)
- [서비스 보완 계획](../../docs/plans/backend-service-readiness-plan.md)
- [스펙 작업 안내](../../docs/spec-driven-development.md)
