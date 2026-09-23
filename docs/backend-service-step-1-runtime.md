# 보완 1단계 결과 — X·Discord 안정화

완료일: 2026-09-22. [보완 개발 계획](backend-service-readiness-plan.md)의 A단계 구현과 로컬 검증을 완료했다. 기존 선택 이전 조사인 `backend-phase-1-baseline.md`와는 별도 단계다. 실제 DB 이전·운영 활성화는 수행하지 않았다.

## 이번 목표의 범위

- admin-web은 없는 것으로 취급한다. 관리 화면·관리 API·연동·관리 기능 개발에 의존하지 않는다.
- YouTube 아카이브·세트리스트·커버와 등록된 Spotify 계정의 신규 DB 전환은 다음 단계에서 진행한다. Spotify는 `external_accounts(platform=spotify)`에 등록된 계정만 사용하며 미등록 계정을 탐색·생성·연결하지 않는다.
- 노래방 번호의 확정 연결에는 `karaoke_numbers.song_id`가 필요하다. 곡 ID 구축 후 TODO로 남긴다. 가사·번역·독음 생성도 TODO이며 이번 통합 목표에서 제외한다. 저장된 자료 조회는 유지한다.
- 이번 단계에서는 X 원문 저장과 Discord 원문 URL 전송만 변경했다. 봇 명령·X 분류·X→YouTube 자동 등록·Google 호출은 추가하지 않았다.

## 구현 결과

| 영역 | 변경 |
| --- | --- |
| 최초 X 조회 | 원문은 저장하되 과거 글 delivery를 만들지 않는다. 성공한 빈 응답도 기준선 확보로 기록하고 실패한 조회는 기준선을 만들지 않는다 |
| 기준선 저장 | 기존 `collection_states.provider_state.x_baseline_initialized`를 사용. 승계한 `last_seen_external_id`가 있으면 기존 cursor부터 정상 재개 |
| 계정 순환 | 마지막 조회 시각 순으로 선점하고 같은 실행에서 처리한 계정은 제외. 성공 후 `next_poll_at` 갱신. 앞의 계정만 반복 처리하는 문제 해결 |
| 활성 여부 | `collection_enabled`와 보관 상태가 기준. 기존 state의 disabled가 재활성화를 막지 않음 |
| 계정 식별 | 숫자 platform ID/유효 handle 누락은 상태 오류로 남기고 provider 미호출. 수집 도중 계정 ID/handle·활성 상태가 바뀌면 결과 저장 차단 |
| X 원자 저장 | 원문·delivery·cursor는 같은 transaction. 기존 cursor보다 오래된 응답은 알림으로 만들지 않고 cursor도 역행하지 않음 |
| lease | 한 번에 실제 처리할 한 건만 선점. 고유 claim token과 만료 시각을 저장·결과 반영 때 검사. 이전 worker가 뒤늦게 결과를 덮어쓰지 못함 |
| 채널 조회 | guild intent만 사용. cache miss 시 REST fallback, route의 guild 소속·채널 유형·봇 view/send 권한 확인 |
| 전송 직전 검사 | route version·활성 계정·guild/channel·소유자 활성 상태·source 계정 관계·lease 재확인. 채널 REST 조회가 끝난 뒤 POST 직전에도 service callback으로 다시 확인 |
| DB 기록 장애 | 전송 성공 후 영수증 transaction만 최대 3번 시도. 계속 실패하면 결과 불명확으로 격리하고 알려진 message ID를 복구용 기록에 남김. 외부 메시지는 다시 보내지 않음 |
| Discord 오류 | 확인된 미전송만 제한 재시도. Retry-After 반영. 접근/영구 거부는 failed, 전송 도중 timeout·취소·불명확한 실패·잘못된 receipt는 unknown |
| DB 전체 장애 | 상태 기록마저 실패하면 sending을 남김. lease 만료 뒤 unknown으로 격리하며 자동 재전송하지 않음 |
| 민감정보 | provider 예외 본문 대신 오류 종류를 상태에 기록. DB URL·토큰·원문을 오류 로그로 출력하지 않음 |

