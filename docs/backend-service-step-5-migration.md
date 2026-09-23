# 백엔드 보완 5단계 — 선택 이전과 설정·legacy 경계

기준: 2026-09-23. 이번 단계는 로컬 코드·fixture 검증이다. 운영 writer 정지, 최종 manifest 적용, Railway 변경, Discord·provider 실동작 확인은 [전환 절차](backend-phase-5-cutover.md)에서 수행한다.

## 이전 대상과 재개 의미

`scripts/migrate_runtime_state.py`는 `LEGACY_DATABASE_URL`에 `REPEATABLE READ READ ONLY` 트랜잭션만 열고, `DATABASE_URL`의 신규 DB identity(`catalog-v2`, revision `001/002`, instance)를 확인한다. 기본 실행은 보고서 생성만 하며 적용에는 동일한 manifest의 `approved_for_apply=true`가 필요하다. `001/002`에는 변경이 없고 이번 단계에 신규 schema revision은 필요하지 않다.

X cursor, 검토된 route 소유권, 성공한 Discord 전송 이력과 원문 의존 집합만 옮긴다. YouTube는 승인된 채널의 미완료 영상과, 채널 영상이 이미 `processed`여도 `youtube_live_archives.status='pending'`인 댓글/세트리스트 대기를 함께 선택한다. 승인 채널 영상과 연결되지 않은 과거 X 자동등록 후보는 제외 사유를 manifest에 남긴다. 동일 외부 영상에 서로 다른 승인 계정이나 충돌하는 대기 상태가 있으면 적용하지 않고 멈춘다.

작업 payload와 key는 현행 `YouTubeCollect` 계약으로 만든다. 동일 외부 영상에 구 archive 행이 여러 개이면 영상당 작업 하나로 합치고 모든 원본 ID와 상태를 기록한다. 대기 횟수는 최대 기존 횟수를 `wait_count`로, 다음 확인 시각은 가장 이른 `next_attempt_at`으로, 마지막 확인 시각은 가장 최근 기록으로 보존한다. 기존 신규 영상은 YouTube 외부 ID와 소유 계정으로 연결한다. 신규 archive에 이미 가창이 있거나 완료 처리된 영상은 재조회 작업에서 제외하고 근거를 manifest에 남긴다. 종료 시각이 없는 채널 영상은 즉시 수집 작업으로 실행하지 않고 채널 poll의 pending ID에 남긴다. 채널 첫 조회에는 manifest의 기준 시각을 사용해 과거 영상 재수집을 막는다. 기존 신규 archive가 비어 있고 변경 충돌이 없으면 후속 댓글 결과로 가창을 채울 수 있다. 이미 있는 가창과 수동 수정은 덮어쓰지 않는다. 성공한 Discord 전송은 다시 예약하지 않는다.

Manifest에는 선택한 계정 version, X cursor, route 소유자, 성공 delivery ID, 원문 legacy ID→신규 계정/외부 ID 대응, YouTube 영상·archive ID 대응, 작업 시각·대기 횟수, 제외 이유와 건수를 기록한다. 원문 본문·토큰·DB URL은 기록하지 않는다. 적용은 단일 트랜잭션·영수증으로 원자화하고 같은 manifest 재실행은 중복 적용하지 않는다. 실제 전환에서는 writer를 멈춘 뒤 새 dry-run을 만들고, 그 snapshot을 승인·적용한다. 과거 dry-run 결과는 적용 근거로 쓰지 않는다.

## 실행·설정 경계

정상 API·X/Discord·YouTube·Spotify worker는 루트 `.env` 또는 서버 환경변수의 `DATABASE_URL` 하나와 `app/db/catalog_session.py`의 revision/instance guard를 사용한다. 이전 전용 `LEGACY_DATABASE_URL`은 정상 Settings가 읽지 않는다. 옛 `NEW_DATABASE_URL`이 남아 있으면 앱이 시작을 거부한다. 로컬 `.env.catalog`의 신규 DB/이미지 설정은 비밀값을 출력하지 않고 `.env`로 통합했다. 백업은 Git 제외 `.tmp/env-consolidation/`에 있다. 구 SQL의 `app/core/db.py`와 `app/db/session.py` 연결 진입점은 호출 즉시 거부한다.

