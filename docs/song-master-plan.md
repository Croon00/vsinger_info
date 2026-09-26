# 곡 마스터 구축 계획

작성: 2026-09-27. `songs`를 고유 곡 기준으로 채우고 세트리스트 `performances.song_id`를 연결하기 위한 규칙과 순서다. 0·1단계는 완료했고 2단계 이후는 아직 구현하지 않았다.

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
| 0 | 표기 규칙·예외 문서화, latin ASCII 제약(003) | 완료. 2026-09-27 운영 DB 적용·`--verify` 통과 |
| 1 | 읽기 전용 측정: 아티스트별 Spotify/YouTube 계정 비율, 원문 키 빈도 분포, 기존 `songs` 450행의 출처·중복 | 완료. 아래 측정 결과 |
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
- 003은 코드 배포 후 운영 DB에 적용했다. 2026-09-27 `scripts/migrate_catalog.py --verify`: revision `001`-`003`, `catalog-v2`, `verified: true`.

## 1단계 측정 결과 (2026-09-27)

`scripts/audit_song_master_readiness.py`로 운영 DB를 읽기 전용 조회했다. 원문 키는 `app/core/song_keys.py`의 보수적 정규화(NFKC·대소문자·공백·감싼 따옴표만)로 묶었고, 다른 표기를 같은 곡으로 판단하지 않는다. 상세 목록은 Git 제외 보고서에만 있다.

| 항목 | 값 |
| --- | --- |
| 활성 아티스트 / 라이브 진행자 / 원곡자로 연결된 아티스트 | 319 / 57 / 244 |
| Spotify owner 계정 보유 (전체·진행자) | 3 · 2, 수집 활성 0 |
| YouTube owner 계정 보유 (전체·진행자) | 69 · 48 |
| 가창 행 / `song_id` 연결 | 74,504 / 25,709 (34.5%) |
| 원문 쌍 / 정규화 키 / 곡명만 기준 | 16,264 / 15,266 / 10,701 |
| 1회만 나온 키 / 원곡자 표기 없는 가창 | 9,276 / 7,891 |
| 미연결 가창 / 미연결 키 / 일부만 연결된 키 | 48,795 / 13,683 / 199 |
| 미연결 가창 중 상위 키 점유율 | 100개 11.2%, 300개 25.5%, 500개 35.4%, 1000개 50.5%, 2000개 65.0% |
| 기존 `songs` | 450행. 원곡자 연결 450, `title_ko`·`title_latin` 352, 언어 176, 녹음·노래방 0. 생성 기록은 correction 243, 영수증 없음 207 |
| 기존 곡 중 같은 원어 곡명 | 9그룹. 원곡자 조합까지 같은 그룹 0 |
| `recordings` | 0행 |

해석:

- 가장 많이 불린 곡은 기존 450곡으로 이미 연결돼 있다. 남은 미연결 가창은 분포가 넓어 상위 1000개 키로 절반을 덮는다. 곡 seed는 미연결 키 빈도순으로 진행한다.
- 상위권 원문은 곡명·원곡자가 대체로 깔끔하다. 원곡자 없는 인사말류(`こんつきー` 등)처럼 곡이 아닌 행이 섞여 있어 후보 단계에서 제외 판정이 필요하다.
- 일부만 연결된 199개 키는 이미 검수된 연결을 근거로 같은 키의 나머지 행을 연결할 후보다. 연결된 행이 모두 같은 `song_id`일 때만 후보로 만든다.
- 같은 곡명 9그룹은 대부분 서로 다른 곡이지만, `僕が死のうと思ったのは`처럼 같은 작품을 다른 명의로 등록했을 가능성이 있어 5단계에서 외부 ID로 확인한다.
- Spotify는 사실상 미등록이며 `recordings`도 비어 있다. `recording_external_ids.platform`은 `spotify`만 허용하므로 3단계 ISRC 저장에는 migration이 필요하다.
- 1회만 나온 9,276개 키는 수작업 대비 효과가 낮아 외부 DB 정확 일치로만 처리하고 나머지는 미연결로 둔다.
