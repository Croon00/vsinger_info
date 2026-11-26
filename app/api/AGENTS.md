# FastAPI 영역 작업 지침

이 문서는 `app/api/` 아래에서 작업할 때 루트 `AGENTS.md`에 추가로 적용된다.
이 디렉터리는 웹·외부 클라이언트가 사용하는 HTTP API 경계만 담당한다.

## 현재 범위

- `app/api/main.py`는 `routers/read_api.py`를 `/api`와 숨김 별칭 `/api/v2`에 마운트한다. 월드컵과 오리지널 곡의 가사 저장은 `/api`에 마운트한다. 그 밖의 공개 경로는 `/health`, `/ready`다.
- 카탈로그 라우터는 설정된 경우 `X-API-Key`를 검사한다. 가사 쓰기는 별도 `X-Lyrics-Editor-Key`와 대상 녹음의 오리지널 범위를 검증한다.
- `routers/`의 `artists.py`, `songs.py`, `youtube.py`, `spotify.py`, `auth.py`는 마운트하지 않은 보존 코드다. 사용자 요청 없이 다시 마운트하거나 기능을 추가하지 않는다.
- 계약과 페이지·필터·정렬 기준은 [조회 API](../../docs/read-api.md)에 유지한다.

## 경계

- endpoint는 요청 검증과 응답 조립만 하고 업무 처리는 `app/services/`, SQL은 `app/repositories/`에 둔다.
- 조회 요청에서 수집·번역·생성·전송·작업 예약을 시작하지 않는다. 외부 provider를 호출하지 않는다.
- Discord 봇 객체를 import하지 않고 Discord 전송을 수행하지 않는다.
- 기존 `app/core/db.py` 초기화를 호출하지 않는다.

## API 규칙

- 웹용 endpoint는 `/api/` prefix 아래에 둔다.
- 입력과 출력은 Pydantic 모델로 명시하고 내부 DB 컬럼 구조와 분리한다.
- 목록 API는 pagination·필터·정렬을 제공하고 기준을 문서화한다.
- 사용자 입력 오류는 400, 인증 실패는 401, 리소스 없음은 404를 기본으로 한다.
- 토큰·DB URL을 응답이나 로그에 노출하지 않는다.

## 관리 API를 다시 도입할 때

사용자 결정으로 쓰기 API를 추가할 때는 다음을 지킨다.

- 상태를 바꾸는 동작은 GET으로 만들지 않고, 장시간 작업은 요청과 worker 실행을 분리한다.
- 인증된 사용자만 호출하게 하고, `guild_id` 같은 범위 값은 클라이언트 입력을 신뢰하지 않고 접근 권한을 검증한다. Discord 서버 설정 변경은 `manage_guild`를 확인한다.
- 403·409와 다른 서버의 자원 접근 차단을 테스트한다.

## 테스트

- 성공 응답과 400·401·404, 빈 결과, pagination 경계를 테스트한다.
- 외부 X, OpenAI, Google, Discord, YouTube, Spotify 호출은 mock 처리한다.
- 응답 모델 변경 시 `web/`이 사용하는 기존 필드 호환성을 확인한다.
