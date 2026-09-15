# 새 프론트 실연동 조사

조사일: 2026-09-16. 대상 프론트: `front-design-draft`.

기존 백엔드의 현재 마운트된 HTTP 라우터, 요청·응답 모델, 응답을 구성하는 코드를 정적으로 대조했다. 서버 실행, DB 연결, 외부 서비스 호출, 기존 프론트 시각 구현 열람은 하지 않았다. 따라서 아래의 **구현됨**은 코드 구현을 의미하며, 운영 DB의 데이터 보유량·정확성, 배포 상태, API 키 설정, 외부 서비스의 실제 성공 여부까지 확인했다는 뜻은 아니다.

## 결론

라이브·세트리스트·디스코그래피·가사는 이미 조회 API가 있다. 전부 새로 개발할 필요는 없다. 다만 현재 mock의 응답을 그대로 반환하는 API는 아니므로 프론트의 데이터 변환 계층이 필요하다.

현재 화면의 기능을 유지하기 위한 주요 백엔드 보완은 **자유어 통합검색, 원어/한국어 이름 계약, 생일·그룹 멤버 데이터, 라이브의 아티스트 ID와 목록 메타데이터**다. 공연은 기존 이벤트 후보 API를 활용할 수 있으며 운영용 노출 규칙과 조회 기능을 보완하는 방향을 권장한다. 로그인과 즐겨찾기 서버 저장은 계정·기기 간 동기화를 도입할 때 필요한 선택 범위다.

## 1. 개발 또는 보완이 필요한 백엔드

