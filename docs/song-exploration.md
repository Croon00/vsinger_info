# 곡 탐색

최종 확인 2026-11-23. 날짜별 결정·검증·실데이터 수치는 [곡 탐색 이력](records/backend/song-exploration-history.md), 그룹 오리지널 MV 등록 작업은 [2026-11-01 기록](records/data/duo-original-mv-2026-11-01.md)에 있다.

탐색 화면의 곡 탭은 우타와꾸 곡·커버 곡·오리지널 곡을 소속사·아티스트·검색어·기간으로 조회한다. 조회는 읽기 전용이며 provider·LLM·Discord·Calendar를 호출하지 않는다. 오리지널 곡의 장르·분위기 태그(`genres`, `moods`, `music_tag_sources`)는 [음악 분류](original-music-tags.md)를 따른다.

## 화면과 URL 상태

탐색의 아티스트/곡 탭은 URL `view=artists|songs`로 전환하며 아티스트 탐색의 검색·정렬 값과 분리한다. 곡 탭은 소속사, 정렬, 곡 이름 검색, 24개씩 더보기를 지원하고 다음 URL 값으로 선택을 보존한다.

| URL 값 | 내용 |
| --- | --- |
| `kind` | 곡 종류 |
| `song_agency` | 소속사 |
| `song_order` | 정렬 |
| `song_q` | 검색어 |
| `song_artists`(반복) | 선택한 아티스트 |
| `song_start`, `song_end` | 영상 등록 기간(커버·오리지널) |

새로고침·정렬·검색·더보기에 같은 필터를 전달한다.

## HTTP 계약

모든 경로는 `/api` 아래이며 임시 `/api/v2` 별칭에서도 제공한다. 기존 조회 API와 같이 `API_KEY`가 설정된 환경에서만 키를 요구한다. 응답에는 `Server-Timing`(SQL 시간·쿼리 수)과 `Cache-Control: private, no-store`를 붙인다.

### GET /api/explore/songs

예: `GET /api/explore/songs?kind=utawaku&agency=all&q=&order=high&offset=0&limit=24`

| 파라미터 | 값 |
| --- | --- |
| `kind` | `utawaku`(기본), `cover`, `original` |
| `order` | `high`(기본), `low`, `latest`, `name` |
| `agency` | `all`(기본), `independent`, 소속사 원어명(1~200자) |
| `q` | 최대 200자. 원어·한국어 곡명과 아티스트 원어·한국어·영문 이름 및 별칭 부분 검색 |
| `offset`, `limit` | 0~100000, 1~100(기본 24) |
| `artist_ids` | 반복. 양의 정수 최대 100개, 중복 제거 |
| `start`, `end` | `YYYY-MM-DD`. 커버·오리지널의 영상 등록일 범위 |
| `genres`, `moods` | 반복. 오리지널 전용([음악 분류](original-music-tags.md)) |
| `published_only` | bool, 기본 false. 커버·오리지널 전용 |

- 검색어는 우타와꾸에서 부른 아티스트와 확인된 원곡 가수, 커버에서 공식 채널 소유 아티스트, 오리지널에서 등록된 가창 명의에 적용한다. 오리지널은 대체 곡명도 검색한다. 검색어에 맞는 곡을 찾되 곡별 횟수는 소속사 범위 전체 집계다. SQL wildcard 문자는 리터럴로 처리한다.
- `artist_ids`: 커버·오리지널은 소속사 범위 내 연결 명의 중 선택한 아티스트가 하나라도 있는 곡을 조회한다. 명의 전체를 먼저 집계한 뒤 선택 여부를 판정하므로 같은 소속사의 협업 아티스트 표기를 잃지 않으며, 같은 영상이 여러 선택에 해당해도 한 번만 표시한다. 우타와꾸는 선택한 아티스트들의 가창 기록을 먼저 제한한 뒤 곡별 부른 횟수·가창자 수·최근 날짜를 집계한다. 같은 듀엣 가창은 여러 명을 골라도 한 번만 센다. 선택하지 않으면 해당 소속사 전체다.
- `start`, `end`: `published_at`의 한국 시간 날짜 기준이며 양 끝을 포함한다. 한쪽만 지정할 수 있다. 영상 등록일이 없는 항목은 날짜 필터가 있을 때 제외한다. 우타와꾸 세트리스트의 방송일 범위와 구분한다.
- `published_only=true`: 유효한 YouTube 영상 ID(11자 영문·숫자·밑줄·하이픈)가 있고 `published_at <= CURRENT_TIMESTAMP`인 행만 고른다. 게시일 미확인·미래 게시일·영상 없는 음원은 제외한다. 최신순은 기존 `published_at DESC NULLS LAST, key`를 유지한다([011](../specs/011-home-recent-songs/spec.md)).
- 모든 필터는 정렬·총 개수·페이지 계산 전에 적용한다.
- 422: 잘못된 열거값·범위·bool, 역전된 날짜 범위, 우타와꾸에 영상 날짜나 `published_only` 지정, 오리지널 이외에 `genres`·`moods` 지정.

