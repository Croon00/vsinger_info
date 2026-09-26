# 곡 마스터 구축 계획

작성: 2026-09-27. `songs`를 고유 곡 기준으로 채우고 세트리스트 `performances.song_id`를 연결하기 위한 규칙과 순서다. 0·1·4단계를 완료했고, 7단계 소급 연결을 한 번 적용했으며, 5단계는 파일럿(읽기 전용)까지 했다. 2·3·6단계는 아직 구현하지 않았다.

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
| 4 | 곡 식별 스키마: 원문 키 대응표, 곡 외부 ID, 곡 별칭, 병합 기록 | 완료. 2026-09-27 운영 DB에 004 적용, 원문 키 backfill 반영 |
| 5 | 곡 seed: Spotify ISRC → MusicBrainz work, 상위 원문 키 → VocaDB/UtaiteDB → MusicBrainz | 상위 키 300개 파일럿 적용 완료(2026-09-27, 새 곡 277·새 아티스트 86). 나머지 pending 키 확장 TODO |
| 6 | `title_ko` 보강: 저장한 외부 ID로 Wikidata 조회, 나머지는 검수 후보 | TODO |
| 7 | 확정 키로 `performances.song_id` 소급 연결, YouTube 수집에서 확정 키 자동 부여 | 소급 연결 2회 적용(연결률 54.7%). 수집 경로 연결 TODO |
| 8 | 곡 연결률이 충분해지면 노래방 번호 작업 시작 | TODO |

5단계는 2~3단계와 독립적으로 진행할 수 있다. 1단계 측정 결과에 따라 4단계 → 일부 연결 키 199개 확장 → 5단계 파일럿을 먼저 하고, 2·3단계(Spotify)는 버튜버 오리지널곡을 위해 병행한다.

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


## 4단계 결과 (2026-09-27)

- `migrations/catalog/004_song_identity.sql`: `song_aliases`, `song_external_ids`, `song_match_keys`, `song_merges`. 기존 표·컬럼은 바꾸지 않았다. 병합 기록은 `songs`에 컬럼을 더하지 않고 별도 추가 전용 표로 두었다.
- `scripts/backfill_song_match_keys.py`: 원문 키를 집계해 저장한다. 상태는 이미 존재하는 `performances.song_id`로만 유도한다. 모든 행이 한 곡이면 `confirmed(existing_link)`, 여러 곡이면 `ambiguous`, 일부만 연결되면 `pending`과 후보 곡을 evidence에 남긴다. 수동·외부 판정은 덮어쓰지 않고 횟수·샘플만 갱신한다. `performances`, `songs`는 변경하지 않는다.
- 운영 DB dry-run(004 미적용 상태 미리보기): 키 15,266개 중 confirmed 1,583(가창 25,347), pending 13,683(가창 49,157), ambiguous 0, 후보 곡이 있는 pending 199. 정규화 뒤 빈 곡명 0.
- 로컬 임시 PostgreSQL: migration 17 passed, backfill 4 passed. 전체 `python -m pytest -q -p no:cacheprovider` 326 passed, 376 warnings(기존 deprecated 경고).
- 운영 반영 순서: 코드 배포 → `scripts/migrate_catalog.py --apply` → `--verify` → `scripts/backfill_song_match_keys.py` dry-run 확인 → `--apply`.
- 운영 반영(2026-09-27): 004 적용 후 `--verify` 통과(revision `001`-`004`). backfill `--apply`로 키 15,266개(confirmed 1,583, pending 13,683)와 영수증 1건을 한 transaction으로 저장했고, 직후 dry-run은 inserts/updates 0이다.
- 첫 `--apply`는 키마다 INSERT를 보내 원격 왕복이 길어졌고, 사용자가 중단한 뒤에도 서버에 미완료 transaction이 남아 있었다. 확인 결과 커밋된 행과 영수증은 0건이었고, 해당 세션만 종료한 뒤 재실행했다. 이후 저장 경로는 `jsonb_to_recordset` 기반의 일괄 INSERT/UPDATE로 바꿨으며 약 5초에 끝났다.


## 일부 연결 키 검토 (2026-09-27, 완료)