| 항목 | 현재 확인한 차이 | 필요한 작업 / 우선도 |
| --- | --- | --- |
| 자유어 통합검색 | `/api/youtube-performances`는 `song_title` 필수. 없으면 400. 곡명 조건과 원곡 아티스트 조건은 AND로 연결된다. 새 프론트는 한 검색어가 이름·곡명·원곡 아티스트 중 어느 하나에 맞으면 결과를 표시한다. | **필수 보완.** `q` 검색을 추가하거나 통합검색 API를 제공한다. 원곡명·한국어 곡명·원곡 아티스트명·한국어명 OR 검색과 아티스트 이름/별칭 검색을 지원한다. 기존 필터 검색 계약은 유지한다. 전체 아카이브를 내려받아 브라우저에서 검색하는 방식은 운영용 대안으로 권장하지 않는다. |
| 이름의 언어 분리 | mock은 `name=원어`, `display_name=한국어`로 사용한다. 백엔드 `display_name`은 `display_artist_name()`이 만드는 표시 이름이며 원어·로마자 혼합일 수 있다. `name` 역시 원어라는 보장이 없다. | **필수 보완.** `name_native`, `name_ko`, `aliases`처럼 의미가 명시된 읽기 응답을 권장한다. 기존 `display_name` 의미를 바꾸지 않고 추가하고, 기존 데이터를 정리한다. 로마자를 한국어 부제목으로 대체하지 않는다. |
| 생일과 그룹 멤버 | 아티스트 API에 생일 필드가 없다. 프론트는 mock의 `birthday: MM-DD`와 `src/lib/dates.ts`의 특정 mock ID에 연결된 멤버 생일을 사용한다. | **현재 캘린더 유지에 필수.** 아티스트 생일 및 멤버 이름·생일·소속 아티스트 ID 조회 계약을 추가한다. 출생 연도 없이 월·일만 저장할 수 있게 하고 윤년 정책을 정한다. 프론트의 멤버 하드코딩을 제거한다. |
| 라이브와 아티스트 연결 | 목록 필터는 `artist_name` 문자열이며 응답에 안정적인 `artist_id`가 없다. 상세도 표시 이름 위주다. 검색 결과는 아티스트 카드로 연결하기 위해 ID가 필요하다. | **안정적인 연동에 우선 보완.** 라이브 목록에 `artist_id` 필터, 목록·상세·세트리스트 검색 응답에 대표 아티스트 ID를 제공한다. 별칭·중복 등록은 `related_artist_ids`와 일관되게 처리한다. 소스 없이 직접 등록된 아카이브의 연결 방법도 정한다. |
| 라이브 목록 메타데이터 | 목록은 `youtube_url`, `video_title`, 방송일, 세트리스트를 반환하지만 `duration_seconds`와 `youtube_video_id`를 명시적으로 선택하지 않는다. 상세는 `y.*`를 반환한다. | **현재 카드 표시 유지에 보완.** 목록에 영상 ID·길이를 추가한다. 영상 ID는 URL에서 변환 가능하지만 길이를 얻기 위해 목록의 모든 상세를 추가 호출하지 않도록 한다. 제목 번역이 없는 항목은 원제 폴백을 허용한다. 명시적 응답 모델도 권장한다. |
| 공연의 사용자용 조회 | `/api/event-candidates` 생성·목록과 상태/아티스트/유형/형식 필터는 있다. 날짜 구간·페이지·상세 ID 조회·수정/검토 HTTP API는 없다. 날짜와 아티스트가 null일 수 있고 `event_format=unknown`도 허용된다. | **기존 API 활용 + 운영 보완.** 초기에는 `live_event`, `ready/synced`, `onsite/hybrid`, 유효한 날짜·아티스트를 선별해 표시할 수 있다. 이후 날짜 범위·페이지·상세 조회와 검토/수정 기능을 추가한다. 후보 테이블 전체를 확정 공연으로 노출하지 않는다. |
| 프로필 이미지 메타데이터 | 아티스트 API에는 `spotify_image_url`이 있으나 mock의 공식 이미지 출처, 크롭 위치, 독립 프로필 이미지 필드는 없다. `official_site` 등 소스는 있다. | **현재 공식 사진을 유지하려면 보완.** `profile_image_url`, 출처 URL, 필요 시 크롭 위치를 제공한다. Spotify 이미지로 대체하는 제품 결정이면 기본 사진 조회는 기존 API로 가능하다. 원본 이미지 없는 아티스트의 폴백도 필요하다. |
| 인증·읽기/관리 권한 | 아티스트·곡·YouTube 라우터는 선택적 `X-API-Key` 보호. 키 미설정 시 통과한다. Spotify 라우터에는 같은 인증 dependency가 없다. 마운트된 웹 OAuth는 Google 연동 시작/콜백이며 사용자 로그인·세션 API가 아니다. | **공개 배포 전 설계 필요.** 공개 읽기와 관리자 변경 권한을 분리하고 보호 방식을 통일한다. 서버 관리용 공용 키를 프론트 번들에 넣지 않는다. 비공개 개인용이면 서버 프록시 등 별도 보호 방식도 가능하다. |
| 즐겨찾기·설정 동기화 | 전용 사용자/즐겨찾기/설정 HTTP API가 없고 프론트는 localStorage를 쓴다. | **선택 개발.** 계정 간 동기화가 필요할 때 사용자 인증, 즐겨찾기 조회/추가/삭제, 설정 저장 API를 추가한다. 기기 내 저장을 유지하면 백엔드 추가 개발 불필요. |

공연 mock에 있는 `city`는 기존 이벤트 응답에 없다. 도시 표기를 유지하려면 추가하되, 초기 연동에서 `venue`만 표시하면 신규 필드 없이 가능하다. 티켓 링크는 기존 `ticket_url`과 출처 `source_url`을 구분해 연결한다. 별도의 Google Calendar 조회 API는 화면 자체의 월간 달력을 그리는 데 필수는 아니다.

## 2. 구현되어 있으나 새 프론트에서 실사용하지 않는 백엔드

현재 `src/main.ts`는 모든 실행에서 MSW를 시작한다. 실제 가사 API와 같은 경로도 mock이 가로챈다. 따라서 아래 API는 모두 **새 프론트 기준 미연동**이다. 기존 프론트의 사용 여부를 조사한 목록은 아니다.

