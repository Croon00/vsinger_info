# 조회 API

최종 확인 2026-11-23. 사용자 프론트 `web/`이 신규 통합 DB를 읽는 조회 전용 HTTP 계약이다. 날짜별 결정과 검증 결과는 [변경·검증 기록](records/backend/read-api-history.md)에 있다.

## 연결과 실행

프로젝트 루트의 `.env` 또는 환경변수 `DATABASE_URL`을 사용한다. 정상 API·worker와 같은 신규 통합 DB 설정이며 접속 문자열은 브라우저로 보내지 않는다. 설정이 없거나 연결이 실패하면 503을 반환하고 기존 DB나 목업으로 대체하지 않는다.

```powershell
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
# 다른 터미널에서
cd web
npm run dev
```

API는 기본 8000, 프론트는 http://localhost:5174 이다. `web/.env.local`의 `BACKEND_URL`로 API 주소를 바꾼다. `API_KEY`가 설정된 환경에서는 모든 `/api` 경로가 `X-API-Key`를 요구하며(`/health`·`/ready` 제외), Vite 서버가 `BACKEND_API_KEY`로 전달한다. 운영 배포에는 별도의 동일 출처 `/api` 프록시가 필요하다.

조회는 `app/db/catalog_session.py`의 공유 연결 풀과 요청별 **READ ONLY 트랜잭션**을 사용한다. 마이그레이션·초기화·수집·번역·외부 API 요청을 하지 않는다. SQL은 `app/repositories/catalog_read.py`, 응답 조합은 `app/services/catalog_read.py`, HTTP 경계는 `app/api/routers/read_api.py`에 있다. 같은 라우터를 숨김 별칭 `/api/v2`에도 마운트하며, 구 Spotify·songs 등 기존 router는 마운트하지 않는다.

## 공통 규칙

- 목록 페이지는 `{items,total,offset,limit}`이며 `offset` 0~100000, `limit` 1~100이다. 기본 `limit`은 경로마다 다르다(라이브·커버 12, 검색 50, 생방송·공연 100).
- 없는 상세나 노출하지 않는 아티스트는 404, 잘못된 범위·열거값·날짜는 422, DB 연결 실패는 503이다.
- 빈 DB/관계는 정상적인 빈 목록·0 통계를 반환한다.
- `Server-Timing` 헤더로 SQL 처리 시간과 쿼리 수를 제공하고, `Cache-Control: private, no-store`로 캐시하지 않는다.

## 경로

