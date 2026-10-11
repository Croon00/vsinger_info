# Spotify 이름 일치 연결 — 2026-10-11

현재 등록된 아티스트의 디스코그래피를 새 아티스트까지 표시하기 위해 사용자가 명시적으로 요청한 별도 조사·등록 도구다. 기존 조회 화면은 저장된 앨범·트랙을 사용하고 공개 조회 API에서는 provider 수집을 시작하지 않는다. 등록된 계정만 사용하는 기존 Spotify worker 구조도 유지한다.

## 기준과 실행

- 대상: 활성 show_in_catalog 아티스트 중 활성 Spotify 연결이 없는 아티스트. 기존 연결은 교체하지 않는다.
- 검색명: 저장된 name_native, name_latin, name_ko. 임의 로마자·별명은 생성하지 않는다. 비교는 NFKC·양끝 공백·대소문자를 정규화하며 내부 공백이나 기호는 삭제하지 않는다.
- Spotify 공식 artist 검색을 한 페이지 10개, 이름당 최대 10페이지까지 확인한다. 이름 일치 프로필이 하나이고 각 검색이 완료된 경우만 match다. 결과 누락·상한 도달, 여러 동일 이름 프로필은 review이며 미일치는 missing이다. Spotify 검색 결과 범위에서 단일 후보라는 뜻이며 이름만으로 전 세계 동명이인 부재를 보증하지 않는다.
- 기존 계정(보관 계정 포함)은 다른 아티스트에게 자동 재할당하지 않는다. 서로 다른 카탈로그 아티스트가 같은 Spotify 후보를 얻으면 둘 다 보류한다. 이전 skip 검수 이력도 이름 일치만으로 뒤집지 않는다.
- 기본 실행은 신규 DB 읽기 전용·외부 API 조회·로컬 보고서 작성이다. --apply는 사용자 요청 범위에서 단일 후보를 신규 등록하고 collection_enabled=true, owner 연결, catalog_imports/catalog_changes 이력, spotify_collect 작업을 원자 생성한다. 자동 판정 이력은 reviewed=false로 기록한다.
- worker 작업은 link_youtube=false이며 기존 앨범/싱글/참여 발매 및 트랙 크레딧 보존 규칙을 사용한다. 가사·번역·노래방·알림은 실행하지 않는다.
- 토큰·API key는 보고서에 저장하지 않는다. provider 오류는 안전한 코드만 남기고 429/연결/서버 오류가 발생하면 배치 호출을 중지한다. 검색 캐시는 출력 디렉터리에 저장된다. 새 조사는 새 디렉터리를 사용해야 하며 중단한 같은 배치만 기존 캐시로 재개한다.

```powershell
python scripts/discover_spotify_accounts.py --output outputs/spotify-discovery-2026-10-11
python scripts/discover_spotify_accounts.py --apply --run spotify-discovery-2026-10-11 --output outputs/spotify-discovery-2026-10-11
```

로컬 환경의 proxy가 provider 접속을 차단하는 경우에만 --direct-connect를 사용할 수 있다. Railway 환경 설정을 변경하는 옵션이 아니다. 적용 후 등록된 계정은 다음 실행의 조사 대상에서 빠지며 같은 작업은 감사 operation ID와 worker idempotency key로 중복을 방지한다.