### 현재 화면에 연결할 기존 API

| 새 프론트 기능 | 기존 API | 연결 시 주의점 |
| --- | --- | --- |
| 홈 즐겨찾기·탐색·프로필 | `GET /api/artists`, `GET /api/artists/{id}` | `grouped=true`와 `related_artist_ids`, `name_aliases`를 지원한다. 이름 언어 계약과 이미지 필드는 위 보완 필요. `profile_intro → intro` 등 변환한다. |
| 소속사 필터 | `GET /api/artist-agencies` | 현재 탐색 탭은 RK Music/KAMITSUBAKI를 고정 옵션으로 사용한다. 실데이터 소속사로 교체 가능. |
| 프로필 주요 링크 | `GET /api/artists/{id}/sources` 또는 아티스트 응답의 `sources` | `source_type`에 맞게 X 사용자명과 공식 사이트 URL을 변환한다. 수집 소스와 사용자에게 표시할 주요 링크를 구별한다. |
| 라이브 목록·뷰어 | `GET /api/youtube-lives`, `GET /api/youtube-lives/{archive_id}` | `video_title → title`, `youtube_video_id → video_id` 또는 URL에서 추출. 세트리스트의 `start_seconds`는 그대로 사용 가능. 목록 기본 50, 일반 최대 100. `all_records=true`는 아티스트 이름이 있을 때만 전체 조회. 420초 이하 영상은 현재 목록/검색에서 제외된다. |
| 세트리스트 검색 | `GET /api/youtube-performances` | 곡명/가수/원곡 아티스트 필터는 구현됨. 위의 `song_title` 필수·AND 조건 때문에 mock 통합검색의 직접 대체는 불가. 결과는 중첩 `live/artist`가 아닌 평탄한 응답이다. |
| 검색 필터 후보 | `GET /api/youtube-performance-filters` | performers/original_artists/songs 목록. 현재 검색 화면에는 다중 조건 선택 UI가 없다. |
| 디스코그래피 | `GET /api/spotify/artists/{artist_id}/discography` | 앨범 요약 목록만 반환한다. Spotify 아티스트 미매칭은 409. 출시일 정밀도가 연/월/일로 다를 수 있다. 현재 mock처럼 모든 앨범에 수록곡이 이미 들어 있지 않다. |
| 앨범 수록곡 | `GET /api/spotify/albums/{album_id}` | 앨범 선택 시 지연 조회 권장. 트랙 ID는 Spotify 문자열 ID이며 현재 mock `Track.id: number`와 다르다. `duration_ms`를 표시 문자열로 변환한다. |
| 가사 존재 여부·곡 ID 매핑 | `GET /api/songs/lyrics/by-spotify-tracks?ids=...` | `spotify_track_id → song_id`, `has_lyrics`를 제공한다. Spotify 트랙 ID를 가사 상세의 숫자 song ID로 직접 사용하면 안 된다. |
| 원문·번역·발음 가사 | `GET /api/songs/{song_id}/lyrics` | 현재 경로와 같지만 MSW 사용 중. `needs_review`, 출처 유형/URL을 제공한다. mock 전용 `is_sample`과 실제 가사의 검토 상태는 다른 개념이다. |
| 공연 탭·달력 공연 | `GET /api/event-candidates` | `status_filter`, `artist_id`, `event_type`, `event_format` 지원. 기본 조회에는 후보/무시 상태 등이 섞일 수 있어 필터가 필요하다. 현 프론트의 `event_format !== online`만으로 unknown을 오프라인 처리하면 안 된다. |

### 현재 화면에 대응 UI가 없는 기존 API