응답은 `Page[SongExploreRead]`(`items,total,offset,limit`)다. 항목은 `key,title,title_ko,artist_name,youtube_video_id,view_count,views_updated_at,performance_count,artist_count,archive_id,start_seconds,published_at`과 오리지널 태그 필드다. 해당되지 않거나 확인되지 않은 수치는 null이다.

### GET /api/explore/song-performers

`GET /api/explore/song-performers?song_key=song:1&agency=all`은 해당 곡을 부른 전체 아티스트를 `id,name,display_name`으로 반환한다. `song_key`는 `song:<id>` 또는 `raw:<32자리 소문자 MD5>`다. 첫 세트리스트 페이지에 없는 아티스트도 선택지로 제공한다.

### 우타와꾸 리스트의 복수 가창자·방송 날짜 필터

우타와꾸 '리스트 열기'와 홈 검색은 `/search` 화면에서 `GET /api/search`를 사용한다. 기존 행·썸네일·영상 시점 이동을 재사용하며 곡 탐색에서는 `song_key`, 선택한 `artist_id`·`artist_ids`, `agency`를 전달해 페이지 계산 전에 필터한다. 홈의 일반 검색 동작은 유지한다.

- 반복 `artist_ids`(양의 정수 최대 100개): 선택한 가창자 중 누구라도 포함된 가창 기록의 합집합이며 협업 가창은 중복 반환하지 않는다. 기존 단일 `artist_id`와 함께 전달하면 교집합이다. 선택이 없으면 가창자 제한을 해제한다.
- `start`, `end`(`YYYY-MM-DD`): `COALESCE(live_archives.broadcast_at, videos.published_at)`의 한국 시간 날짜로 비교하고 양 끝을 포함한다. 한쪽만 지정할 수 있다. 커버·오리지널의 영상 등록일과 구분한다.
- 이 조건은 정렬·총 개수·페이지 계산 전에 적용한다. 역전된 범위·잘못된 날짜·잘못된 ID는 422다.

`GET /api/search/performers?q=...&agency=all&artist_id=...`는 곡 키가 없는 홈 검색의 가창자 선택지다. 기존 검색과 같은 제목·별칭·원곡자·가창자 일치 범위에서 활성 공개 아티스트를 중복 없이 반환하며 페이지 제한이 없다. 선택한 가창자와 날짜 필터로 선택지 자체를 줄이지 않는다. 곡 키가 있으면 `/api/explore/song-performers`를 사용한다.

## 표시와 집계

### 우타와꾸

- 확인된 `song_id`별로 묶는다. 미연결 곡은 정규화한 원문 곡명+원곡 아티스트 키로만 묶으며 동일 제목만으로 서로 다른 작품을 합치지 않는다.
- 원곡 아티스트 이름을 확인된 곡 명의 또는 원문에서 얻을 수 없는 묶음은 목록에서 제외한다.
- 가창 횟수는 `DISTINCT performances.id`이며 복수 가창자 때문에 같은 공연을 중복 집계하지 않는다. 가창자 명의가 없을 때만 라이브의 대표 아티스트를 사용한다.
- 소속사는 가창자의 현재 등록 소속사로 필터한 뒤 집계한다.
- '리스트 열기'는 곡 고유 키·소속사·선택한 `artist_ids`를 유지해 홈 검색과 같은 세트리스트 화면으로 이동한다.