공식 계약: [Spotify Search for Item](https://developer.spotify.com/documentation/web-api/reference/search). offset, 최대 limit 10, artist 타입과 market 사용을 확인했다.

## 2026-10-11 검증

### 추가 신원 확인

사용자가 AZKi(995)의 첫 번째 후보 `0HX3yJ7THlqC9drRqhOkgo`를 지정하여 대표 owner 계정으로 연결했다. 두 번째 후보는 연결하지 않았다. receipt 6456, 계정 322, catalog_changes 2개, 최초 수집 작업 83454이며 request_run은 `spotify-confirmed-azki-2026-10-11`이다. collection_enabled=true와 소유권 연결을 실제 DB에서 확인했고 기존 worker 수집을 시작했다.

사용자가 町田ちま의 두 프로필 `2XdS8B1ffoRtHvgk5Ww3oF`와 `4bT3xIkdDQZwmpS5CqrTfU`가 같은 사람임을 확인하여 아티스트 991에 모두 owner로 연결했다. 첫 계정만 대표로 두며 두 계정 모두 수집한다. 동명이인 검색만으로 자동 승인한 것은 아니다.

戌亥とこ(992)는 검색 결과의 프로필 표시명이 `Toko Inui`여서 저장된 이름과 불일치해 missing으로 분류되었다. [공식 음원 안내](https://inui-toko.lnk.to/telescope)의 Spotify 앨범 `1S8NN0gl8SBCJeiBvlPyRM`을 API로 조회해 해당 프로필 `0ne7ErnOjNiUqDxacxTZDn`의 크레딧을 확인하고 연결했다. 추정한 로마자 이름으로 공통 자동 연결 조건을 넓히지 않았다.

추가 적용 receipt 6440: 계정 319–321, owner 연결 3개, catalog_changes 6개, 최초 작업 83387–83389. request_run은 `spotify-confirmed-chima-toko-2026-10-11`이며 기존 Spotify worker로 수집한다. 동일 작업 재적용은 already_applied를 반환했다. 발매 목록은 기존 조회 API에서 한 아티스트 아래 함께 표시한다.

실데이터 중간 검증에서 운영 `/api/artists/991/albums`는 발매 5개, `/api/artists/992/albums`는 발매 10개를 HTTP 200으로 반환했다. 두 町田ちま 계정 모두 collection_enabled=true, owner 관계이며 대표 계정은 하나임을 확인했다. 참여 발매와 누락 발매 보완은 이어서 수집 중이므로 이 개수를 전체 최종 수집 개수로 해석하지 않는다.

초기 실제 신규 DB의 표시 아티스트 103명 중 49명은 활성 Spotify 연결과 저장된 앨범이 있었고 54명은 미연결이었다. 신규 도구로 54명 전체의 provider 검색을 수행했다. 기존 요미의 skip 이력을 보존한 최종 분류는 match 22, review 19, missing 13이다. 보고서는 Git 제외 outputs/spotify-discovery-2026-10-11/에 보존한다. 후보 없음은 실제 발매 없음의 증거가 아니며 저장된 이름 기준 검색에 미일치한 결과다.

자동 테스트: `tests/test_spotify_discovery.py tests/test_spotify_catalog_collection.py` — 32 passed, 31 skipped, 1 warning. provider mock으로 정확/부분 이름·중복 후보·동명이인·기존 소유권·과거 거절·공유 후보·pagination·불완전 응답·malformed·429 중지 동작을 확인했다. DB fixture 31개는 로컬 PostgreSQL 부재로 건너뛰었으며 실제 DB 반영·worker 결과는 아래에 별도로 기록한다.

실데이터 적용: receipt 6328로 external_accounts 22개(297–318)와 owner 연결 22개를 등록하고 catalog_changes 44개를 남겼다. 같은 보고서를 다시 적용하면 already_applied를 반환하며 계정·작업이 중복되지 않았다. 기존 49명 연결은 유지되어 연결된 표시 아티스트는 71명이다.

수집은 request_run=spotify-discovery-2026-10-11로 한정한 기존 leased worker에서 수행한다. 중간 검증 시 신규 22명 중 13명의 발매가 저장되었으며 작업은 succeeded 37, pending 21, running 1, 실패 0이었다. 전체 수집 완료 기록이 아니라 진행 중 스냅샷이며 최종 상태는 worker_jobs와 로컬 verification-progress.json에서 확인한다. 남은 그룹도 기존 worker 큐에서 처리한다.

운영 조회 API `/api/artists/{id}/albums`는 114·976·1016에 대해 HTTP 200을 반환했고, 저장된 데이터의 CatalogAlbumRead 응답과 일치했다. 프론트 구성과 조회 계약은 변경하지 않았으며 수집 데이터가 기존 디스코그래피 화면에 표시된다. 앞으로 추가되는 미연결 아티스트는 위 등록 도구를 다시 실행해야 한다. 주기적인 worker는 연결된 계정의 발매 갱신만 수행하며 이름 검색으로 계정을 자동 등록하지 않는다.