수정 위치: [repository](../app/repositories/runtime_delivery.py), [X service](../app/services/x_collection.py), [delivery service](../app/services/notification_delivery.py), [오류 계약](../app/services/delivery_errors.py), [Discord adapter](../app/bots/discord_bot.py), [scheduler](../app/agents/scheduler.py).

## 실행 주기와 설정

X와 Discord는 독립 loop로 실행하므로 X provider 응답을 기다리는 동안에도 delivery를 처리한다. `AGENT_INTERVAL_SECONDS`는 X 계정의 정상 polling 간격으로 유지한다. X의 due 상태는 최대 10초 간격으로 확인하며 backoff와 `next_poll_at`이 실제 provider 호출을 제한한다. `AGENT_RUN_ON_START=false`이면 최초 X 실행은 기존처럼 한 polling 간격 뒤다.

Discord는 시작 직후 대기열 확인을 시작하고 이후 5초마다 due delivery를 확인한다. 준비되지 않은 봇은 delivery를 선점하지 않는다. 따라서 AGENT_RUN_ON_START는 이제 X의 최초 실행 지연에만 적용된다. 새 환경변수는 추가하지 않았다.

X fetch timeout은 기본 240초, lease는 300초다. Discord 채널 조회·전송 timeout은 기본 90초, lease는 120초다. 정상 DB session은 기존 statement timeout을 유지한다. 긴 batch를 미리 점유하지 않으므로 뒤의 작업이 실행을 기다리다 lease를 소진하지 않는다.

`RUNTIME_CUTOVER_ENABLED=false`는 API-only, true와 `AGENT_ENABLED=false`는 봇 연결만, 두 값 모두 true일 때 X/Discord loop를 실행한다. 환경변수 변경은 배포/프로세스 재시작이 필요하다. 현재 Railway 설정은 이 검증에서 확인하지 않았다.

## 검증

2026-09-22, 격리된 로컬 PostgreSQL과 가짜 provider/sender로 실행했다.

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

**198 passed, 312 warnings.** warnings는 기존 Python/FastAPI/Starlette deprecation이다. 기존 165개 테스트에 [보완 회귀 테스트](../tests/test_runtime_readiness.py) 33개를 추가했다. 기존 X 테스트는 승계 cursor가 있는 경우의 새 글 전송을 검증하도록 수정했다.

검증 범위:

- 사전 조사 6개 결함의 정상 동작, 빈 최초 조회·최초 실패 후 재개
- polling 중 비활성/계정 변경·lease 만료, ID 누락, cursor 역행 차단, provider timeout
- 전송 성공 후 일시/지속 DB 기록 장애, timeout·취소·불명확한 예외·잘못된 receipt
- 403/404/429/500 오류 분류, Retry-After, 잘못된 guild·권한 상실·채널 조회 중 route 비활성화
- 동시 collector/sender의 중복 선점 차단, stale owner·만료된 claim의 결과 갱신 차단
- X provider가 멈추거나 예외를 내도 Discord 실행 진행
- 기존 API·선택 이전·신규 schema·조회 계약·runtime 잠금 회귀

로컬 Python에서 빠져 있던 프로젝트 명시 의존성 `audioop-lts`를 설치해 실제 discord.py client 클래스를 테스트했다. 오디오 기능이나 실제 Discord 연결은 사용하지 않았다. 관리자 관련 기존 테스트가 전체 suite에 포함되어 있지만 관리자 개발·연동을 이번 완료 조건으로 삼지 않는다.

## 남은 경계

외부 전송의 exactly-once를 보장하지 않는다. route의 마지막 검사 이후 외부 POST까지의 경합, 프로세스 종료, discord.py 내부 HTTP 재시도·실제 네트워크 동작은 운영 환경에서 별도 확인한다. 불명확한 건은 자동 재전송하지 않는다.

운영 DB schema·데이터·환경변수, PR, Railway는 변경하지 않았다. 이번 변경은 기존 `001/002` schema로 동작하며 추가 migration은 없다. 현재 운영 서버에 적용된 상태가 아니며 전체 통합 완료도 아니다. 다음은 **보완 2단계: admin-web에 의존하지 않는 YouTube·Spotify 작업 실행기**다.