### 커버

- 영상 한 개당 한 항목이다. 제목에 명시된 cover/covered/covers·歌ってみた·カバー·커버를 근거로 사용하고, 설명만의 홍보 문구나 歌唱 크레딧은 분류 근거로 사용하지 않는다. 셀프 커버도 제외한다.
- 과거 오분류 후보를 삭제하지 않고 동일 제목 기준으로 조회에서 제외한다.
- 소속사 범위는 업로드 공식 채널의 현재 owner 관계다. 채널 소유자가 확정된 가창자라는 뜻은 아니며 임의로 참여자를 생성하지 않는다.
- VESPERBELL·KMNZ 커버는 [공유 채널과 멤버 표시](shared-youtube-channels.md)를 적용한다. 멤버 이름 검색에는 명시적 솔로·협업·미표기 합창 구분을 사용하며 전체 곡 목록에서는 같은 영상을 한 번만 표시한다.

### 오리지널

- 등록된 발매 음원(`recordings`)을 버전별로 표시한다. 여러 앨범에 수록돼도 동일 recording은 한 항목이다.
- 같은 YouTube 영상에 연결된 recording은 정렬·총 개수·페이지 계산 전에 한 항목으로 묶는다. 다른 영상과 영상 미연결 recording은 별도로 유지하며 원본 발매 연결은 변경하지 않는다.
- 공식 영상이 `covers`에 있고 현재 제목 기준으로도 커버인 항목만 제외한다. 과거 설명만으로 만들어진 cover 후보 때문에 정상 발매 음원을 숨기지 않는다. 나머지 발매곡의 커버 여부는 모두 검수된 상태가 아니므로 화면에 미확정 곡 포함 안내를 표시한다.
- 소속사는 등록된 발매 아티스트를 따른다.

### 오리지널 곡의 그룹 표시

오리지널 곡 탭의 목록 명의와 아티스트 선택지는 다음 그룹 단위로 통일한다.

| 그룹 | 멤버 |
| --- | --- |
| VESPERBELL | ヨミ·カスカ |
| KMNZ | LITA·TINA·NERO |
| HONK THE HORN | MOCO·BAMBI |
| NUROJUNK | KAGURA·SAKUYA |

- `app/repositories/original_song_groups.py`의 명시적 slug 규칙과 활성 `artist_group_members`(`left_on IS NULL`) 관계를 함께 확인하며 동명이인(예: 神楽めあ)을 포함하지 않는다. YouTube 계정 유무와 무관하게 읽기 표시 대상으로 사용한다.
- 오리지널 곡에서만 적용한다. 발매곡의 표시 명의·소속사·선택 필터는 그룹 기준이며 그룹명/멤버명 검색을 지원한다. 원본 recording·명의·소유권은 수정하지 않는다.
- 그룹과 멤버 크레딧이 같은 영상에 함께 있어도 영상 ID 중복 제거를 유지한다. 이전 URL의 멤버 ID로도 해당 그룹 범위를 조회할 수 있다. 협업 상대의 명의는 유지한다.
- `GET /api/artists`와 상세 응답에 nullable `original_song_group: {id,name,agency}`를 제공한다. 프론트는 오리지널 탭에서 이 값으로 선택지를 그룹 ID별 중복 제거하고, 커버·우타와꾸에서는 개인 선택지를 사용한다.
- 조회수·영상 등록일·날짜 범위·정렬·페이지 계약은 다른 곡과 같다.

### 공통

- 보관 처리된 아티스트·공연·영상·곡은 제외한다. 영상은 공개·일부공개·미확인 상태를 허용한다.
- YouTube 링크가 없는 발매곡도 목록에 남기며 조회수는 `—`로 표시한다.
- 커버·오리지널 목록의 조회수 아래 날짜는 해당 YouTube 영상의 `published_at`이며 '등록'으로 표시한다. 영상 등록일이 없으면 생략한다.
- YouTube 조회수와 확인일을 함께 표시하며 실시간 수치로 안내하지 않는다. Spotify 재생 수는 사용하지 않는다.

### 정렬

