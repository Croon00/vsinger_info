# External Integrations 영역 작업 지침

이 문서는 `app/integrations/` 아래에서 작업할 때 루트 `AGENTS.md`에 추가로 적용된다.
이 디렉터리는 프로젝트 내부 코드와 외부 API·웹사이트·전송 시스템 사이의 adapter를 담당한다.

## 책임

운영 경로에서 사용하는 adapter:

- X 사용자·게시글 조회(`x_client.py`)와 notification route helper(`notifications.py`)
- YouTube 채널·아카이브·세트리스트·커버·통계 조회(`youtube_*.py`)와 Holodex 생방송 조회(`holodex.py`)
- 등록된 Spotify 계정의 카탈로그 조회(`spotify_catalog.py` 등)
- 세트리스트 후보 비교용 OpenAI 호출([세트리스트 후보 비교](../../docs/youtube-setlist-selection.md))
- 공식 사이트 공개 라이브 일정 페이지(`live_site_pages.py`)와 프로필 이미지 원본(`avatar_sources.py`)

보존 전용: `google_calendar.py`(Google Calendar legacy), 노래방 조회(`karaoke_lookup.py`, `jpop_playlist_tj.py`)는 후속 TODO다. 사용자 요청 없이 운영 경로에 연결하지 않는다. X 게시글 분류·추출은 제거 대상이다.

## 설계 경계

- 외부 provider의 응답 형식을 프로젝트 전체로 퍼뜨리지 않고 내부 dict 또는 model로 정규화한다.
- provider별 인증, 요청, pagination, 오류 변환은 해당 integration 안에 감춘다.
- workflow 순서와 UI 응답 조립은 integration에 넣지 않는다.
- FastAPI `HTTPException`이나 Discord interaction 타입을 integration에서 사용하지 않는다.
- 여러 호출부가 사용하는 route·calendar helper는 입력과 반환 타입을 명확히 유지한다.

## 네트워크 규칙

- 모든 외부 요청에 유한한 timeout을 설정한다.
- 재시도는 timeout, 429, 일시적인 5xx처럼 안전한 경우에만 제한적으로 적용한다.
- `Retry-After`와 provider rate limit 정책을 존중한다.
- pagination에는 최대 페이지 또는 최대 결과 수를 둔다.
- 외부 응답이 비어 있거나 필드가 누락될 수 있음을 전제로 검증한다.
- 공식 사이트 수집 시 robots.txt와 서비스 약관을 존중한다.

## 인증정보와 로그

- API key, bearer token, OAuth refresh token, client secret을 코드에 하드코딩하지 않는다.
- secret이나 전체 Authorization header를 로그와 예외 메시지에 포함하지 않는다.
- URL query에 민감한 token이 있으면 URL 전체를 로그로 남기지 않는다.
- OAuth state와 사용자 식별자를 혼동하지 않고 callback에서 검증한다.

## 데이터와 시간

- 외부 ID는 숫자로 보이더라도 손실 방지를 위해 문자열로 취급하는 것을 기본으로 한다.
- datetime은 timezone 정보를 보존하고 내부 저장 시 timezone-aware 값을 사용한다.
- provider의 locale·timezone·날짜 생략 규칙을 명시적으로 정규화한다.
- 원문 URL과 provider event ID를 보존해 추적 가능하게 한다.

## 부작용과 안전

- 조회 함수와 생성·전송 함수를 이름과 interface에서 분명히 구분한다.
- Calendar 생성과 Discord 전송은 중복 호출에 안전하도록 idempotency 기록을 사용한다.
- 테스트 코드가 실제 Discord 채널이나 Calendar에 전송하지 않게 한다.
- 티켓 구매, 결제, 응모 제출, CAPTCHA 우회 기능은 구현하지 않는다.

## 테스트

- 실제 네트워크 없이 fixture와 mock response로 테스트한다.
- 성공 응답뿐 아니라 timeout, 401, 403, 404, 429, 5xx, 잘못된 JSON을 다룬다.
- provider response를 내부 model로 변환하는 경계 테스트를 둔다.
- 외부 API 버전이나 응답 schema 변경 시 관련 fixture와 호출부 호환성을 확인한다.