- 대상: 같은 원문 키의 일부 가창만 한 곡에 연결된 pending 키 199개. `scripts/review_partial_match_keys.py export`로 결정 파일을 만들었다.
- 원문 키가 후보 곡의 정규화 원어 제목과 같고 원곡자가 후보 곡의 원곡자 이름·별칭 중 하나와 같으면 `exact`로 보고 `confirm`을 미리 채웠다(189개). 계획 원칙의 "정확 일치이면서 후보 1개" 자동 확정에 해당하며 `decided_by=existing_link`로 기록한다.
- 나머지 10개는 제목 표기(공백·전각 기호·읽기 표기) 또는 원곡자 표기(괄호 병기·공동 명의·캐릭터명)가 달라 사람이 결정한다.
- 저장된 판정은 이후 backfill이 다시 유도하지 않는다(`evidence.review`). 판정 저장은 `song_match_keys`만 바꾸며 가창 연결은 다음 단계다.
- 사용자가 10개를 모두 같은 곡으로 확인했다. `apply --apply`로 199개를 confirmed로 저장(규칙 189, 수동 10)하고 영수증 1건을 남겼다. 직후 backfill dry-run의 updates는 0이다. 결정 파일은 `migrations/catalog/partial-match-key-decisions.json`이다.

## 7단계 첫 적용: 확정 키로 가창 연결 (2026-09-27)

- `scripts/link_performances_from_match_keys.py`: `song_id`가 비어 있고 정규화 원문이 confirmed 키와 같은 가창만 연결한다. 보관된 곡과 병합으로 사라진 곡은 제외한다. 2,000 ID 단위로 커밋하며 단위마다 `catalog_imports`(correction) 영수증과 가창별 `catalog_changes`(before/after `song_id`, 근거 키 ID)를 남긴다. 계획 이후 행이 바뀌면 그 단위를 rollback한다.
- 로컬 임시 PostgreSQL 3 passed(연결 범위, 기존 연결·보관·병합 제외, 감사 기록, 재실행 0건, 동시 변경 rollback).
- 운영 DB dry-run: confirmed 키 1,782개, 미연결 가창 48,795건 중 4,502건 연결 예정(키 199개, 37단위). 연결 후 미연결 44,293건.
- 사용자 승인 후 `--apply`: 37단위 모두 커밋, 4,502건 연결. 직후 dry-run의 links는 0이다. 가창 74,504건 중 연결 30,211건(40.5%), 미연결 44,293건. 되돌리기 스크립트는 아직 없으며 `catalog_changes`로 건별 복원할 수 있다.
- 연결 후 backfill dry-run에서 판정 변경 없이 대표 표기(`sample_raw_title`)만 1건 바뀌었다. 같은 횟수의 표기가 여럿일 때 DB 행 순서에 따라 대표가 바뀌던 문제라, 횟수가 같으면 문자열 순으로 고르게 고쳤다. 새 규칙으로 대표 표기가 달라지는 키 119개는 다음 backfill `--apply` 때 함께 갱신된다(상태·song_id 변경 없음).
- 남은 미연결 키 13,484개는 모두 후보 곡이 없는 pending이다. 다음은 5단계(VocaDB/MusicBrainz 파일럿)다.


## 5단계 파일럿: 외부 목록 후보 조회 (2026-09-27, 읽기 전용)

- `app/integrations/song_catalogs.py`: VocaDB/UtaiteDB(같은 API) 원곡(`songTypes=Original`) 정확 제목 검색, MusicBrainz 녹음 검색과 녹음 ID로 연결된 work 검색. timeout 30초, 요청 간격(VocaDB·UtaiteDB 0.5초, MusicBrainz 1.2초), 429·5xx는 `Retry-After`를 따라 최대 3회 재시도한다. 가사는 요청하지 않는다. User-Agent에 저장소 URL을 넣는다.
- `app/services/song_candidates.py`: VocaDB → UtaiteDB → MusicBrainz 순으로 찾고, 제목과 원곡자가 모두 맞는 후보가 나오면 멈춘다. 원곡자는 VocaDB producer/circle/band, MusicBrainz 녹음 performer·work composer/lyricist만 인정하고 보컬(初音ミク 등)만 맞으면 검수로 보낸다. 비교는 `normalize_text`에 물결·대시 변형과 공백만 접은 `loose` 형태로 하며 저장 키로 쓰지 않는다. 제목과 원곡자가 모두 맞는 후보가 정확히 1개일 때만 `auto`다.
- `scripts/match_song_candidates.py --songs --keys 300`: 기존 곡 450개를 먼저, 이어서 빈도 상위 pending 키 300개를 조회했다. DB는 읽기 전용이고 보고서와 provider 응답 cache는 Git 제외 `db-migration/reports/song-master-candidates/`에 있다. 첫 실행 약 26분(요청 VocaDB 764, UtaiteDB 539, MusicBrainz 882), cache 재실행 22초.
- 로컬 fixture: adapter 10개(파싱, 503 재시도, 404·잘못된 JSON, rate limit 상한, Lucene 이스케이프, 요청 간격)와 후보 규칙 9개 통과. 실제 provider 호출은 파일럿 실행뿐이다.

