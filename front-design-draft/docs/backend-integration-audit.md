# 새 프론트 실연동 재조사

후속 변경: 2026-09-18 성능 개선으로 조회 전용 v2가 추가되었다. 이 문서의 기존 API 조사는 연결 당시 기록이며, 현재 프론트 경로와 지원 범위는 [조회 API v2](read-api-v2.md)가 우선한다.

조사일: 2026-09-18. 확인한 실제 루트는 `D:\06_Dev\schedule_music`이다. 이 문서는 2026-09-16 조사를 대체한다.

현재 마운트된 라우터, 서비스, 응답 모델을 다시 대조했다. 백엔드 실행·DB 연결·변경 및 기존 `web`의 시각 구현 열람은 하지 않았다. 코드에 존재하는 API와 가동 중인 서버에서 검증한 API는 구분한다.

## 이전 조사와 달라진 점

- `/api/youtube-performances`에서 `song_title`은 이제 선택값이다. 원곡 아티스트만으로 검색할 수 있다. 곡명 검색과 원곡 아티스트 검색을 각각 실행하고 결과를 합쳐 현재 통합검색을 연결했다.
- `/api/youtube-performance-stats`가 존재한다. 전체 가창 데이터의 상위 200개 집계로, 아티스트 필터·최근 가창일·페이지가 없어 상세 페이지 통계의 직접 대체는 아니다.
- `/api/youtube-covers`가 존재한다. 공식 채널의 커버 업로드 목록이며 현재 라이브 아카이브 UI와는 다른 범위다.
- 프론트 기본 실행은 실제 API이며, 디자인 목업은 별도 모드로 분리했다. 실제 모드에서 목업 데이터로 실패를 감추지 않는다.

## 서버 주소

상위 `.env`의 `PUBLIC_BASE_URL`은 비어 있으며 Google 콜백은 `http://127.0.0.1:8000/auth/google/callback`이다. 별도 API 서버 주소·포트는 확인되지 않았다. 조사 당시 로컬 8000번 `/health`에 연결하지 못했다. 콜백 값이 서버 가동을 증명하지는 않는다.

프론트 `.env.local`의 `BACKEND_URL`로 실제 주소를 지정한다. 기본값은 `http://127.0.0.1:8000`이다. 필요하면 서버 전용 `BACKEND_API_KEY`를 개발 프록시에 설정한다. 상위 `.env` 전체를 복사하거나 DB 주소를 HTTP API 주소로 사용하지 않는다. 실행법은 [README](../README.md)에 있다.

## 현재 연결한 기존 API

| 기능            | HTTP 계약                                                                         | 연결 방식과 제한                                                                                                                    |
| --------------- | --------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| 아티스트·프로필 | `GET /api/artists?grouped=true`, `/api/artists/{id}`                              | 대표/관련 ID·별칭·Spotify 이미지·소속사·소개·활성 소스 활용. 소속사 필터는 데이터로 구성.                                           |
| 이름            | `name`, `display_name`, `name_aliases`                                            | display_name은 한국어 전용이 아니다. name을 표시하고 나머지는 검색 별칭으로 사용. 한국어를 임의 생성하지 않음.                      |
| 라이브 목록     | `GET /api/youtube-lives?artist_name=...&all_records=true`                         | 기본 50/일반 최대 100개 제한 대신 아티스트별 전체 조회. 이름·별칭의 유일한 정확 일치로 연결하여 부분 일치 충돌 제외.                |
| 라이브 상세     | `GET /api/youtube-lives/{id}`                                                     | URL에서 영상 ID 추출, 세트리스트·타임스탬프 연결. 길이 없으면 배지 생략. 방송일 없으면 공개일, 모두 없으면 날짜 미정.               |
| 통합검색        | `GET /api/youtube-performances?song_title=q`, `?original_artist=q`                | 서로 다른 필터는 AND이므로 별도 요청 후 performance ID로 중복 제거. 각 최대 500개 도달 시 일부 결과일 수 있음을 표시.               |
| 통계·활동량     | 전체 라이브의 performances                                                        | 조회되어 해당 아티스트로 확인된 데이터로 계산. 서버가 제외하는 420초 이하 영상과 연결 불명확 항목은 포함하지 않음.                  |
| 앨범            | `GET /api/spotify/artists/{id}/discography`                                       | 요약만 조회. 미연결 409는 오리곡 탭에 격리.                                                                                         |
| 수록곡          | `GET /api/spotify/albums/{id}`                                                    | 선택한 앨범만 지연 조회. 문자열 트랙 ID·디스크/트랙 순서·발매일 정밀도 유지.                                                        |
| 가사 ID 매핑    | `GET /api/songs/lyrics/by-spotify-tracks?ids=...`                                 | Spotify 문자열 ID를 숫자 song_id로 변환. 최대 50개씩 요청.                                                                          |
| 저장된 가사     | `GET /api/songs/{song_id}/lyrics`                                                 | 원문·번역·발음·출처·검토 상태. 생성 요청 없음.                                                                                      |
| 공연·달력       | `GET /api/event-candidates?event_type=live_event&status_filter=ready` 및 `synced` | 합친 목록에서 onsite/hybrid, 유효한 날짜·등록 아티스트만 표시. 날짜만 있거나 offset 없는 값은 날짜만 사용하고 시간을 추정하지 않음. |
| 생일            | API 없음                                                                          | 실제 모드에서 생일 필터와 생성 제외.                                                                                                |
| 즐겨찾기·설정   | 계정 저장 API 없음                                                                | 로컬 저장 유지. 실제/목업 저장 키 분리, 실제 기본 즐겨찾기 비움.                                                                    |

