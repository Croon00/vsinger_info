# 새 카탈로그 통합 조회 API

2026-09-22 기준. 새 사용자 프론트 `web/`의 실제 모드는 **신규 통합 DB**를 `/api`로 조회한다. X/Discord runtime도 같은 DB 전용 코드이며 기존 DB router는 정상 app에서 마운트하지 않는다.

## 연결과 실행

프로젝트 루트의 `.env` 또는 환경변수 `DATABASE_URL`을 사용한다. 정상 API·worker와 같은 신규 통합 DB 설정이며, 접속 문자열은 브라우저로 보내지 않는다. 설정이 없거나 연결이 실패하면 503을 반환하고 기존 DB 또는 목업으로 대체하지 않는다.

```powershell
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
# 다른 터미널에서
cd web
npm run dev
```

API는 기본 8000, 프론트는 http://localhost:5174 이다. `web/.env.local`의 `BACKEND_URL`로 API 주소를 변경한다. 선택적 `API_KEY` 인증은 유지하며 Vite 서버의 `BACKEND_API_KEY`로 전달한다. 운영 배포에는 별도의 동일 출처 /api 프록시가 필요하다.

새 카탈로그 조회는 `app/db/catalog_session.py`의 공유 연결 풀과 요청별 **READ ONLY 트랜잭션**을 사용한다. 마이그레이션·초기화·수집·번역·외부 API 요청을 수행하지 않는다. SQL은 `app/repositories/catalog_read.py`, 응답 조합은 `app/services/catalog_read.py`, HTTP 경계는 `app/api/routers/read_api.py`에 있다.

## HTTP 계약

목록 페이지는 `{items,total,offset,limit}`, offset 0~100000, limit 1~100이다. 없는 상세는 404, 잘못된 범위는 422, DB 연결 실패는 503이다. 빈 DB/관계는 정상적인 빈 목록·0 통계를 반환한다. `Server-Timing`은 SQL 처리 시간과 쿼리 수를 제공한다.

| 경로 (`/api` 아래) | 응답과 기준 |
| --- | --- |
| GET /artists | 보관되지 않았고 show_in_catalog=true인 통합 명부. 원어 이름 오름차순+ID. 전체 목록 |
| GET /artists/{id} | 동일 노출 조건의 아티스트. 기존 DB ID/이름 기반 병합 없음 |
| GET /artists/{id}/lives | 대표·출연·가창 연결로 참여한 아카이브. 방송일/공개일 내림차순+ID, 세트리스트 곡 목록 없이 활성 곡 수 `performance_count`를 포함한 요약 |
| GET /lives/{id} | 아카이브와 영상, ordinal+ID 순 세트리스트 |
| GET /artists/{id}/statistics | 가창자 ID에 따른 곡·원곡 아티스트 순위와 월별 활동량 |
| GET /search?q=... | 원어/한국어/영문 곡명, 원곡 아티스트 이름·별칭, 미매칭 원문 OR 검색. 날짜 내림차순+아카이브+ordinal+ID |
| GET /concerts | 보관/취소 제외 공연. artist_id, start(포함), end(제외) 선택 필터 |
| GET /concerts/{id} | 공연·도시·장소·출처 링크·첫 티켓 정보 |
| GET /artists/{id}/albums | DB에 등록된 참여 앨범. 발매 연월일 내림차순+ID |
| GET /albums/{id} | 앨범과 디스크/트랙 순 수록 녹음, 가사 존재 여부 |
| GET /recordings/{id}/lyrics | 해당 녹음의 저장된 가사·번역·독음과 출처 URL |

기존 `/spotify/artists/.../discography` 및 `/spotify/albums/...` 소비는 새 앨범 경로로 교체했다. 사용자 웹은 기존 songs 가사 조회를 호출하지 않는다. 구 Spotify·songs router는 정상 app에서 마운트하지 않는다.

## 필드와 식별자