| 대상 | auto | review | none | no_artist | auto 출처 |
| --- | --- | --- | --- | --- | --- |
| 기존 곡 450개 (가창 30,211) | 407개, 가창 28,702 | 26 | 17 | - | VocaDB 158, UtaiteDB 60, MusicBrainz 189 |
| 상위 pending 키 300개 (가창 11,236) | 277개, 가창 10,306 | 7 | 12 | 4 | VocaDB 85, UtaiteDB 49, MusicBrainz 143 |

해석:

- 키 auto 277개를 모두 적용하면 미연결 가창 44,293건 중 10,306건(23.3%)이 연결된다. 277개 중 4개는 기존 곡의 다른 표기(예: `フクロウ ～…～`)라 기존 곡에 연결하고, 나머지 273개는 새 곡이다. 새 곡 중 2쌍은 같은 work를 가리킨다(`Rain`의 大江千里 원곡과 秦基博 커버, 물결 표기만 다른 `さよならの夏`). 적용할 때 외부 ID로 한 곡으로 묶는다.
- 키 auto의 원곡자 중 180개만 우리 `artists`에 있다. 나머지 97개는 새 아티스트가 필요하며, `artists.entity_kind`가 필수라 solo/group을 provider 아티스트 정보로 정해야 한다.
- 기존 곡 10(`僕が死のうと思ったのは`, 中島美嘉)과 208(같은 곡, amazarashi)이 같은 MusicBrainz work다. 곡을 작품 단위로 보면 병합 후보다.
- review는 동명곡(`SUN`, `落日`), 같은 아티스트의 MusicBrainz 중복 work(`相思相愛`, `水平線`), 캐릭터 명의(`涼宮ハルヒ（平野綾）`, `シェリル・ノーム starring May'n`)가 대부분이다. none은 provider에 아직 없는 곡(`W/X`, `拝啓、はじまりの色` 등)이다.
- `title_latin` 후보: 제목이 이미 라틴 문자이거나 provider 로마자 표기(VocaDB Romaji, MusicBrainz `ja-Latn`)가 있을 때만 만든다. 영어 이름은 번역이라 쓰지 않는다. 키 auto 277개 중 132개, 기존 곡 auto 407개 중 216개에 있다. VocaDB 로마자는 장음을 `ou`로 적어(`Jun Toumei Shounen`) 기존 곡 표기(`Shojo Rei`)와 방식이 다르다.
- `title_ko`는 MusicBrainz ko 별칭에서 각 1개만 나왔다. 6단계(Wikidata)로 채운다.
- VocaDB·UtaiteDB에서 가져온 이름은 CC BY 4.0이라 출처 URL(외부 ID로 만들 수 있음)을 남기고 화면에 출처를 표시해야 한다. 표시 방법은 아직 정하지 않았다.

## 5단계 적용 준비 (2026-09-27)

