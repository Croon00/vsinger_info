# 보완 4단계 결과 — 등록된 Spotify 계정 수집

실행일: 2026-09-23. [서비스 보완 계획](backend-service-readiness-plan.md)의 D단계다. 신규 DB에 이미 등록된 활성 Spotify 계정의 고정 ID만 입력으로 사용해 앨범·녹음·트랙 관계를 신규 정규화 모델에 저장한다. admin-web, 기존 DB, 이름 검색, 자동 계정 등록, 가사·번역·독음·노래방 호출은 경로에 없다.

## 경로와 입력

`music_jobs`의 `spotify_collect` handler → `services/spotify_collection.py` → `integrations/spotify_catalog.py` → `repositories/spotify_collection.py`로 실행한다. 별도 migration은 필요하지 않다. 기존 `albums`, `album_artists`, `recordings`, `recording_artists`, `recording_external_ids`, `album_tracks`, `catalog_imports`를 사용한다.

등록·선점·수집 직전·저장 시 `external_accounts(platform=spotify, collection_enabled=true, archived_at IS NULL)`와 입력의 22자 고정 ID를 대조한다. `artist_external_accounts.relationship=owner`로 연결된 활성 아티스트가 없으면 provider를 호출하지 않는다. 다른 발매 명의도 **각각 등록·활성인 Spotify 계정의 owner 관계와 provider의 실제 ID 크레딧**이 함께 있어야 연결한다. 미등록 계정이나 이름이 비슷한 아티스트는 생성·활성화·추측 연결하지 않는다.

