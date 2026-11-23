# 조회 API 변경·검증 기록

현재 계약은 [조회 API](../../read-api.md)를 따른다. 2026-11-23 `read-api-v2.md`를 `read-api.md`로 바꾸며 날짜별 결정·검증 문단을 이 문서로 옮겼다. 수치와 상태는 각 기록 시점의 값이다.

## 2026-09-18 이전 DB 성능

기존 2026-09-18 성능 결과는 이전 DB 기준 기록으로 web/docs/qa.md와 당시 측정 산출물에 남아 있으며 새 DB 성능으로 해석하지 않는다.

## 2026-09-20 신규 카탈로그 조회 전환

임시 로컬 PostgreSQL로 빈 DB, 없는 리소스, 한국어/별칭 검색, 페이지 total, 참여자별 통계, 날짜 미정, 보관/비공개 제외, 앨범/녹음/가사 연결을 검증했다. 프론트 단위 테스트 24개와 PC·모바일 HTTP fixture 테스트 2개가 통과했다. 실제 Neon 읽기 전용 점검에서 노출 아티스트 68명 및 라이브·통계·공연·검색·앨범 경로의 200 응답을 확인했다. 레코드 추가·수정·재수집은 수행하지 않았다.

## 2026-09-22 `/api` 통합

새 사용자 프론트 `web/`의 실제 모드가 신규 통합 DB를 `/api`로 조회하도록 전환했다. X/Discord runtime도 같은 DB 전용 코드이며 기존 DB router는 정상 app에서 마운트하지 않는다. 기존 `/spotify/artists/.../discography` 및 `/spotify/albums/...` 소비는 새 앨범 경로로 교체했고 사용자 웹은 기존 songs 가사 조회를 호출하지 않는다.

## 2026-09-24 원문 아티스트 검색

임시 로컬 PostgreSQL fixture로 song_id가 없는 `ヨルシカ` 원문을 `요루시카`·영문명·별칭으로 검색하고, 가창 아티스트 이름 검색·페이지 total/순서·기존 조회 경로를 검증했다. 실 DB 읽기 전용 조회에서 `요루시카` 검색은 5회 중간값 약 176ms(50건 반환, total 4166), 아티스트 목록은 약 152ms였다. 이 수치는 직접 DB 호출 시간이며 브라우저 전체 로딩 시간은 아니다. DB 변경은 수행하지 않았다.

## 2026-10-02 곡 별칭 검색

disposable 로컬 PostgreSQL·provider mock 기반 백엔드 테스트 58개와 프론트 HTTP fixture/통계 단위 테스트 16개 통과. 전체/부분/대소문자 검색, 별칭 중복과 페이지 total/순서, 같은 제목의 다른 곡·미연결·보관된 곡 제외, 비공개/삭제 영상 제외, HTTP 응답 계약, 가창 횟수·순위 보존과 LIKE 특수문자 처리를 확인했다. 추가 migration은 없다.

실제 신규 DB 읽기 전용 검증에서 `요나가우타`와 `영원한 밤의 노래`는 각각 곡 1149의 가창 36건을 반환했고 HACHI 통계의 해당 곡(23회)에 두 별칭이 포함됐다. 변경 전후 첫 페이지 SQL의 EXPLAIN ANALYZE를 교대로 3회 실행한 중앙값은 별칭 검색 98→106ms, HACHI 검색 141→139ms, `夜` 검색 124→135ms, HACHI 곡 통계 SQL 306→311ms였다. 별칭 검색에서 별칭 테이블은 SQL당 한 번 검사됐다. 통계는 곡별 집계 후 별칭을 조회한다. DB 실행 시간이며 네트워크·전체 API 응답·브라우저 렌더링이나 동시 부하를 측정한 값은 아니다. 기존 검색어에서도 측정 변동이 있어 모든 환경의 지연을 보장하지 않는다. 운영 DB 데이터·schema·인덱스·수집 상태는 변경하지 않았다. 서버 배포는 수행하지 않았다.

## 2026-10-06 통계 곡 드릴다운

`GET /api/search`에 `artist_id`와 `song_key`를 추가했다. Verification on 2026-10-06: frontend build passed; backend adapter unit tests 12 passed; desktop browser drilldown 1 passed. PostgreSQL fixture tests 12 skipped because the local PostgreSQL fixture server is unavailable. A separate read-only live catalog check confirmed scoped results, out-of-range pagination totals, and ordinary unscoped search; no collection or data writes were performed. Deploy both API and frontend to enable this feature on the public site.

## 2026-11-14 생방송 목록

`GET /api/streams`(`Page[LiveStreamRead]`)를 추가했다. 이후 프로필·시간 표시 확장으로 `avatar_url`, `avatar_variants`, `status`, `scheduled_at`, `include_upcoming`을 추가했다.

## 2026-11-15 생방송 수집 주기와 Holodex

- 사용자 지정: YouTube 경로의 새 방송·예약 방송 검색 30분(`YOUTUBE_LIVE_DISCOVERY_SECONDS=1800`), 알고 있는 예정/진행 방송 상태 확인 1분(`YOUTUBE_LIVE_CHECK_SECONDS=60`).
- Holodex 연결 및 사용자 지정 주기 변경: `HOLODEX_API_KEY`가 있으면 Holodex 전용 monitor가 `HOLODEX_POLL_SECONDS=3600`(1시간)마다 전체 조회한다. 마지막 성공 시각과 다음 확인 시각을 모두 검사하므로 기존 1분 기한이나 프로세스 재시작 때문에 한 시간 이내 다시 조회하지 않는다.
- 후속 사용자 지정: 전체 목록 검색 1시간은 유지하고, 생방송이 있거나 예정 시각이 된 채널을 `HOLODEX_LIVE_CHECK_SECONDS=180`(3분)마다 추가 확인한다.
- 할당량 유예 보완: `quotaExceeded`/`dailyLimitExceeded`를 고정 24시간 대신 미국 태평양 자정 다음 1분까지 기다리도록 바꿨다. 기존 DB에 기록된 `retry_at`은 자동 단축하지 않는다. fixture 검증은 생방송 monitor·YouTube adapter·멀티뷰 관련 45개 통과, 로컬 PostgreSQL 의존 39개 skip이다. 운영 읽기 전용 확인에서는 전체 활성 139채널에 유예가 걸려 있고 최근 15분 관측이 0개여서 운영 방송 목록이 비어 있었다. provider 오류 로그는 확보하지 못했으므로 실제 할당량 오류 여부는 추정이며 운영 배포·DB 유예 변경·실제 재수집은 수행하지 않았다.
- 할당량 산정 참고(당시 활성 139채널 기준): 30분마다 모두 조회하면 playlistItems 호출만 이론상 일 6,672회이며, 상태 묶음/최초 채널 조회와 아카이브 수집이 추가된다.

## 2026-11-15 오리지널 장르·분위기

`GET /api/explore/music-tags`와 오리지널 곡의 `genres,moods` 필터를 추가했다. 상세는 [음악 분류](../../original-music-tags.md)를 따른다.
