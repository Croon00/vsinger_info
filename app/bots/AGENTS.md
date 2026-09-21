# Discord Bot 영역 작업 지침

이 문서는 `app/bots/` 아래에서 작업할 때 루트 `AGENTS.md`에 추가로 적용된다.
이 디렉터리는 Discord 연결, slash command, interaction 응답과 채널 전송을 담당한다.

2026-09-21 목표 변경: [최종 통합 계획](../../docs/backend-consolidation-plan.md)에 따라 모든 사용자 명령·interaction을 제거하고 X 원문 URL 전송만 남긴다. 아래 명령 관련 지침은 아직 남아 있는 코드의 전환 안전 기준이며 새 봇 관리 기능을 구현하라는 요구가 아니다. 실제 제거와 Discord 원격 명령 해제는 후속 구현·배포 작업이다.

## 책임

- Discord bot lifecycle과 command 등록
- slash command 입력 검증과 ephemeral 응답
- Discord guild·channel·permission 확인
- 분류된 게시글을 선택된 채널에 표시
- 버튼과 interaction callback 처리

## 경계

- SQL과 비즈니스 규칙을 command 함수에 직접 중복 구현하지 않는다.
- 라우트 CRUD는 `app/integrations/notifications.py` 같은 공용 helper를 사용한다.
- 수집·분류·일정 추출은 `app/agents/` 및 `app/integrations/`에 위임한다.
- FastAPI endpoint를 봇 내부에서 직접 호출해 같은 프로세스의 로직을 우회하지 않는다.
- command 함수는 권한 확인, service 호출, 사용자 응답 조립에 집중한다.

## 권한과 안전

- 서버 공용 설정 명령은 `manage_guild` 권한을 필수로 확인한다.
- command에서 받은 `channel`, `route_id`, `source_id`가 현재 guild 범위인지 검증한다.
- 토큰과 OAuth credential을 메시지, embed, 로그에 포함하지 않는다.
- 티켓 구매, 응모 제출, 결제, CAPTCHA 우회 기능은 구현하지 않는다.
- 재전송이나 일괄 테스트는 전송 건수를 사용자에게 먼저 명확히 보여주고 중복 폭주를 방지한다.

## 메시지 규칙

- 메시지는 2,000자 제한보다 여유 있게 짧게 유지한다.
- 원문 URL은 반드시 포함한다.
- 사용자용 메시지에는 내부 confidence, raw exception, 긴 LLM reasoning을 노출하지 않는다.
- `irrelevant` 사용자 표시는 `(분류 : 잡담)`처럼 짧게 표현한다.
- Discord가 URL embed를 자동 생성한다는 점을 고려해 원문을 불필요하게 반복하지 않는다.
- 사용자에게만 필요한 설정 결과는 기본적으로 ephemeral 응답을 사용한다.

## 테스트

- Discord API 자체는 mock하고 전송할 channel과 message를 검증한다.
- 권한 없는 사용자의 설정 변경이 거부되는지 테스트한다.
- route가 없거나 channel을 찾지 못했을 때 안전하게 skip되는지 테스트한다.
- 같은 source item이 정규 파이프라인에서 중복 전송되지 않는지 확인한다.