| 기능 | 구현된 API | 활용 위치 |
| --- | --- | --- |
| 아티스트 관리 | `POST /api/artists`, `PATCH/DELETE /api/artists/{id}` | 관리자 화면 |
| 소속사·수집 소스 관리 | `POST /api/artist-agencies`, `POST /api/artists/{id}/sources`, `DELETE /api/artists/{id}/sources/{source_id}` | 관리자 화면 |
| 공연 후보 수동 등록 | `POST /api/event-candidates` | 관리자 공연 등록 |
| 라이브 URL 등록·채널 과거 수집 | `POST /api/youtube-lives`, `POST /api/youtube-lives/backfills` | 관리자 수집 도구. backfill은 202 반환, 작업 ID/진행 조회 API는 현재 없음 |
| 세트리스트 메타데이터 수정 | `PATCH /api/youtube-performances/{id}` | 곡명·한국어명·원곡 아티스트명 교정. 현 요청 모델은 타임스탬프 수정 항목을 포함하지 않음 |
| Spotify 아티스트 후보·프로필 | `GET /api/spotify/artists`, `GET /api/spotify/artists/{id}/candidates`, `GET /api/spotify/artists/{id}/profile` | Spotify 등록·매칭 관리 |
| Spotify 동기화·YouTube 자동 연결 | `POST /api/spotify/artists/{id}/sync`, `POST /api/spotify/artists/{id}/youtube-auto-link` | 디스코그래피·영상 데이터 준비 |
| Spotify 노출 관리 | `DELETE /api/spotify/artists/{id}`, `POST /api/spotify/artists/{id}/enable` | Spotify 제외/활성화. 일반 아티스트 삭제와 의미가 다름 |
| 공동 발매 관계 | `GET /api/spotify/relationships` | 아티스트 관계 화면을 추가할 때 선택 활용 |
| YouTube 기반 가사 생성 | `POST /api/songs/from-youtube` | 가사 관리. 현재 새 프론트는 읽기만 제공 |
| Spotify 곡·YouTube 연결 | `POST /api/songs/spotify-track-youtube` | 가사/곡 연결 관리 |
| 작사·작곡·편곡 크레딧 수정 | `PATCH /api/songs/{song_id}/credits` | 곡 정보 관리 |
| Google 계정 연동 | `GET /api/auth/google/start`, `GET /api/auth/google/callback` | Google Calendar 연동 설정을 추가할 때. 웹 사용자 로그인으로 간주할 수 없음 |

`app/api/main.py`의 `_deprecated_router` 자체는 마운트되지 않는다. 다만 Spotify와 Google OAuth 라우터는 그 파일의 함수를 `add_api_route`로 실제 등록한다. 함수 옆의 deprecated 데코레이터만 보고 해당 기능이 비활성이라고 판단하면 안 된다. 새 클라이언트는 호환용 무접두사 경로 대신 `/api` 경로를 사용한다.

Discord 알림 라우팅·수집 worker·Google Calendar 동기화는 이번 네 화면의 직접 HTTP 소비 범위 밖이다. 현재 마운트된 API에는 알림 라우트 관리, 수집 글 목록, 캘린더 동기화 상태 조회 endpoint가 없다. 봇/worker 내부 기능이 존재하는 것과 웹에서 바로 호출 가능한 API가 있는 것은 구분해야 한다.

## 3. 백엔드 신규 개발로 분류하면 안 되는 프론트 연결 작업

