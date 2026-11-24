# 아티스트 Spotify 장르 설계

## 구현 경로

YouTube 채널 통계([아티스트 정렬](../../docs/artist-sorting.md))와 같은 구조를 따른다. DB 마이그레이션은 없다.

- 수집: `scripts/refresh_spotify_artist_genres.py` → `app/integrations/spotify_artist_genres.py`(`/artists/{id}` 1회씩, 응답 검증·정규화·재시도) → `app/repositories/spotify_artist_genres.py`(대상 선정·namespace 병합 저장). 기존 `SpotifyCatalogClient`의 토큰·요청 간격(1초)을 재사용한다.
- 대상: 표시 중(`show_in_catalog`)이고 보관되지 않은 아티스트의 owner Spotify 계정. 기본은 수집 활성 계정, `--all-registered`는 비활성 계정까지 포함하되 수집 설정을 바꾸지 않는다. `--account-id`로 계정을 지정한다.
- 조회: `CatalogReadRepository.artists`에 대표 owner Spotify 계정(`is_primary`, `position`, 관계 ID 순)의 lateral join을 추가한다. `ArtistRead`에 두 필드를 추가한다.
- 화면: `web/src/lib/spotify-genres.ts`가 표시 이름을 만들고 `ArtistPage.vue` 프로필의 한국어 이름 아래에 Badge 목록을 둔다. 탐색 카드에는 공간 때문에 표시하지 않는다.

정기 Spotify 수집 worker는 수동 시작 구조라 장르 갱신을 넣지 않았다. 장르 변경 빈도가 낮아 스크립트 갱신으로 충분하다.

## 검증

AsyncMock provider fixture로 정규화·중복 제거·필드 없음·ID 불일치·재시도·건너뛰기를 확인한다. vitest로 표시 이름과 DTO 매핑을 확인한다. 실데이터는 스크립트 실행 결과와 조회 서비스의 읽기 전용 결과로 확인한다.