## 개발·보완이 필요한 백엔드

- 아티스트·그룹 멤버의 생일 저장 및 조회.
- 원어/한국어/기타 별칭의 명확한 언어 계약. 곡과 원곡 아티스트의 기존 `_ko`는 활용 가능.
- 라이브·검색의 안정적 artist_id 응답/필터. 이름만으로는 모든 별칭과 중복 이름 연결을 보장할 수 없음.
- 검색의 페이지·전체 건수와 자유어 OR 계약. 기존 필터로 초기 연결은 가능하므로 신규 검색 API를 선행 조건으로 삼지 않음.
- 공연 기간·페이지·상세 조회, 시간대 포함 ISO 날짜, 도시 정보.
- 대규모 데이터를 위한 아티스트별 통계·월별 활동량·곡/아티스트 순위 페이지 조회.
- 라이브 목록의 영상 길이, 독립 프로필 이미지, 그룹 대표와 Spotify 매칭 ID의 일관성.
- 공개 읽기 권한과 관리 권한 분리. 라이브 상세 GET의 한국어 메타데이터 보완·저장 부작용을 순수 조회와 분리.

구체적인 우선순위·완료 조건은 [TO-DO](backend-todo.md)에 정리했다. 미지원 기능을 가상 데이터로 보충하거나 백엔드에 새로 구현하지 않았다.

## 구현되어 있으나 현재 화면에서 사용하지 않는 API

| API 또는 기능                                             | 미사용 이유 / 활용 위치                                                 |
| --------------------------------------------------------- | ----------------------------------------------------------------------- |
| `GET /api/youtube-performance-stats`                      | 전체 상위 200개 집계이며 현재 아티스트별 통계와 기준이 다름.            |
| `GET /api/youtube-covers`                                 | 커버 업로드 화면을 추가할 때 활용. artist_id/collaborator_id 필터 있음. |
| `GET /api/youtube-performance-filters`                    | 다중 조건 검색 UI의 후보 목록. 현재는 자유어 검색.                      |
| `GET /api/artist-agencies`                                | 현재는 조회된 아티스트의 소속사만 필터에 사용.                          |
| 아티스트·소속사·소스 POST/PATCH/DELETE                    | 관리자 등록/수정 UI.                                                    |
| `POST /api/event-candidates`                              | 관리자 공연 후보 등록.                                                  |
| `POST /api/youtube-lives`, `/api/youtube-lives/backfills` | 영상 등록·과거 수집. backfill은 202 응답, 작업 진행 조회 계약 없음.     |
| `PATCH /api/youtube-performances/{id}`                    | 세트리스트 메타데이터 교정. 타임스탬프 수정은 현재 요청 모델 미지원.    |
| Spotify 아티스트 목록·후보·프로필 조회                    | 등록·매칭 관리.                                                         |
| Spotify sync·youtube-auto-link·enable·exclude             | 관리자 데이터 준비·노출 설정. 페이지 방문으로 실행하지 않음.            |
| `GET /api/spotify/relationships`                          | 공동 발매 관계 화면.                                                    |
| songs/from-youtube·spotify-track-youtube·credits 변경     | 가사 생성·곡 연결·크레딧 관리.                                          |
| Google auth/start·callback                                | Google Calendar 계정 연동. 웹 사용자 로그인 기능과 다름.                |

Discord 라우팅·수집 worker·Google Calendar 동기화는 이번 네 화면의 직접 HTTP 소비 범위 밖이다. 내부 기능이 존재하는 것을 웹용 HTTP API 제공으로 간주하지 않았다.

## 조사·검증 근거

- 실제 등록: `../app/api/main.py`, `../app/api/routers/{artists,youtube,songs,spotify,auth}.py`. `_deprecated_router` 자체는 미마운트지만 Spotify/Google 라우터가 main 함수를 add_api_route로 등록한다.
- 모델: `../app/core/models.py`, `../app/schemas/{artists,youtube}.py`, `../app/integrations/spotify.py`.
- 응답 구성: `../app/services/{artist_service,youtube_service,song_service}.py`, `../app/integrations/youtube_live_archive.py`, `../app/core/artist_identity.py`, `../app/repositories/event_candidates.py`.
- 인증/설정: `../app/core/security.py`, `../app/core/config.py`, `.env` 주소 관련 항목.
- 연결: `src/api/{backend,backend-types,http,client,config}.ts`, `vite.config.ts`, `src/main.ts`와 화면 리소스 로더.
- `tests/unit/backend.test.ts`, `tests/integration/backend.spec.ts`는 현재 계약을 재현한 응답으로 검증한다. 실제 DB 데이터 품질과 가동 중인 API 검증은 남아 있다.
