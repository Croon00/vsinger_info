# 아티스트 Spotify 장르 표시

작성: 2026-11-24 · 상태: 로컬 구현·실데이터 저장 완료, 배포·화면 검수 남음

## 사용자 시나리오

- US1: 전제 — 아티스트에 Spotify 계정이 등록되어 있고 Spotify가 장르를 제공한다. 동작 — 아티스트 상세에 들어간다. 기대 결과 — 이름 아래에 `Spotify` 표시와 함께 J-Pop·애니송·보카로 같은 장르 칩이 보인다.
- US2: 전제 — Spotify 장르가 비어 있거나 계정이 없다. 동작 — 아티스트 상세에 들어간다. 기대 결과 — 장르 영역을 표시하지 않고 나머지 프로필은 그대로다.

## 요구사항과 완료 조건

- FR-001: 장르는 Spotify가 아티스트 단위로 제공하는 값만 저장한다. 곡의 장르·분위기 태그로 옮기거나 추정하지 않는다([음악 분류](../../docs/original-music-tags.md)와 별개 축).
- FR-002: `collection_states.provider_state.spotify_artist_genres`에 `spotify_artist_id`, `genres`, `captured_at`을 저장한다. 다른 namespace·수집 상태·`collection_enabled`를 바꾸지 않는다.
- FR-003: 갱신은 사용자가 실행하는 스크립트로만 한다. 응답에 `genres` 필드가 없거나 Spotify가 더 이상 제공하지 않는 계정은 기존 값을 유지한다. 일시 오류는 재시도하고 한도를 넘기면 저장 없이 중단한다.
- FR-004: `/api/artists`, `/api/artists/{id}`는 `spotify_genres`(배열, 기본 빈 배열)와 `spotify_genres_updated_at`을 반환한다. 대표 owner Spotify 계정 하나의 값이며 여러 계정을 합치지 않는다. 조회 중 provider를 호출하지 않는다.
- FR-005: 화면은 자주 쓰는 시장 분류만 한국어로 바꾸고(J-Pop, J-Rock, 애니송, 보카로 등) 나머지는 원문을 표시한다. 툴팁으로 아티스트 단위 값임을 알린다.
- SC-001: 기존 아티스트 응답 필드와 정렬을 유지한다.
- SC-002: provider fixture·프론트 단위 테스트·빌드와 실데이터 저장·조회 결과를 기록한다.

근거: 2026-11-24 사용자 요청(Spotify 아티스트 장르를 아티스트 옆에 표시).