| 종류 | 기본 | 그 밖의 정렬 |
| --- | --- | --- |
| 우타와꾸 | 부른 횟수 내림차순(`high`) | 오름차순, 최근 부른 순, 곡 이름 순 |
| 커버·오리지널 | YouTube 조회수 내림차순(`high`) | 오름차순, 최신 영상 순, 곡 이름 순 |

조회수 미확인은 양방향 모두 마지막이다. 동률은 곡 제목과 고유 키로 결정한다. 최신 영상 정렬은 연결된 YouTube 영상의 게시일이며 발매일 정렬로 표기하지 않는다.

## Shorts 제외

곡 탐색과 아티스트 커버 탭은 같은 Shorts 표시 규칙을 사용한다.

- 명시적인 Shorts 제목 표식과 저장된 `is_short=true` 항목은 제외한다.
- 180초 초과 영상 또는 일반 영상으로 확인된 항목을 표시한다. 180초 이하·길이 미확인 항목은 형식 확인 전까지 대기하며 화면에 대기 정책을 안내한다.
- 길이만으로 짧은 일반 커버를 Shorts라고 확정하거나 원본을 삭제하지 않는다.

형식 확인 방법은 아래 [운영 도구](#shorts-형식-확인)를 따른다.

## 화면 동작

### 홈과 아티스트 화면에서의 사용

- 홈 최근 곡: `kind=original`과 `kind=cover`를 각각 `order=latest&offset=0&limit=10&published_only=true`로 조회한다.
- 홈 즐겨찾기 캐러셀: 같은 API에 즐겨찾기 아티스트 ID(`artist_ids`)와 `published_only=true&limit=10&order=latest`를 전달한다. 즐겨찾기가 비어 있으면 전체 조회로 대체하지 않는다.
- 아티스트 `?tab=originals`: `kind=original&artist_ids=ID`로 앨범 없는 녹음·영상 미연결 녹음까지 24곡씩 표시하며 `published_only`를 쓰지 않는다.
- 오리지널 일일 수집이 만든 새 녹음·영상도 같은 계약으로 조회한다([오리지널 일일 수집](youtube-original-collection.md)). 모든 요청은 조회 전용이다.

### 아티스트 복수 선택

- 우타와꾸·커버·오리지널 모두 아티스트 복수 선택을 표시한다. 선택한 소속사에 속한 공개 아티스트를 가나다순으로 제공하며, 개인세는 agency가 없는 명의다. '소속사 전체'이면 공개 아티스트 전체를 선택할 수 있다.
- 선택지는 첫 곡 페이지가 아닌 전체 아티스트 카탈로그를 사용한다.
- 소속사 또는 곡 종류를 바꾸면 선택을 초기화한다. '아티스트 전체'도 선택을 해제한다.
- 목록 조회·필터는 수집을 시작하지 않는다.

### 기간 필터

- 곡 탐색은 `BroadcastPeriodFilter`를 '영상 등록 기간'으로 사용하고, `/search` 화면은 같은 컴포넌트를 '방송 기간'으로 사용한다. 우타와꾸 탭에서는 영상 등록 기간을 숨기고 API에 전달하지 않는다.
- 프로젝트 프리셋의 shadcn-vue RangeCalendar·Popover를 사용한다. 한국어 달력에서 시작일/종료일을 연속 선택하고 '적용'할 때 두 URL 값을 함께 변경한다. 선택 중에는 조회를 시작하지 않으며 취소·ESC는 기존 기간을 유지한다.
- 연도/월 바로 이동, 최근 30일·90일·이번 달·올해, 전체 기간 복귀를 지원한다. 선택한 기간은 버튼에 표시하고 새로고침해도 유지한다. 더보기·정렬·아티스트 선택·소속사 변경에도 기간을 유지한다.
- 버튼은 줄어들지 않고 필터는 줄바꿈한다. 팝오버는 화면 너비·가용 높이 안에서 표시·스크롤해 모바일에서 적용 버튼이 화면 밖으로 밀리지 않게 한다.

### /search 화면

- URL의 반복 `artist_ids`, `start`, `end`에 필터를 보존한다. 빈 결과에서도 조건 변경·초기화가 가능하며 잘못된 날짜 범위는 요청 전에 안내한다.
- 원곡 아티스트 선택은 현재 불러온 결과에 적용하는 단일 필터다.

### 영상 재생

- 커버·오리지널 곡 제목은 연결된 YouTube 영상이 있으면 현재 화면의 Dialog에서 재생한다. 모바일 inline 재생과 autoplay를 요청하며 원문 YouTube 링크도 유지한다.
- 제목과 아티스트를 표시하고 닫기·Escape·배경 클릭으로 닫는다. 닫거나 탐색 조건을 바꾸거나 페이지에서 벗어나면 iframe을 제거해 재생을 중단한다.
- 영상 미연결 제목은 재생 버튼으로 만들지 않는다. 자동 재생·퍼가기 허용 여부는 브라우저·YouTube 정책을 따른다.

## 운영 도구

### 조회수 갱신

```powershell
.venv\Scripts\python.exe scripts/refresh_youtube_video_statistics.py
```

- 신규 DB identity 검증 후, 기존 커버 또는 발매 음원에 연결된 YouTube 영상 중 업로드 source 계정이 있고 최근 24시간 안에 갱신하지 않은 영상을 최대 10,000개 선택한다.
- `videos.list(part=snippet,statistics)`를 최대 50개씩 최소 2초 간격으로 호출하며 한 실행은 최대 200개 API 요청이다.
- 채널 ID가 기존 업로드 계정과 같은 응답만 저장하며 기존 소유권을 변경하지 않는다. source 계정이 없거나 API가 반환하지 않는 영상은 수치를 추정하거나 다른 계정에 귀속시키지 않는다.
- Pydantic으로 검증한 `view_count`, `channel_id`, `captured_at`을 collection state의 `youtube_video_statistics` namespace에 영상 ID별로 저장한다. 다른 namespace·lease·cursor는 유지한다.
- 페이지 단위 트랜잭션이며 재실행은 24시간 안의 완료 항목을 건너뛴다. 실패한 요청은 무제한 재시도하지 않고 안전한 원인 코드로 종료한다. 키·DB URL은 출력하지 않는다.
- 주기적 자동 갱신 작업은 등록돼 있지 않다. 신규 수집 영상이 늘면 같은 명령을 다시 실행해 미확인 조회수를 보충한다.

### Shorts 형식 확인

```powershell
.venv\Scripts\python.exe scripts/classify_youtube_cover_formats.py
```

- 신규 DB의 기존 커버 중 대상 최대 10,000개를 조사한다. 제목 표식은 먼저 저장한다.
- 나머지는 YouTube robots.txt 허용 여부를 검사한 뒤 공개 `/shorts/{video_id}` URL에 HEAD 요청을 보낸다. HTML 200 응답은 Shorts, 같은 영상 `/watch?v=`로의 리디렉션은 일반 영상으로 기록한다. 동의·알 수 없는 리디렉션은 미확인으로 보존한다.
- 403·429·서버 오류는 중단하며 CAPTCHA·로그인·차단을 우회하지 않는다. 요청 간 1초 이상 쉬고 영상·음성·player API·비공개 browse API를 요청하지 않는다.
- 현재 YouTube 공개 URL 동작에 의존하는 판별이며 YouTube Data API의 공식 Shorts 플래그가 아니다.
- `collection_states.provider_state.youtube_video_formats`에 영상 ID별 판별·근거·확인일만 저장한다. 다른 namespace를 보존하고 20개 단위로 저장해 재실행 시 완료 대상을 건너뛴다. 미확인은 24시간 후 다시 확인할 수 있다. 중단되면 같은 명령으로 재개한다.

### 검수된 오리지널 MV 등록

`scripts/import_reviewed_original_videos.py <manifest>`는 검토된 manifest의 공식 MV를 허용된 publisher 채널에 한해 recording과 명의로 등록한다. 반복 적용은 `already_applied`로 건너뛴다. 모든 신규 오리지널이 주기적으로 자동 분류되는 것은 아니다. 실행 예와 결과는 [2026-11-01 기록](records/data/duo-original-mv-2026-11-01.md)에 있다.

## 이력

날짜별 기능 추가·검증·실데이터 수치는 [곡 탐색 이력](records/backend/song-exploration-history.md)을 따른다.