| 경로 (`/api` 아래) | 응답과 기준 |
| --- | --- |
| GET /artists | 보관되지 않았고 show_in_catalog=true인 통합 명부. 원어 이름 오름차순+ID. 전체 목록. `spotify_genres`는 [아티스트 Spotify 장르](artist-spotify-genres.md) |
| GET /artists/{id} | 동일 노출 조건의 아티스트. 기존 DB ID/이름 기반 병합 없음 |
| GET /artists/{id}/lives | 대표·출연·가창 연결로 참여한 아카이브. 방송일/공개일 내림차순+ID, 세트리스트 없이 활성 곡 수 `performance_count`를 포함한 요약 |
| GET /artists/{id}/covers | 공식 채널 커버. [YouTube 커버](youtube-covers.md) |
| GET /lives/{id} | 아카이브와 영상, ordinal+ID 순 세트리스트 |
| GET /artists/{id}/statistics | 가창자 기준 곡·원곡 아티스트 순위와 월별 활동량. 곡의 `searchText`는 이름·곡 별칭·원곡자 검색용 문자열. `titleKo`·`artistKo`, 원곡 아티스트 순위의 `nameKo`는 저장된 한국어 이름이며 없으면 null |
| GET /search?q=... | 아래 [검색](#검색) |
| GET /search/performers?q=... | 전체 검색 결과의 공개 가창자 선택지. [곡 탐색](song-exploration.md) |
| GET /explore/songs, /explore/song-performers | 우타와꾸·커버·오리지널 곡 탐색. 홈 최근 곡·즐겨찾기 캐러셀·아티스트 오리지널 탭도 이 경로를 쓴다(`published_only`). [곡 탐색](song-exploration.md) |
| GET /explore/music-tags | 오리지널 장르·분위기 태그. [음악 분류](original-music-tags.md) |
| GET /streams, /stream-groups | 아래 [생방송 멀티뷰](#생방송-멀티뷰) |
| GET /concerts | 보관/취소 제외 공연. `artist_id`, `start`(포함), `end`(제외) 선택 필터 |
| GET /concerts/{id} | 공연·도시·장소·출처 링크·첫 티켓 정보 |
| GET /artists/{id}/albums | 앨범 명의(album_artists) 또는 수록 녹음의 가창 명의(recording_artists)로 연결된 앨범. 발매 연월일 내림차순+ID. `is_primary`는 해당 아티스트가 앨범 명의에 있으면 true, 트랙 명의로만 연결된 참여 발매면 false |
| GET /albums/{id} | 앨범과 디스크/트랙 순 수록 녹음, 가사 존재 여부, `youtube_url`(연결된 공개/일부 공개 영상만, 없으면 null). 아티스트 기준이 없으므로 `is_primary`는 null |
| GET /recordings/{id}/lyrics | 해당 녹음의 저장된 가사·번역·독음과 출처 URL. 등록 절차는 [가사 등록](original-lyrics.md) |

## 검색

`GET /api/search`는 원어/한국어/영문 곡명·곡 별칭, 아카이브 대표·가창 아티스트 이름·별칭, 원곡 아티스트 이름·별칭, 미매칭 원문을 OR로 검색한다. 정렬은 날짜 내림차순+아카이브+ordinal+ID이며 결과에는 영상 시점 재생 링크가 있다.

다음 선택 필터는 모두 페이지 계산 전에 적용한다.

- `artist_id`: 해당 아티스트가 `performance_artists`로 연결된 가창만. 통계 화면의 곡 드릴다운에 사용한다.
- `song_key`: `song:<id>` 또는 `raw:<32자 소문자 MD5>`. 아티스트 통계와 같은 곡 식별자다. 통계의 곡 제목은 `/search?q=...&artist_id=...&song_key=...`로 연결하고, 날짜가 있는 결과는 `/lives/<archive>?t=<seconds>`로 연다. 홈의 일반 검색은 범위 제한이 없다.
- `agency`, 반복 `artist_ids`(합집합), `start`·`end`(한국 시간 방송일, 양 끝 포함): [곡 탐색의 필터 계약](song-exploration.md)을 따른다.

검색은 이름·별칭에 맞는 아티스트와 곡 별칭에 맞는 활성 곡 ID를 각각 한 번 찾고, 조건에 맞는 세트리스트 ID를 페이지로 자른 뒤 표시 필드를 조회한다. `total`과 정렬은 전체 일치 결과 기준이며, 여러 별칭이 일치해도 같은 가창 기록을 중복 반환하지 않는다.

## 생방송 멀티뷰

### 조회

`GET /api/streams?offset=0&limit=100&include_upcoming=false`는 `Page[LiveStreamRead]`를 반환한다.

- 항목: `account_id`, `channel_id`, `artist_id`, `artist_name`, `avatar_url`, `avatar_variants`, `video_id`, `title`, `status`(`live`/`upcoming`), `started_at`(예정 방송은 null), `scheduled_at`, `checked_at`.
- 기본은 생방송만 반환한다. `include_upcoming=true`이면 생방송(시작 내림차순) 다음에 예정 방송(예정 시각 오름차순)을 붙인다. 생방송끼리는 시작 시각 내림차순·계정 ID·영상 ID순이다.
- 채널을 여러 아티스트가 공유하면 대표 아티스트(owner 우선·is_primary·position·ID) 하나로 표시한다. 아티스트 이미지는 저장된 프로필/해상도 variant를 쓰며 이미지 수집을 시작하지 않는다.
- 데이터는 `collection_states.provider_state.youtube_live_snapshot`의 방송 배열이다. 활성 YouTube 계정이 공개 카탈로그 아티스트에 연결돼 있으면 조회한다. `youtube_live_only`로 등록한 계정은 멀티뷰에서 수집하고, 카탈로그에서 숨긴 활성 소유 그룹도 멀티뷰에 표시할 수 있다. 미래 관측은 제외한다. [멤버십 채널 등록 기록](records/data/multiview-membership-channels-2026-11-24.md)
- 유효 시간: 생방송은 `live_checked_at`(없으면 `checked_at`)부터 15분이며 응답의 `checked_at`도 이 시각이다. Holodex 예정 방송은 전체 조회 `checked_at`부터 75분(수집 간격 60분+유예 15분)이다. 그 밖의 YouTube 관측은 15분이다.
- 시작 시각이 없는 예정 방송은 예정 시각이 지나도 실제 시작이 확인될 때까지 `upcoming`으로 유지한다.
- API는 수집·외부 요청·DB 변경을 시작하지 않는다.

`GET /api/stream-groups`는 `{key,name,kind,account_ids}[]`를 반환한다.

- `kind`는 `agency` 또는 `group`, `key`는 `agency:ID`/`group:ID`다.
- 활성 수집 계정과 공개 아티스트의 명시적 연결만 사용한다. 그룹 멤버는 `artist_group_members`의 `left_on IS NULL` 연결이며, 이 조건만으로 실제 현재 재적 여부를 검증했다고 간주하지 않는다.
- 그룹 자체 채널과 멤버 채널을 모으되 같은 계정 ID는 중복하지 않는다. 숨김/보관된 그룹은 제외하고, 방송이 없는 그룹도 선택지에 남긴다.
- 정렬은 kind·이름·key 순이다.

프론트는 `/multiview`에서 최대 4개 공식 YouTube 플레이어와 선택한 방송의 공식 채팅 iframe을 쓴다. 채팅 `embed_domain`은 현재 hostname이며 YouTube 모바일 웹 채팅 임베드는 지원하지 않는다. 외부 재생 제한·자동재생 정책·채팅 비활성화·브라우저 로그인 제한은 원본 링크로 안내한다.

### 수집 (Holodex 모드)

서버 전용 `HOLODEX_API_KEY`가 있으면 전용 monitor가 Holodex를 사용하고 YouTube API로 자동 fallback하지 않는다.

| 설정 | 기본값 | 동작 |
| --- | --- | --- |
| `HOLODEX_POLL_SECONDS` | 3600 (허용 60~3600) | 공개 아티스트의 활성 YouTube 채널 ID를 50개씩 묶어 `GET https://holodex.net/api/v2/users/live`(`X-APIKEY` 헤더)로 전체 생방송·예정 방송 조회 |
| `HOLODEX_LIVE_CHECK_SECONDS` | 180 (허용 180~3600) | 현재 생방송이 있거나 예정 시각이 된 채널만 같은 경로로 묶어 상태 확인. 대상이 없으면 요청하지 않음 |

- 전체 조회는 마지막 성공 시각과 다음 확인 시각을 모두 검사하므로 프로세스를 재시작해도 주기 안에 다시 조회하지 않는다. 채널은 최대 500개씩 180초 lease로 claim하며, 기한·lease·재시도는 `provider_state.holodex_live_monitor`에서 관리해 YouTube 할당량 유예와 분리한다.
- 결과는 같은 `youtube_live_snapshot`에 `provider=holodex`로 정규화해 저장한다. `status`, `start_actual`, `start_scheduled`를 사용하며 예정 시각만으로 생방송 시작을 추정하지 않는다.
- 상태 확인은 기존 생방송과 예정 시각이 된 영상 ID만 갱신한다. provider가 `live`로 확인한 항목을 `streams`로 옮기고, 아직 `upcoming`이면 제목·예정 시각을 갱신하며, 성공 응답에서 종료·누락된 확인 대상은 목록에서 제거한다. 미래·시각 미정 예정 방송은 유지하고 미등록 영상은 추가하지 않는다. 전체 조회의 `checked_at`·`next_check_at`은 보존하고 `live_checked_at`·`next_live_check_at`만 갱신한다. 두 조회는 같은 provider lease를 쓴다.
- 실패/429/잘못된 응답은 snapshot을 보존하고 해당 주기와 더 긴 `Retry-After`를 존중한다. 성공한 빈 응답은 전체 조회에서는 해당 채널 목록을, 상태 확인에서는 확인 대상만 비운다. Holodex가 추적하지 않는 채널은 나오지 않을 수 있다.
- 반영 지연: 미등록 방송과 예정 시각 전 조기 시작은 최대 약 1시간, 저장된 예정 방송의 시작 확인과 생방송 종료 반영은 약 3분에 provider 지연이 더해진다.
- 원문 영상·채널 ID를 유지하며 아카이브·알림·LLM을 실행하지 않는다. 멀티뷰의 Holodex 링크와 adapter 소스에 [출처와 이용 조건](https://docs.holodex.net/)을 표시한다.

### 수집 (YouTube 모드)

`HOLODEX_API_KEY`가 없을 때 사용한다.

| 설정 | 기본값 | 동작 |
| --- | --- | --- |
| `YOUTUBE_LIVE_DISCOVERY_SECONDS` | 1800 | 새 방송·예약 방송 검색 |
| `YOUTUBE_LIVE_CHECK_SECONDS` | 60 | 알고 있는 예정/진행 방송 상태 확인 |
| `YOUTUBE_POLL_INTERVAL_SECONDS` | 86400 | 일일 아카이브 수집(별개 경로) |

- 전용 loop는 5초마다 DB 기한을 확인하며 worker의 유휴 대기(`WORKER_IDLE_SECONDS`)에 묶이지 않는다. `music_worker_loop`에서 함께 실행되고, 단독 실행은 `python -m app.services.youtube_live_monitor`다. API만 실행하면 수집기는 시작하지 않는다.
- 검색은 채널 uploads playlist를 캐시하고 한 페이지의 최근 10개 ID만 읽는다. 처음 본 ID와 예약/진행 후보 ID를 계정 간 합쳐 `videos.list`로 50개씩 확인한다. 최근 확인한 일반 업로드는 재검사를 생략하고 후보는 종료/비공개/조회 불가까지 추적한다. 최근 창 밖으로 밀려난 예약이나 uploads에 표시되지 않는 영상은 놓칠 수 있다.
- 상태는 `provider_state.youtube_live_monitor`에 보존한다(playlist·최근 ID·후보 ID·다음 기한·180초 lease). 25채널씩 원자적으로 claim하고 네트워크 처리에 150초 제한을 두며, 저장 전에 계정 활성·채널 ID·lease token/만료를 재검사한다. 일일 수집/backfill은 이 namespace와 snapshot을 덮어쓰지 않는다.
- snapshot의 `upcoming`은 `{video_id,title,scheduled_at}` 배열이며 예정 시각은 `liveStreamingDetails.scheduledStartTime` 원문(없으면 null)이다.
- 오류 시 이전 snapshot을 보존하고 재시도한다. `quotaExceeded`/`dailyLimitExceeded`는 [YouTube 일일 할당량 초기화](https://developers.google.com/youtube/data/determine_quota_cost) 시각인 미국 태평양 자정 다음 1분(서머타임 반영)까지, 더 긴 `Retry-After`가 있으면 그만큼 모든 생방송 채널에 유예를 적용한다.
- 할당량: 채널당 uploads 검색 요청이 따로 필요하며 [`playlistItems.list`](https://developers.google.com/youtube/v3/docs/playlistItems/list)와 [`videos.list`](https://developers.google.com/youtube/v3/docs/videos/list)는 요청당 1 unit이다. 30분 주기만으로 총량이 한도 안이라고 보장하지 않으므로 실제 프로젝트 할당량은 별도로 확인한다.
- 알림·LLM·댓글·아카이브/커버 저장을 시작하지 않는다.

## 필드와 식별자

- 프론트 DTO의 `name`은 artists.name_native, `display_name`은 name_ko, `name_latin`은 영문 이름이다. 별칭은 artist_aliases에서 읽는다.
- 아티스트 응답의 `original_song_group`은 `{id,name,agency}` 또는 null이며, 승인된 4개 그룹의 현재 멤버에게 오리지널 곡 탐색의 그룹 선택지를 제공한다. 공개 조건이나 원본 명의는 바꾸지 않는다([곡 탐색](song-exploration.md)).
- 생일은 확인된 월·일만 MM-DD로 전달한다. 한국어 이름·생일을 추정하지 않는다. 상징색은 응답에 포함하며 캘린더의 실제 색상 적용은 별도 범위다.
- 외부 링크는 artist_external_accounts와 external_accounts의 연결을 사용한다. collection_enabled=false여도 등록된 공개 링크를 표시하고 보관된 계정은 제외한다.
- 원곡자는 song_artists, 실제 가창자는 performance_artists로 구분한다. 여러 원곡자는 순서대로 이름을 연결하고 첫 가창자를 검색 결과 대표로 표시한다.
- song_id가 없는 세트리스트도 raw_artist의 정확한 표기가 등록 아티스트의 이름·별칭과 같으면 그 아티스트의 다른 이름·별칭으로 검색한다. 이 조회는 song_id나 원곡자 소유권을 자동 등록하지 않는다.
- 곡 별칭은 `song_aliases.alias`의 대소문자를 구분하지 않는 부분 검색이며 `%`, `_`, `\`는 문자 그대로 처리한다. 활성 `song_id`가 연결된 가창 기록에만 적용하고, 같은 제목의 다른 곡·미연결 기록·보관된 곡으로 확장하지 않는다. 결과의 정식 곡명은 유지한다.
- 앨범/트랙/녹음/곡 ID는 서로 다르다. 가사 버튼에는 recording_id를 사용하며 Spotify ID나 song_id로 대신하지 않는다.
- 발매일은 저장된 연·월·일 정밀도를 보존한다. EP 등 앨범 종류도 유지한다.
- 프론트 즐겨찾기는 `schedule-music-api:catalog-v1-favorites`로 분리한다. 기존 ID 자동 승계는 하지 않으며 기존 테마·캘린더 설정은 유지한다.

## 집계·공개 기준

- 보관된 아카이브/영상과 private/deleted 영상은 제외한다. public/unlisted/unknown은 저장된 가용성 그대로 조회하며 외부 플랫폼을 확인하지 않는다. 새 DB는 검수된 라이브 관계를 사용하므로 기존 420초 길이 필터는 적용하지 않는다.
- 활동량/방송 수는 아티스트가 참여한 아카이브를 한 번씩 센다. 월은 Asia/Seoul이며 미래/날짜 미정은 그래프에서 제외한다.
- 통계 API의 월별 활동량에는 이번 달 누적도 포함된다. 프론트 그래프는 진행 중인 이번 달을 빼고 지난달까지 표시한다. 6M/1Y는 완료된 6개월/12개월, All은 최초 기록 월부터 지난달까지이며, 기록이 없으면 지난달 0건과 빈 상태 안내를 표시한다.
- HONK THE HORN·NUROJUNK 네 멤버의 개인 라이브·통계는 지정 그룹 공식 채널의 비커버 방송으로 제한한다. 커버 표시 규칙은 [공유 YouTube 채널](shared-youtube-channels.md)을 따른다.
- 가창 통계는 performance_artists에 해당 아티스트가 연결된 performance만 센다. 출연만 했다는 이유로 다른 사람의 가창을 포함하지 않는다. 가창자가 미연결된 세트리스트는 상세에 보이지만 개인 통계에는 포함하지 않는다.
- 곡은 song_id 기준이다. 미매칭 곡만 원문 제목+원문 아티스트의 소문자·양끝 공백 정리 값으로 임시 구분한다. 같은 제목의 다른 곡 ID를 합치지 않는다.
- 공동 원곡자는 각 명의에 횟수를 부여하므로 원곡 아티스트 비율 합계가 100%를 넘을 수 있다. 비율 분모는 전체 가창 횟수다. 미등록 원곡자는 순위에서 제외한다.
- 순위는 동률 공동 순위(1,1,3)다. 통계 고유 곡/아티스트 집계는 전체를 전달하고 프론트에서 검색·정렬·10개씩 페이지 처리한다.
- 통계의 `searchText`에는 곡별 집계 후 연결된 활성 곡의 별칭을 붙인다. 실제 모드 프론트의 부른 곡 검색은 기존 문자열 정규화와 부분 검색을 적용하며 별도 요청을 추가하지 않는다. 제목·곡 ID·횟수·순위는 별칭으로 달라지지 않는다.
- 공연은 starts_at의 시간대를 보존하고, 시각 미정이면 event_date만 전달한다. 날짜도 미정이면 빈 문자열로 반환해 프로필에는 날짜 미정으로 표시하고 달력에서는 제외한다.
- 공연 범위 필터는 정확한 시각이면 한국시간 날짜, 날짜만 있으면 event_date 기준이다. 프로필은 온라인 공연도 표시하고 캘린더는 오프라인/복합만 표시한다.
- 여러 출연자의 공연은 artist_ids를 함께 반환한다. 해당 아티스트별 조회에서는 그 아티스트를 대표로 표시하고, 캘린더 즐겨찾기 필터는 전체 참여 ID를 확인한다.
- 여러 티켓 창은 상세 UI가 하나만 지원해 opens_at·ID 순 첫 창의 URL/가격을 보여준다. 전체 티켓 차수 UI, 공식 커버·노래방 번호·곡 상세 화면은 후속 범위다.

## 프로필 이미지

artists 응답에 `avatar_variants`(128/256/512 URL 객체)를 제공한다. 대표 이미지 필드 `spotify_image_url`은 호환성 때문에 이름을 유지하지만 값은 새 DB의 `avatar_url`이며 Spotify 조회를 뜻하지 않는다. 관리 이미지에만 변형 URL을 제공하고 외부 이미지에는 빈 객체를 반환한다. 요청 중 이미지 다운로드·변환은 하지 않는다. 저장소와 교체 절차는 [프로필 이미지 저장](avatar-storage.md)을 따른다.