- 기존 프론트 DTO의 `name`은 artists.name_native, `display_name`은 name_ko, `name_latin`은 영문 이름이다. 별칭은 artist_aliases에서 읽는다. DTO 이름 `spotify_image_url`은 호환을 위해 남겼지만 실제 값은 artists.avatar_url이다.
- 생일은 확인된 월·일만 MM-DD로 전달한다. 한국어 이름·생일을 추정하지 않는다. 상징색은 응답에 포함하며 캘린더의 실제 색상 적용 디자인은 별도 범위다.
- 외부 링크는 artist_external_accounts와 external_accounts의 연결을 사용한다. collection_enabled=false여도 등록된 공개 링크를 표시하며, 보관된 계정은 제외한다.
- 원곡자는 song_artists, 실제 가창자는 performance_artists로 구분한다. 여러 원곡자는 순서대로 이름을 연결하고 첫 가창자를 검색 결과 대표로 표시한다.
- 앨범/트랙/녹음/곡 ID는 서로 다르다. 프론트는 가사 버튼에 recording_id를 사용한다. Spotify ID나 song_id를 가사 ID로 대신 사용하지 않는다.
- 발매일은 저장된 연·월·일 정밀도를 보존한다. EP 등 앨범 종류도 유지한다.
- 프론트 즐겨찾기는 `schedule-music-api:catalog-v1-favorites`로 분리한다. 기존 ID 자동 승계는 하지 않으며 기존 테마·캘린더 설정은 유지한다.

## 집계·공개 기준

- 보관된 아카이브/영상과 private/deleted 영상은 제외한다. public/unlisted/unknown은 저장된 가용성 그대로 조회하며 외부 플랫폼을 확인하러 가지 않는다. 새 DB는 검수된 라이브 관계를 사용하므로 기존 420초 길이 필터는 적용하지 않는다.
- 활동량/방송 수는 아티스트가 참여한 아카이브를 한 번씩 센다. 월은 Asia/Seoul, 미래/날짜 미정은 그래프에서 제외한다.
- 가창 통계는 performance_artists에 해당 아티스트가 연결된 performance만 센다. 출연만 했다는 이유로 다른 사람의 모든 가창을 포함하지 않는다. 가창자가 미연결된 세트리스트는 상세에 보이지만 개인 통계에는 포함하지 않는다.
- 곡은 song_id 기준이다. 미매칭 곡만 원문 제목+원문 아티스트의 소문자·양끝 공백 정리 값으로 임시 구분한다. 같은 제목의 다른 곡 ID를 합치지 않는다.
- 공동 원곡자는 각 명의에 횟수를 부여하므로 원곡 아티스트 비율 합계가 100%를 넘을 수 있다. 비율 분모는 전체 가창 횟수다. 미등록 원곡자는 순위에서 제외한다.
- 순위는 동률 공동 순위(1,1,3). 통계 고유 곡/아티스트 집계는 전체를 전달하고 프론트에서 검색·정렬·10개씩 페이지 처리한다.
- 공연은 starts_at의 시간대를 보존하고, 시각 미정이면 event_date만 전달한다. 날짜도 미정이면 빈 문자열로 반환해 프로필에는 날짜 미정으로 표시하고 달력에서는 제외한다.
- 공연 범위 필터는 정확한 시각이면 한국시간 날짜, 날짜만 있으면 event_date 기준이다. 프로필은 온라인 공연도 표시하고 캘린더는 오프라인/복합만 표시한다.
- 여러 출연자의 공연은 artist_ids를 함께 반환한다. 해당 아티스트별 조회에는 그 아티스트를 대표로 표시하고, 캘린더 즐겨찾기 필터는 전체 참여 ID를 확인한다.
- 여러 티켓 창은 현재 상세 UI가 하나만 지원해 opens_at·ID 순 첫 창의 URL/가격을 보여준다. 전체 티켓 차수 UI, 공식 커버·노래방 번호·곡 상세 화면은 후속 범위다.

## 검증

2026-09-20: 임시 로컬 PostgreSQL로 빈 DB, 없는 리소스, 한국어/별칭 검색, 페이지 total, 참여자별 통계, 날짜 미정, 보관/비공개 제외, 앨범/녹음/가사 연결을 검증했다. 프론트 단위 테스트 24개와 PC·모바일 HTTP fixture 테스트 2개가 통과했다. 실제 Neon 읽기 전용 점검에서 노출 아티스트 68명 및 라이브·통계·공연·검색·앨범 경로의 200 응답을 확인했다. 레코드 추가·수정·재수집은 수행하지 않았다.

기존 2026-09-18 성능 결과는 이전 DB 기준 기록으로 web/docs/qa.md와 당시 측정 산출물에 남아 있으며 새 DB 성능으로 해석하지 않는다.

## 프로필 이미지

artists 응답에 avatar_variants(128/256/512 URL 객체)를 제공한다. 대표 이미지 필드 spotify_image_url은 호환성을 위해 유지하지만 값은 새 DB의 avatar_url이며 Spotify 조회를 의미하지 않는다. 관리 이미지에만 변형 URL을 제공하고 외부 이미지에는 빈 객체를 반환한다. 요청 중 이미지 다운로드·변환은 하지 않는다. 저장소 연결과 교체 절차는 [프로필 이미지 저장](avatar-storage.md)을 따른다.
