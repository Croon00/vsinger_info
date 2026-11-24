# 아티스트 Spotify 장르

최종 확인 2026-11-24. 요구사항과 검증 기록은 [015-artist-spotify-genres](../specs/015-artist-spotify-genres/spec.md)에 있다.

Spotify가 아티스트 단위로 제공하는 장르(`j-pop`, `anime`, `vocaloid` 등)를 아티스트 상세의 이름 아래에 표시한다. 곡별 장르·분위기([음악 분류](original-music-tags.md))와는 별개이며 곡에 적용하지 않는다. 소규모 아티스트는 Spotify가 장르를 비워 두는 경우가 많다(2026-11-24 표시 대상 75계정 중 8개에 값 있음).

## 저장과 조회

- `collection_states.provider_state.spotify_artist_genres`: `spotify_artist_id`, `genres`(소문자·중복 제거·최대 20개), `captured_at`.
- `/api/artists`, `/api/artists/{id}`: `spotify_genres`(없으면 빈 배열), `spotify_genres_updated_at`. 대표 owner Spotify 계정 하나의 값이며 조회 시 provider를 호출하지 않는다.
- 화면 표시 이름은 `web/src/lib/spotify-genres.ts`에서 정한다(J-Pop, J-Rock, 애니송, 보카로 등). 그 외 값은 원문을 단어별 대문자로 표시한다.

## 갱신

```powershell
.venv\Scripts\python.exe scripts/refresh_spotify_artist_genres.py
.venv\Scripts\python.exe scripts/refresh_spotify_artist_genres.py --all-registered
.venv\Scripts\python.exe scripts/refresh_spotify_artist_genres.py --account-id <ID>
```

- 기본은 표시 중인 아티스트의 수집 활성 owner Spotify 계정, `--all-registered`는 비활성 계정까지 포함한다. `collection_enabled`·앨범 수집 상태를 바꾸지 않는다.
- 계정마다 `/artists/{id}`를 1초 간격으로 요청한다. 일시 오류(5xx·429)는 최대 3회 재시도 후 저장 없이 중단하고, 더 이상 제공되지 않는 계정이나 `genres` 필드가 없는 응답은 기존 값을 유지한다.
- 정기 실행은 없다. 키·DB URL을 출력하지 않는다.