자동 주기 수집은 추가하지 않았다. 명시적으로 입력한 작업이 Spotify 앨범 목록을 KR 시장 기준 최대 10개씩 가져오고 `album_offset`을 10씩 늘린 후속 작업을 DB에 원자 등록한다. 앨범의 트랙은 페이지당 50개, 최대 4페이지를 가져온다. 페이지나 트랙 수가 불완전하면 해당 작업을 실패 처리해 부분 앨범을 저장하지 않는다. 앨범 목록은 최대 offset 1000까지 허용하며, 상한 도달 시 조용히 완료하지 않는다. 모든 HTTP 호출은 30초 timeout과 기본 최소 1초 간격을 적용한다. 429·일시적인 5xx·timeout은 안전한 작업 재시도로, `Retry-After`는 다음 시도 시각에 반영한다. 이 한도는 실제 계정 규모와 quota를 확인해 운영 전 재검토한다. [Spotify의 아티스트 앨범 API](https://developer.spotify.com/documentation/web-api/reference/get-an-artists-albums)는 페이지 크기 상한 10과 `include_groups`/`market` 입력을 명시한다.

다음은 **검증 전용** 로컬 입력 예다. 등록은 `validate` 대신 `enqueue`를 사용하고 cutover guard를 통과해야 한다. `request_run`을 바꾸면 명시적 재수집으로 기록한다.

```json
{
  "job_type": "spotify_collect",
  "external_account_id": 1,
  "payload": {
    "spotify_artist_id": "ssssssssssssssssssssss",
    "request_run": "initial",
    "link_youtube": false
  }
}
```

```powershell
.\.venv\Scripts\python.exe scripts/music_jobs.py validate --request .\spotify-request.json
```

실제 작업은 계정 관계가 확인되고 worker가 켜진 뒤 `enqueue --request`로 요청한다. 이 문서 작성 중 실제 계정 요청이나 provider 호출은 수행하지 않았다.

## 저장과 보존

- `albums.spotify_album_id`와 `recording_external_ids(platform=spotify,external_id)`로 중복을 막는다. 같은 트랙 ID가 여러 신규 앨범에 있으면 녹음 한 행을 재사용하고 각 `album_tracks` 관계만 만든다.
- Spotify album의 실제 크레딧은 `album_artists`, 각 트랙의 실제 크레딧은 `recording_artists`에 등록 계정 관계 범위에서만 연결한다. 앨범 크레딧에 없는 피처링 아티스트도 트랙 크레딧이 있으면 해당 아티스트의 앨범 조회 목록에 나타난다.
- `recordings.song_id`는 미확정이면 NULL로 둔다. 가사·번역·독음과 노래방 번호를 새로 만들지 않는다.
- 기존 앨범·녹음의 제목, 한국어 표기, 작품·공식 영상 연결, 가사, 아티스트·트랙 관계, 수동 제외 상태는 재수집으로 덮어쓰지 않는다. 재수집 결과와 변경 충돌은 검토 후보로 남긴다. 새 앨범/녹음에만 자동 관계를 만든다.
- 원본 앨범·트랙 응답, 적용·보류 이유와 작업 범위는 같은 transaction의 `catalog_imports` 영수증에 보존한다. 영수증에는 인증 토큰을 넣지 않는다. 계정/소유 관계가 조회와 저장 사이에 달라지면 적용하지 않는다.

## 선택적 공식 영상 연결

`link_youtube=true`인 명시적 작업만 YouTube 후보를 확인한다. 대상 아티스트와 owner 관계로 연결된 **활성 YouTube 채널이 정확히 하나**일 때 그 채널 안에서만 찾는다. 새 녹음 중 한 작업에서 최대 20트랙을 확인하며 채널·곡명·공식 영상 표시를 검증한다. 후보가 없거나 여러 개면 연결을 보류하고 후보 ID를 영수증에 남긴다. 기존 녹음의 수동 연결 또는 빈 연결은 변경하지 않는다. 대상 채널이 없거나 여러 개면 검색하지 않고 그 사유를 영수증에 남긴다. 다른 계정 소유의 기존 영상과 충돌해도 연결하지 않고 충돌 사유를 기록한다. 상한 때문에 보류된 트랙도 영수증에 표시하며 승인 없이 자동으로 광범위한 재검색을 시작하지 않는다.

이 선택 기능은 신규 Spotify 계정에서 시작한 작업 범위 안에서만 작동한다. 구 `spotify_youtube.py`의 구 DB SQL/이름 검색을 호출하지 않는다. Spotify 링크는 조회 API에 공식 Spotify URL로 노출되며, 앨범 커버 URL은 provider 원본 그대로 저장한다. [Spotify 앨범 API](https://developer.spotify.com/documentation/web-api/reference/get-an-album)와 [앨범 트랙 API](https://developer.spotify.com/documentation/web-api/reference/get-an-albums-tracks)의 응답 범위에 맞춰 구현했다.

## 검증과 다음 단계

일회용 로컬 PostgreSQL과 가짜 Spotify/YouTube 응답으로 등록·비활성·보관·ID 불일치 계정의 provider 호출 0, 공동 발매 크레딧, 미등록 공동 명의 제외, 피처링 앨범 조회, 재수집 중복 0, 수동 수정·가사 보존, 페이지 재개, 429/timeout, 선택적 공식 영상 연결, 실제 `/api/artists/{id}/albums`와 `/api/albums/{id}` 응답을 검증했다. 실제 Spotify API·운영 DB·Railway는 사용하지 않았다. 2026-09-23 전체 `python -m pytest -q -p no:cacheprovider`: **300 passed**, 374 warnings, 132.04초. 경고는 기존 FastAPI/Starlette의 deprecated API 사용이다. 이후 채널 미등록·기존 영상 소유권 충돌의 보류 사유를 보완했고 Spotify 관련 fixture **32 passed**, 51 warnings, 19.05초로 다시 검증했다. `git diff --check`도 통과했다.

`/ready`는 worker가 활성화된 경우 YouTube API key 및 Spotify client ID/secret의 누락을 변수 **이름만** 표시한다. 준비 상태가 참이어도 실제 provider의 권한·quota·네트워크와 운영 데이터의 매핑은 다음 단계에서 확인해야 한다.

다음은 **보완 5단계**의 이전 pending 작업/payload 정합성, 설정 통합, legacy 경계 정리다. 이후 보완 6단계에서 실제 서비스 통합 검증·운영 전환을 준비한다.
