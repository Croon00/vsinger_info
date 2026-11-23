# Spotify 이름 일치 연결

최종 확인 2026-11-23. 2026-10-11 조사·연결 결과와 검증은 [적용 기록](records/data/spotify-exact-name-discovery-2026-10-11.md)에 있다.

Spotify 계정이 연결되지 않은 아티스트의 디스코그래피를 표시하기 위해, 사용자가 명시적으로 요청할 때 실행하는 조사·등록 도구다. 조회 화면은 저장된 앨범·트랙만 사용하고 공개 조회 API는 provider 수집을 시작하지 않는다. 주기적인 Spotify worker는 이미 연결된 계정의 발매 갱신만 수행하며 이름 검색으로 계정을 자동 등록하지 않는다. 새로 추가된 미연결 아티스트는 이 도구를 다시 실행해야 한다.

## 실행

```powershell
python scripts/discover_spotify_accounts.py --output outputs/spotify-discovery-<배치명>
python scripts/discover_spotify_accounts.py --apply --run spotify-discovery-<배치명> --output outputs/spotify-discovery-<배치명>
```

| 옵션 | 동작 |
| --- | --- |
| `--output DIR` | 필수. 보고서와 검색 캐시 위치. 새 조사는 새 디렉터리를 쓰고, 중단한 같은 배치만 기존 캐시로 재개한다 |
| (기본) | 신규 DB 읽기 전용, 외부 API 조회, 로컬 보고서 작성 |
| `--apply` | 사용자 요청 범위에서 단일 후보만 등록 |
| `--run NAME` | 감사·작업 request_run 이름. 기본 `spotify-discovery-<UTC 날짜>` |
| `--direct-connect` | 로컬 proxy가 provider 접속을 막을 때만 사용. Railway 설정을 바꾸는 옵션이 아니다 |

## 판정 기준

- 대상: 활성 show_in_catalog 아티스트 중 활성 Spotify 연결이 없는 아티스트. 기존 연결은 교체하지 않는다. 적용 후 등록된 계정은 다음 실행의 대상에서 빠진다.
- 검색명: 저장된 name_native, name_latin, name_ko. 임의 로마자·별명은 생성하지 않는다. 비교는 NFKC·양끝 공백·대소문자를 정규화하며 내부 공백이나 기호는 지우지 않는다.
- [Spotify Search for Item](https://developer.spotify.com/documentation/web-api/reference/search)의 artist 검색을 한 페이지 10개, 이름당 최대 10페이지까지 확인한다(offset·limit·artist 타입·market 사용).
- 분류: 이름 일치 프로필이 하나이고 각 검색이 완료된 경우만 `match`. 결과 누락·상한 도달, 여러 동일 이름 프로필은 `review`, 미일치는 `missing`이다. Spotify 검색 결과 범위의 단일 후보라는 뜻이며 이름만으로 전 세계 동명이인 부재를 보증하지 않는다. `missing`은 실제 발매 없음의 증거가 아니다.
- 기존 계정(보관 계정 포함)은 다른 아티스트에게 자동 재할당하지 않는다. 서로 다른 카탈로그 아티스트가 같은 Spotify 후보를 얻으면 둘 다 보류한다. 이전 skip 검수 이력도 이름 일치만으로 뒤집지 않는다.
- 사용자가 신원을 직접 확인한 경우(검색명 불일치, 같은 사람의 복수 프로필 등)는 공통 자동 연결 조건을 넓히지 않고 개별 확인 근거로 연결한다.

## 적용

- `--apply`는 신규 external account 등록, `collection_enabled=true`, owner 연결, catalog_imports/catalog_changes 이력, `spotify_collect` 작업을 원자적으로 만든다. 자동 판정 이력은 `reviewed=false`로 기록한다.
- 같은 작업은 감사 operation ID와 worker idempotency key로 중복을 막으며 재적용은 `already_applied`를 반환한다.
- worker 작업은 `link_youtube=false`이며 기존 앨범/싱글/참여 발매와 트랙 크레딧 보존 규칙을 따른다. 가사·번역·노래방·알림은 실행하지 않는다.
- 한 아티스트에 계정이 여러 개면 대표는 하나만 두고 모두 수집하며, 발매 목록은 조회 API에서 한 아티스트 아래 함께 표시한다.

## 안전

토큰·API key는 보고서에 저장하지 않는다. provider 오류는 안전한 코드만 남기고 429/연결/서버 오류가 발생하면 배치 호출을 중지한다.

## 테스트

`tests/test_spotify_discovery.py`, `tests/test_spotify_catalog_collection.py`는 provider mock으로 정확/부분 이름·중복 후보·동명이인·기존 소유권·과거 거절·공유 후보·pagination·불완전 응답·malformed·429 중지를 확인한다. DB fixture 테스트는 로컬 PostgreSQL이 있어야 실행된다.