1. **mock/real 실행 모드 분리.** MSW를 조건부로 시작하고 기존 Service Worker의 API 가로채기가 남지 않게 전환한다. API base URL, 개발 프록시 또는 운영 동일 출처 라우팅을 설정한다. 현재 Vite에는 백엔드 프록시가 없다.
2. **응답 변환 계층.** mock DTO와 백엔드 응답 차이, null, 날짜 정밀도, 영상 제목 폴백, Spotify 문자열 ID/로컬 숫자 ID를 처리한다. `/api/draft/*` 경로를 그대로 백엔드에 신규 생성할 필요는 없다.
3. **탭별 독립 로딩.** 현재 ArtistPage는 아티스트·라이브·앨범·공연을 `Promise.all`로 묶는다. Spotify 미매칭 409 하나로 프로필 전체가 실패하지 않도록 분리한다. 앨범 상세는 선택 시 가져온다.
4. **실데이터 상태 표시.** 샘플 일정/가사 문구가 현재 오버레이에 무조건 표시된다. mock에서만 표시하고 실데이터에서는 출처·검토 상태를 사용한다. 정보 누락, 401/403/409/503도 구분한다.
5. **mock ID 제거.** 기본 즐겨찾기 `[1,2,3,4,5,6]`을 실 DB ID로 간주하지 않는다. 별도의 저장 키를 사용하거나 검증된 매핑을 적용한다. 멤버 생일의 고정 ID 역시 제거한다.
6. **검색·목록 규모 대응.** 서버 검색 계약과 페이지 처리에 맞춰 프론트를 연결한다. 현재 라이브 더보기는 받은 배열을 잘라 보여주는 방식으로, 서버의 다음 페이지를 가져오지 않는다.
7. **영상 재생 유지.** YouTube IFrame 재생·자동재생 실패 시 음소거 재시도·타임스탬프 이동·썸네일 폴백은 프론트에 이미 있다. 이를 위해 별도 영상 스트리밍 백엔드를 개발할 필요는 없다.

## 4. 권장 진행 순서

1. 원어/한국어 이름, 대표 아티스트 ID, 생일/멤버, 공연 노출 상태의 계약을 확정한다.
2. 자유어 검색과 라이브 ID·목록 메타데이터를 보완한다. 생일 데이터 저장/조회와 필요한 프로필 메타데이터를 추가한다.
3. 기존 아티스트·라이브·Spotify·가사·공연 API를 변환 계층으로 연결한다. 모드 분리, 탭별 오류 격리, mock ID/문구 제거를 같이 처리한다.
4. 실제 데이터로 한국어·원어·원곡 아티스트 검색, 아카이브 페이지, 미매칭 Spotify, 미등록 가사, unknown 공연, 윤년 생일을 검증한다.
5. 배포 대상에 맞게 읽기/관리 권한을 적용한다. 계정 간 동기화가 필요하면 로그인·즐겨찾기·설정 API를 별도 추가한다.

## 후속 기능: 통계 탭 (2026-09-16)

라이브 다음에 통계 탭이 추가되었다. 현재는 mock API로 받은 전체 아카이브의 세트리스트를 프론트에서 집계한다. 실제 연결 시에는 아티스트별 전체 데이터 기준 요약·곡별 횟수/최근 가창일·원곡 아티스트 비율을 반환하는 집계 API를 권장한다. 곡 검색/네 가지 정렬/페이지 조회도 서버에서 처리하되, 필터링된 목록과 별개로 전체 요약·비율을 유지해야 한다. 기존 라이브 API 기본 제한(50개 또는 일반 최대 100개)만 받아 전체 통계로 표시하면 누락이 생긴다. 곡·원곡 아티스트 정규화 ID를 활용하면 텍스트 표기 차이에 따른 중복 집계를 줄일 수 있다.

## 코드 근거

- 프론트 계약/소비: `src/api/client.ts`, `src/api/types.ts`, `src/mocks/handlers.ts`, `src/mocks/search.ts`, `src/main.ts`, `src/pages/ArtistPage.vue`, `src/components/ContentOverlay.vue`, `src/composables/preferences.ts`, `src/lib/dates.ts`.
- 실제 API 등록: `../app/api/main.py`, `../app/api/routers/{artists,youtube,songs,spotify,auth}.py`.
- 요청/응답: `../app/core/models.py`, `../app/schemas/{artists,youtube}.py`, `../app/integrations/spotify.py`의 Pydantic 모델.
- 응답 구성 및 조건 확인: `../app/services/{artist_service,youtube_service,song_service}.py`, `../app/integrations/youtube_live_archive.py`의 목록·상세·검색 함수, `../app/core/artist_identity.py`, `../app/repositories/event_candidates.py`.
- 인증: `../app/core/security.py` 및 각 라우터 dependency.