- 사용자 결정: `僕が死のうと思ったのは`는 中島美嘉(곡 10)와 amazarashi(곡 208)를 그대로 두 곡으로 둔다. 같은 MusicBrainz work ID는 곡 208에만 붙인다. `W/X`는 `W/X/Y`의 오타이고 `拝啓、はじまりの色`는 YONO(아티스트 33)의 곡이라 수동으로 보완한다. `title_latin`은 provider 로마자를 그대로 쓴다. 새 아티스트는 웹조사로 필수값과 `name_ko`를 채우고 `show_in_catalog=false`, `is_virtual`은 버튜버일 때만 true로 둔다. `name_native`가 라틴 문자면 `name_ko`는 비운다.
- 같은 원칙을 일반화했다. 다른 아티스트의 키가 같은 work로 모이면(원곡과 유명 버전) 아티스트마다 별도 곡으로 두고, work ID는 work에 작곡·작사로 올라 있는 쪽, 없으면 가창이 많은 쪽 곡에 붙인다. 이번에는 `Rain`(大江千里 원곡, 秦基博 버전)이 해당한다. 후보 조회도 저장된 work ID의 곡과 아티스트가 다르면 그 곡으로 흡수하지 않는다(`existing_matches`).
- 검수 필요 33건은 서브에이전트가 1차 검수했다(연결 14, 일치 없음 12, 새 곡 4, 보류 3). 2차 검수 표시 10건은 부모가 재판단해 종결했다. `一番の宝物 / LiSA`는 후보가 karuta 원곡이라 연결하지 않았고, `シェリル・ノーム starring May'n` 두 곡은 새 아티스트 하나를 공유한다. 보류 3건(`Hope Song`, `I LOVE YOU / クリス・ハート`, `U`)은 pending으로 남긴다.
- 새 아티스트 84그룹은 서브에이전트 4개가 병렬로 웹조사했다(근거 URL·신뢰도는 결정 파일과 `catalog_changes.provenance`에 남긴다). `放課後ティータイム`의 `is_virtual=true` 제안은 애니메이션 캐릭터 밴드라 false로 바로잡았다. 신뢰도 low는 `ハムちゃんず`, `伊織` 2건이다.
- 결정: 수동 결정·보정은 `migrations/catalog/song-master-manual.json`, 합친 결정 파일은 `migrations/catalog/song-master-decisions.json`이다. `scripts/seed_song_master.py apply --apply`가 한 transaction으로 저장하고 영수증(`catalog_imports`)과 행별 `catalog_changes`를 남긴다. 내보낸 뒤 바뀐 곡·키, 이미 저장된 외부 ID·slug가 있으면 전체를 거부한다.
- 로마자가 곡 제목과 같으면(`Lemon`처럼 제목이 이미 라틴 문자) 기존 곡 표기에 맞춰 `title_latin`을 비운다.
- 로컬 임시 PostgreSQL: 적용 스크립트 4개(분리 규칙·표기 규칙, 한 번만 기록·감사 기록·재실행 no-op, 변경 행 거부, 잘못된 조사값 거부) 포함 전체 `python -m pytest -q -p no:cacheprovider` 359 passed, 376 warnings(기존 deprecated 경고).
- 운영 DB dry-run: 기존 곡 419곡에 외부 ID 420개, 빈 `title_latin` 4곡, 새 아티스트 86명, 새 곡 277곡(외부 ID 275개), 키 285개 확정(기존 곡 연결 7, 가창 10,605건). 생략 3건은 위 보류 키다. 가창 연결은 적용 뒤 `scripts/link_performances_from_match_keys.py`로 한다.


## 5단계 적용과 가창 연결 (2026-09-27)

- 사용자 승인 후 `scripts/seed_song_master.py apply --apply`: dry-run과 같은 manifest(`ec75deb3…`)로 한 transaction 커밋(영수증 import 296). `catalog_changes`는 artists create 86, songs create 277, songs update 419, song_match_keys update 285다. 같은 파일 재실행은 `already_committed`다.
- 적용 뒤 운영 DB(읽기 전용 확인): songs 727, artists 405, song_external_ids 695(musicbrainz_work 334, vocadb 247, utaitedb 114). 새 아티스트 86명은 모두 `show_in_catalog=false`, `is_virtual=false`(solo 51, group 35)이고, `name_ko`가 빈 34명은 모두 원어 이름이 라틴 문자다(`Cö shu Nie` 포함). 새 곡 277곡은 모두 원곡자가 연결됐고 79곡에 `title_latin`이 있다. `僕が死のうと思ったのは`는 곡 10(외부 ID 없음)과 208(work ID 1개), `Rain`은 곡 1369(大江千里)와 1370(秦基博)으로 나뉘었다. `拝啓、はじまりの色`는 YONO(아티스트 33)의 곡 1453이다.
- 이어서 `scripts/link_performances_from_match_keys.py --apply`: 키 285개로 10,605건 연결, 37단위 모두 커밋. 직후 dry-run의 links는 0이다. 가창 74,555건 중 연결 40,816건(54.7%), 미연결 33,688건이다(측정 중 수집으로 가창 51건 증가). song_id가 존재하지 않는 곡을 가리키는 가창은 0건이다.
- backfill dry-run은 판정 변경 없이 대표 표기 119건만 남았다(위 7단계 항목). 남은 pending 키는 13,199개다.
- 되돌리기 스크립트는 아직 없다. 가창 연결은 `catalog_changes`로 건별 복원할 수 있고, 새 곡·아티스트는 import 296의 create 기록으로 찾을 수 있다.
