# 곡 마스터 구축 계획

작성: 2026-09-27. `songs`를 고유 곡 기준으로 채우고 세트리스트 `performances.song_id`를 연결하기 위한 규칙과 순서다. 0단계(규칙·ASCII 제약) 외에는 아직 구현하지 않았다.

## 원칙

- 곡의 근거는 외부의 검수된 목록(VocaDB/UtaiteDB, MusicBrainz, Wikidata, 등록 아티스트의 Spotify)이다. 세트리스트 원문은 조회할 대상과 빈도를 정하는 데만 쓰고, 원문만으로 곡을 생성하지 않는다.
- 외부 ID를 곡의 중복 방지 기준으로 저장한다. 같은 외부 ID는 같은 `song_id`에 연결한다.
- 자동 확정은 정확 일치이면서 후보가 1개인 경우만 한다. 나머지는 후보 파일로 검수한다. 수집 worker가 곡·계정을 추측해 생성하지 않는다.
- 외부 자료의 라이선스·출처 표시와 provider rate limit을 따른다. VocaDB 내용은 CC BY 4.0이며 가사는 가져오지 않는다.

## 표기 규칙

- `title_latin`, `name_latin`: 발음 부호 없는 출력 가능 ASCII만 쓴다. 외부 값의 발음 부호는 제거한다(`Tōkyō` → `Tokyo`). DB 제약 `artists_name_latin_ascii`, `songs_title_latin_ascii`(revision 003)가 강제한다.
- `title_ko`, `name_ko`: 가능한 한 채우되 출처가 있어야 한다. 우선순위는 Wikidata ko label → MusicBrainz ko 별칭 → 공식 한국 발매명이다. 출처가 없으면 LLM 제안을 검수 후보로만 만들고, 승인한 값만 반영하며 근거를 기록한다. 번역기 결과를 직접 저장하지 않는다. 팬 호칭은 곡 별칭으로 분리한다.

## Spotify 계정 등록 예외

수집 worker는 계속 등록된 Spotify 계정만 사용하고 이름 검색으로 계정을 찾지 않는다. 기존 아티스트의 Spotify ID는 별도 조사 스크립트가 후보 파일을 만들고, 사람이 검수한 행만 적용 스크립트로 `external_accounts`에 등록한다. 수집 활성화는 등록과 별도로 결정한다.

## 작업 순서

| 단계 | 내용 | 상태 |
| --- | --- | --- |
| 0 | 표기 규칙·예외 문서화, latin ASCII 제약(003) | 코드·로컬 검증 완료, 운영 DB 미적용 |
| 1 | 읽기 전용 측정: 아티스트별 Spotify/YouTube 계정 비율, 원문 키 빈도 분포, 기존 `songs` 450행의 출처·중복 | TODO |
| 2 | 아티스트 Spotify ID 후보 조사 → 검수 → 적용. Wikidata로 `name_ko`/`name_latin` 후보 병행 | TODO |
| 3 | Spotify 수집과 ISRC 저장(`recording_external_ids`) | TODO |
| 4 | 곡 식별 스키마: 원문 키 대응표, 곡 외부 ID, 곡 별칭, 병합 기록 | TODO |
| 5 | 곡 seed: Spotify ISRC → MusicBrainz work, 상위 원문 키 → VocaDB/UtaiteDB → MusicBrainz | TODO |
| 6 | `title_ko` 보강: 저장한 외부 ID로 Wikidata 조회, 나머지는 검수 후보 | TODO |
| 7 | 확정 키로 `performances.song_id` 소급 연결, YouTube 수집에서 확정 키 자동 부여 | TODO |
| 8 | 곡 연결률이 충분해지면 노래방 번호 작업 시작 | TODO |

5단계는 2~3단계와 독립적으로 진행할 수 있다.

## 0단계 검증 (2026-09-27)

- 운영 DB 읽기 전용 조회: `artists` 319행 중 `name_latin` 183행, `songs` 450행 중 `title_latin` 352행. ASCII 밖 문자 0행. 적용 revision은 `001`, `002`.
- 로컬 임시 PostgreSQL: `tests/test_catalog_migration.py` 16 passed. 전체 `python -m pytest -q -p no:cacheprovider` 318 passed, 376 warnings(기존 FastAPI/Starlette deprecated 경고).
- 003은 운영 DB에 적용하지 않았다. 앱의 revision 검사는 `001-002`, `001-003`을 모두 허용하므로 코드 배포 후 `scripts/migrate_catalog.py --apply`로 적용한다.