Google OAuth/Calendar 코드는 정상 앱에 마운트되지 않고 별도 `app/legacy/config.py`의 설정만 참조한다. 기존 DB 데이터는 그대로 보존한다. 구 관리 웹과 구 API의 SQL 경로는 정상 runtime에서 실행되지 않는다. admin-web 연동은 이번 목표에서 제외한다. `/api/v2` 숨김 조회 별칭은 실제 소비자 확인 후 제거한다.

이미지 조회의 `AWS_ENDPOINT_URL_S3`와 `AVATAR_BUCKET`은 공개 URL 구성에 필요하다. `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`은 명시적 업로드 도구에서만 사용한다. `/ready`는 활성 등록 계정이 있는 provider의 YouTube API key 또는 Spotify client 자격 증명만 필수로 확인한다. `OPENAI_API_KEY`는 YouTube 댓글 세트리스트 추출의 선택 사항이며 없으면 규칙 추출을 사용한다.

## Railway 관리자 변수표

| 변수 | 배포 전 확인 |
| --- | --- |
| `DATABASE_URL` | 신규 통합 DB 주소로 설정. 구 DB 주소를 그대로 둔 채 새 코드를 시작하지 않음 |
| `NEW_DATABASE_URL` | 제거. 남으면 시작 실패 |
| `NEW_DATABASE_INSTANCE_ID` | 선택적 UUID 고정 검사. 쓰려면 신규 DB `catalog_instance.id`와 일치시킴 |
| `RUNTIME_CUTOVER_ENABLED`, `AGENT_ENABLED` | 코드 배포·읽기 검증 중 둘 다 `false`; 선택 이전 후 순서대로 활성화 |
| `DISCORD_BOT_TOKEN` | X 링크 전송 전용 봇의 기존 유효 토큰 확인 |
| `X_PROVIDER`와 선택 provider의 토큰/계정 저장소 | X 수집 자격 증명과 twscrape 디스크 지속성 확인 |
| `YOUTUBE_API_KEY` | 활성 YouTube 계정의 poll/영상·댓글 수집에 필수 |
| `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET` | 활성 등록 Spotify 계정이 있을 때 수집에 필수 |
| `AWS_ENDPOINT_URL_S3`, `AVATAR_BUCKET` | 조회 화면의 이미지 URL 구성에 필요 |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION` | Railway에서 이미지 업로드 도구를 실행할 때만 필요 |
| `OPENAI_API_KEY`, `OPENAI_MODEL` | 선택적 YouTube 댓글 추출. 없으면 규칙 기반 처리 |
| `LEGACY_DATABASE_URL` | 정상 서비스에 넣지 않음. 이전 도구 실행자에게 읽기 전용으로만 제공 |

`DATABASE_AUTO_INIT`, Google OAuth/Calendar 변수, 구 Discord 관리 명령 변수는 정상 서비스에 필요하지 않다. Railway 환경변수 변경은 프로세스 재시작/재배포와 함께 검증한다. 기존 서비스에서 이미 설정된 값도 새 코드의 경계와 권한을 확인해야 한다.

## 검증과 남은 일

2026-09-23 실제 두 DB에 **읽기 전용 dry-run만** 실행했다. 마지막 Git 제외 manifest의 선택 건수는 collection state 125, route 51, X 원문 4,672, 성공 전송 이력 4,591, YouTube 재개 작업 754다. 승인 채널 근거가 없는 archive 534건을 제외했다. 신규 DB에 이미 가창이 있는 영상 229건은 재조회하지 않고, 종료 시각이 없는 영상 1건은 job 대신 채널 poll의 pending ID로 남겼다. 같은 영상의 복수 pending archive 17쌍은 작업당 하나로 통합하고 각 원본 상태를 보존했다. dry-run 사이에 운영 writer가 계속 작성해 원문·전송 이력 건수가 증가했다. 따라서 이 manifest는 최종 전환 snapshot이 아니며 `approved_for_apply=false`이고, 운영 적용도 없었다.

로컬 PostgreSQL fixture에서 원자 적용·영수증 재실행·실패 후 복구, 처리 완료 채널 영상/미완료 archive 조합, 신규 빈 archive 재개, 기존 자료 보존을 확인했다. 구 SQL 연결 차단과 이미지 조회 설정 분리도 테스트했다. 전체 회귀 테스트는 2026-09-23에 **310개 통과**했다. 실제 전환 때는 writer 정지 후 새 snapshot으로 다시 dry-run 해야 한다. [6단계](backend-service-readiness-plan.md)의 전체 계정→작업→API 통합, 웹/운영 검증과 PR 검토는 남아 있다.
