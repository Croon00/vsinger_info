# 곡 마스터 구축 계획

작성: 2026-09-27. `songs`를 고유 곡 기준으로 채우고 세트리스트 `performances.song_id`를 연결하기 위한 규칙과 순서다. 0·1·4단계를 완료했고, 7단계 소급 연결을 한 번 적용했으며, 5단계는 파일럿(읽기 전용)까지 했다. 2·3·6단계는 아직 구현하지 않았다.

## 원칙

- 곡의 근거는 외부의 검수된 목록(VocaDB/UtaiteDB, MusicBrainz, Wikidata, 등록 아티스트의 Spotify)이다. 세트리스트 원문은 조회할 대상과 빈도를 정하는 데만 쓰고, 원문만으로 곡을 생성하지 않는다.
- 외부 ID를 곡의 중복 방지 기준으로 저장한다. 같은 외부 ID는 같은 `song_id`에 연결한다.
- 같은 곡은 기본적으로 하나다(사용자, 2026-09-27). 세트리스트가 작곡·제작자나 가창자, 유명 커버 가수 중 누구를 적었든 같은 work면 한 곡이며, 적힌 아티스트를 모두 명의로 둔다(work에 오른 아티스트가 먼저). 예외는 사용자가 정한 것만 manual `split_works`로 아티스트별로 나눈다(현재 `僕が死のうと思ったのは`의 中島美嘉/amazarashi).
- 아티스트는 발매 명의로 곡을 구분할 수 있으면 나누고, 외부 DB가 같은 사람을 한 엔티티로만 표시해 곡별로 구분할 수 없으면 합친다(사용자, 2026-09-27).
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
| 2 | 아티스트 Spotify ID 후보 조사 → 검수 → 적용. Wikidata로 `name_ko`/`name_latin` 후보 병행 | 진행 중. 아래 2단계 결과 |
| 3 | Spotify 수집과 ISRC 저장(`recording_external_ids`) | 운영 수집 진행 중. 아래 3단계 |
| 4 | 곡 식별 스키마: 원문 키 대응표, 곡 외부 ID, 곡 별칭, 병합 기록 | 완료. 2026-09-27 운영 DB에 004 적용, 원문 키 backfill 반영 |
| 5 | 곡 seed: Spotify ISRC → MusicBrainz work, 상위 원문 키 → VocaDB/UtaiteDB → MusicBrainz | 원래 순위 1000위까지 적용 완료(2026-09-27, 1차 새 곡 277·새 아티스트 86, 2차 새 곡 541·새 아티스트 166). 1000위 밖 pending 키 확장 TODO |
| 6 | `title_ko` 보강: 저장한 외부 ID로 Wikidata 조회, 나머지는 검수 후보 | 상위 200곡과 201위 이후 432곡, Wikidata 결과 적용(2026-09-27, 나무위키·검수) |
| 7 | 확정 키로 `performances.song_id` 소급 연결, YouTube 수집에서 확정 키 자동 부여 | 소급 연결 4회 적용(연결률 66.9%). 수집 경로 자동 연결 배포·운영 관측(아래 7단계 수집 경로) |
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

## 7단계 수집 경로 연결 (2026-09-27)

- `app/repositories/youtube_collection.py`의 `persist_collect`가 가창을 넣을 때 `app/repositories/song_match_keys.py`로 confirmed 키를 조회해 같은 transaction에서 `song_id`를 채운다. 새 archive와 가창이 없던 기존 archive 재개 두 경로 모두에 적용된다. 대상 곡은 보관되지 않고 병합으로 사라지지 않은 곡이다.
- 조회 규칙(`app/core/song_keys.py`의 `lookup_keys`/`resolve_key`)은 소급 연결 스크립트와 같다. 먼저 정규화 원문(곡명·원곡자) 정확 일치를 보고, 없고 원곡자 원문이 비어 있으면 곡명 원문을 `/`·`／`(공백 무관) 또는 공백을 둔 대시(` - ` 등)에서 나눈 (곡명, 원곡자) 쌍을 confirmed 키와 비교한다. 나눈 쌍이 여러 곡을 가리키면 연결하지 않는다. 나눈 쌍은 조회에만 쓰고 저장하지 않으며 원문도 바꾸지 않는다.
  - 이유: 운영 수집분(2026-09-23~27) 695행은 모두 규칙 추출(`rules-1`)이고, 규칙 파서는 `곡명 / 원곡자`를 곡명 원문에 그대로 둔다. 정확 일치만으로는 16행(2.3%)만 연결됐다.
  - 운영 DB 읽기 전용 확인: 분리 조회를 더하면 현재 미연결 가창 중 189건(키 160개)이 추가로 연결되고, 여러 곡에 걸리는 행은 0건이다. 이미 연결된 원곡자 없는 가창 1,231건에 같은 규칙을 적용해도 기존 연결과 다른 곡을 고르는 경우는 0건이다. 상위 60건을 눈으로 확인했을 때 오연결은 없었다.
- 조회만 한다. 새 키 추가·빈도 갱신·판정은 하지 않으며, 새 원문 키는 `scripts/backfill_song_match_keys.py`, 이후 확정된 키의 소급 연결은 `scripts/link_performances_from_match_keys.py`로 한다. 소급 연결 스크립트 policy를 v2로 올리고 `catalog_changes.provenance.match`에 `exact`/`split`을 기록한다.
- 수집 경로 연결은 `catalog_changes`를 남기지 않는다. 근거는 보존된 원문과 confirmed 키이며, 같은 규칙으로 언제든 재계산할 수 있다.
- revision 004 표가 없으면(`to_regclass`) 연결 없이 이전처럼 저장한다. 앱이 허용하는 revision 범위(001-002~001-004)는 그대로다.
- 로컬 임시 PostgreSQL: 수집 테스트 2개(confirmed 키만 연결, 분리 조회, 여러 곡에 걸리는 분리 쌍·pending·키 없음·보관 곡·병합 곡은 NULL, 키 표 불변 / 004 표 없음), 조회 규칙 단위 테스트 2개, 소급 연결 분리 조회 테스트 1개를 추가했다. 전체 `python -m pytest -q -p no:cacheprovider` 364 passed, 376 warnings(기존 deprecated 경고). 운영 worker에는 아직 배포하지 않았다. 배포 전까지 쌓인 미연결 가창과 위 189건은 배포 뒤 소급 연결 스크립트 한 번으로 채운다.
- 배포 뒤 소급 연결(v2): dry-run 189건(키 160개)으로 배포 전과 같았고, `--apply`로 6단위 모두 커밋했다. 189건 모두 분리 조회(`match=split`)이며 직후 dry-run의 links는 0이다. 가창 74,572건 중 연결 41,005건(55.0%), 미연결 33,516건이다. 수집기(`youtube-catalog`) 가창 695건 중 193건이 연결됐다. 배포 뒤 새로 저장된 수집 가창은 아직 없어(마지막 저장 2026-09-27 15:08 KST) 수집 경로 자동 연결은 운영에서 아직 관측하지 못했다.


## 5단계 2차 파일럿: 원래 순위 1000위까지 (2026-09-27, 읽기 전용)

- 대상: 1차 파일럿과 같은 순위(현재 pending + import 296에서 확정한 키, `occurrence_count` 내림차순)의 1000위 안에서 아직 pending인 키 717개(가창 11,133건, 1000위 경계 빈도 9회). `scripts/match_song_candidates.py --keys 717`로 조회했다. 1차에서 보류·못 찾음으로 남은 키도 다시 포함된다.
- 실행 약 35분(요청 VocaDB 699, UtaiteDB 550, MusicBrainz 864), provider 오류 0건. 보고서는 Git 제외 `db-migration/reports/song-master-candidates/candidates-20260927T071104Z.json`이다.

| 상태 | 키 | 가창 |
| --- | --- | --- |
| auto | 547 (새 곡 533, 기존 곡 14) | 8,288 |
| review | 61 (원곡자 불일치 56, 보컬만 일치 4, 강한 후보 여러 개 1) | 914 |
| none | 81 | 1,403 |
| no_artist | 28 | 528 |

- auto 출처: MusicBrainz 311, VocaDB 172, UtaiteDB 64. 무작위 30건을 확인했을 때 오연결은 없었다(`春よ、来い / 松任谷由実`는 별칭 荒井由実, `曖昧劣情Lover / 電ポルP`는 같은 사람인 koyori로 맞았다).
- auto 547개 중 222개는 원곡자가 우리 `artists`에 없다. 표기와 provider 아티스트 ID로 묶으면 약 155그룹이며, 1차처럼 조사해야 한다. 나머지 325개는 기존 아티스트다.
- 같은 work를 가리키는 키 3쌍: `Swallowtail Butterfly ～あいのうた～`(물결 앞 공백만 다름, 한 곡), `右肩の蝶`(원곡자 표기 のりP/のりぴー, 한 곡·한 아티스트), `おとなの掟`(椎名林檎 작사·작곡 / Doughnuts Hole 가창, 1차 규칙대로면 두 곡이고 work ID는 椎名林檎 쪽).
- `title_latin` 후보 249개, `title_ko` 2개.
- none 상위는 provider에 없는 곡(`THE REAL FOLK BLUES`), 곡명에 `feat.`가 붙은 표기(`すずめ feat.十明`), 버튜버 오리지널곡(`花に落ちる`·`僕は僕の速さで` / ヨノ, `シズムリウム` / 焔魔るり)이다.
- 적용하면 auto 키만으로 가창 약 8,288건이 연결되어 연결률이 55.0%에서 약 66%가 된다(분리 조회로 조금 더 늘 수 있음). `scripts/seed_song_master.py`는 입력 파일 이름이 1차 기준으로 고정돼 있어 2차 적용 전에 차수별 입력을 받도록 고쳐야 한다.


## 5단계 2차 적용 준비 (2026-09-27)

- `scripts/seed_song_master.py --round 2`: 입력은 Git 제외 `db-migration/reports/song-master-candidates/round-2/`, 수동 결정은 `migrations/catalog/song-master-manual-2.json`, 결정 파일은 `migrations/catalog/song-master-decisions-2.json`이다. 1차 파일과 경로는 그대로 둔다. `prepare`가 조사·검수 입력을 만든다(1차는 손으로 만들었다). provider 아티스트 ID가 없는 크레딧은 아티스트 묶음에 쓰지 않는다(ID 없는 크레딧끼리 서로 다른 11명이 한 그룹이 되던 문제).
- 새 아티스트 165그룹은 서브에이전트 6개, 검수 58건(1차 보류 3건 제외)은 서브에이전트 1개가 1차로 처리했다. 조사 중 6그룹은 기존 아티스트의 다른 표기였다(バルーン→須田景凪, 松田聖子→松田 聖子, 水瀬 凪, あぷえら→Aqu3ra, 石川 さゆり, 冨田悠斗→T-POCKET). 검수는 create 36, no_match 22였다.
- 사용자 결정: `おとなの掟`는 한 곡(명의 Doughnuts Hole, 椎名林檎 순). 같은 원칙으로 한 발매를 작곡·제작자와 가창자로 나눠 적은 `ファンサ`(HoneyWorks, mona（夏川椎菜）)와 `ルパン三世のテーマ`(大野雄二, ピート・マック・ジュニア)도 한 곡으로 묶었다.
- 부모 2차 검수로 바로잡은 것(`song-master-manual-2.json`):
  - 캐릭터 명의는 기존 방식(`ランカ・リー（中島愛）`)대로 캐릭터(성우) 아티스트로 만든다: `ラクス・クライン（田中理恵）`, `阿良々木月火（井口裕香）`, `月村手毬（小鹿なお）`, `ハチワレ（田中誠人）`, `mona（夏川椎菜）`. `B小町`은 유닛 이름 그대로 둔다.
  - `ウイスキーが、お好きでしょ / SAYURI`는 검수 에이전트가 다른 곡의 ID를 옮겨 적어 유일한 후보(vocadb 813248)와 石川さゆり로 고쳤다. 읽기가 확인되지 않은 `you / 癒月`, 조사되지 않은 공동 명의 `にんげんっていいな`는 보류했다.
  - 같은 사람: `ryo`/`ryo(supercell)`, `minato(流星P)`/`湊貴大`. `WINDING ROAD / 絢香×コブクロ`는 공동 이름 아티스트 대신 絢香와 コブクロ 두 명의로 둔다.
  - 기존 곡 연결: `メルト`·`ワールドイズマイン`(ryo 표기)은 기존 supercell 곡 940·1015, `初めての恋が終わる時`는 supercell 한 곡, `ドーナツホール / 米津玄師`는 ハチ의 1308, `曖昧劣情Lover / 電ポルP`는 koyori의 991에 연결한다. koyori(592)와 電ポルP(685), ハチ(638)와 米津玄師(98)는 같은 사람이 두 아티스트로 저장돼 있다(병합은 이번 범위 밖).
  - `Da‐iCE`의 U+2010 하이픈을 ASCII로 고쳤다.
- 적용 규칙 보완: 키가 이미 알려진 아티스트(검수 에이전트가 고른 기존 아티스트, 기존 아티스트로 조사된 표기, 수동 명의)로 풀리면 그 아티스트의 표기로도 기존 곡을 찾는다(`独りんぼエンヴィー`, `ひこうき雲`, `ラヴィ`, `愛にできることはまだあるかい`, `1925`, `エイリアンズ`, `前前前世`가 새 곡 대신 기존 곡에 연결됨). 새 곡끼리는 제목(loose)이 같고 명의가 하나라도 겹치면 한 곡으로 합치고 provider ID를 함께 둔다(`ninelie`, `ウイスキーが、お好きでしょ`, `magnet`). 명의가 겹치지 않으면 다른 곡으로 둔다(`愛のうた`).
- 운영 DB dry-run: 기존 곡 4곡에 외부 ID 4개, 새 아티스트 166명(solo 109, group 57, 모두 `show_in_catalog=false`, `is_virtual=false`), 새 곡 541곡(외부 ID 546개, `title_latin` 130곡), 키 581개 확정(기존 곡 연결 27, 가창 8,785건). 생략 27건은 검수 no_match·보류와 1차 보류 키다. 적용 뒤 가창 연결까지 하면 연결률은 55.0%에서 약 67%가 된다.
- 로컬 임시 PostgreSQL: 적용 스크립트 테스트 3개 추가(수동 병합·같은 사람·공동 명의, `prepare` 묶음·보류 제외, 두 provider로 찾은 새 곡 합치기) 포함 전체 `python -m pytest -q -p no:cacheprovider` 367 passed, 376 warnings(기존 deprecated 경고).

## 같은 곡 한 곡 방침과 중복 병합 (2026-09-27)

- 사용자 방침: `ファンサ`처럼 같은 곡은 기본적으로 한 곡이다. `僕が死のうと思ったのは`는 두 가수 버전을 흔히 구분해서 예외로 나눈 것이다. 이에 따라 1·2차에서 쓴 "다른 아티스트의 버전은 별도 곡" 규칙을 바꿨다.
  - `app/services/song_candidates.py`의 `existing_matches`: 저장된 work ID가 있으면 아티스트가 달라도 그 곡이다. `split_works`에 든 work만 예전처럼 아티스트가 겹칠 때만 그 곡으로 본다.
  - `scripts/seed_song_master.py`: 한 work로 모이는 새 곡은 아티스트가 달라도 한 곡으로 만들고 명의를 모두 둔다(work에 작곡·작사·제작으로 오른 아티스트, 그다음 많이 불린 순). manual `split_works`는 예외 목록이다(2차 파일에 `僕が死のうと思ったのは` work를 넣었다).
  - 1차에서 나뉜 곡의 보정: `一番の宝物`(LiSA, 곡 1088)에 1차에서 붙이지 않았던 karuta 원곡 work(utaitedb 14998)를 2차 결정에서 붙인다. `Rain`(곡 1369 大江千里, 1370 秦基博)은 아래 병합으로 한 곡이 된다. 2차 검수 no_match 22건과 1차 no_match 12건은 후보가 다른 곡이거나 원곡이 아닌 커버 항목(`sweets parade`의 보컬로이드 커버)이어서 바뀌는 것이 없다.
- 아티스트 판단:
  - `ハチ`(638)와 `米津玄師`(98): VocaDB는 한 아티스트(49)로 `Lemon`·`打上花火` 같은 米津玄師 명의 곡까지 ハチ로 적지만, MusicBrainz는 ハチ를 별도 아티스트(米津玄師와 `is person` 관계)로, UtaiteDB는 米津玄師(1378)를 따로 둔다. 발매 명의로 곡을 구분할 수 있으므로 합치지 않는다. 현재 카탈로그도 보컬로이드 곡 3곡은 ハチ, 나머지 20곡은 米津玄師로 나뉘어 있다.
  - `koyori`(592)와 `電ポルP`(685): 사용자 결정으로 합친다. VocaDB도 한 아티스트(308, koyori)다. 이름은 VocaDB 기준인 koyori(592)로 두고 電ポルP·덴포루P·Denporu P를 별칭으로 남긴다.
  - 참고: 2차 조사에서 `バルーン`은 기존 `須田景凪`(171)에 연결됐다. VocaDB는 한 아티스트(10259)로 둔다. 기존 카탈로그도 `シャルル`를 須田景凪로 두고 있어 그대로 둔다.
- `scripts/merge_catalog_entities.py <결정 파일> [--apply]`: 기본은 읽기 전용 dry-run이다. `--apply`는 한 transaction으로 원본을 가리키는 모든 행(실제 외래 키 목록과 대조, 모르는 참조가 있으면 거부)을 대상 쪽으로 옮기고, 대상에 이미 같은 행이 있으면 원본 행을 지우고 감사 기록에 남긴다. 원본 이름은 대상의 별칭이 되고 원본은 보관되며, 곡 병합은 `song_merges`에 남는다. 영수증(`catalog_imports` merge)과 `catalog_changes`(옮긴 행 ID, 지운 행)를 남기고 같은 파일의 재실행은 no-op이다. 결정 파일은 `migrations/catalog/entity-merges-1.json`(아티스트 685→592, 곡 1370→1369)이다.
- 운영 DB dry-run: 아티스트 병합은 곡 명의 1행 이동과 별칭 3개 추가, 곡 병합은 가창 26건·원문 키 1개·명의 1행 이동이다. 2차 곡 마스터를 먼저 적용하면 2차 새 곡 중 電ポルP 명의도 함께 옮겨진다. 2차 곡 마스터 dry-run은 기존 곡 5곡(외부 ID 5개, 一番の宝物 포함)으로 바뀌었고 나머지 수는 같다.
- 적용 순서: 2차 곡 마스터 `--apply` → 병합 `--apply` → 가창 연결 dry-run·`--apply`.
- 로컬 임시 PostgreSQL: 병합 테스트 3개(dry-run 무쓰기, 참조 이동·중복 삭제·별칭·보관·`song_merges`·감사·재실행, 병합 사슬·보관된 쪽 거부)와 한 곡 방침 테스트(`existing_matches` 예외, 2차 규칙) 포함 전체 `python -m pytest -q -p no:cacheprovider` 370 passed, 376 warnings(기존 deprecated 경고).

## 5단계 2차 적용과 병합, 가창 연결 (2026-09-27)

- 사용자 승인 후 순서대로 적용했다. 세 단계 모두 적용 직전 dry-run이 승인 때와 같았고, 적용 뒤 같은 명령의 재실행은 `already_committed` 또는 links 0이다.
  1. `seed_song_master.py --round 2 apply --apply`: import 340. 새 아티스트 166명, 새 곡 541곡(외부 ID 546개), 기존 곡 5곡에 외부 ID 5개, 원문 키 581개 확정.
  2. `merge_catalog_entities.py migrations/catalog/entity-merges-1.json --apply`: import 341. 電ポルP(685)→koyori(592)는 곡 명의 3행(2차 새 곡 2곡 포함) 이동과 별칭 3개, Rain 1370→1369는 가창 26건·원문 키 1개·명의 1행 이동. `song_merges`에 1370→1369가 남았다.
  3. `link_performances_from_match_keys.py --apply`: 38단위 모두 커밋, 8,836건 연결.
- 적용 뒤 운영 DB(읽기 전용): 가창 74,573건 중 연결 49,869건(66.9%), 미연결 24,704건. 보관·병합된 곡을 가리키는 가창과 원문 키는 0건, 보관된 685를 가리키는 행은 0건이다. 새 아티스트는 모두 `show_in_catalog=false`, `is_virtual=false`이고 명의 없는 새 곡은 없다. `おとなの掟`(Doughnuts Hole·椎名林檎), `ファンサ`(HoneyWorks·mona（夏川椎菜）), `WINDING ROAD`(絢香·コブクロ), `ninelie`(Aimer·EGOIST)는 각각 한 곡이다.
- Rain 병합에서 옮긴 秦基博 명의가 大江千里와 같은 순번 0으로 들어갔다. 조회 API는 `position, id` 순이라 大江千里가 먼저 표시된다. 병합 스크립트는 옮긴 명의를 대상 곡 명의 뒤 순번으로 붙이도록 고쳤다(다음 병합부터 적용).
- 수집 경로 자동 연결을 운영에서 처음 관측했다: 배포 뒤 16:56 KST에 수집된 가창 52건 중 28건이 저장될 때 song_id를 받았다(`catalog_changes` 없음, `シルエット/KANA-BOON` 같은 분리 조회 포함). 5건은 이어진 소급 연결로 채워졌다.
- backfill dry-run: 새 원문 키 65개(적용 뒤 새로 수집된 원문), 대표 표기·빈도 갱신 332개. 아직 `--apply`하지 않았다.

## 원문 키 backfill 재적용과 6단계 Wikidata 조회 (2026-09-27)

- 사용자 승인 후 `scripts/backfill_song_match_keys.py --apply`: 새 원문 키 65개(2차 적용 뒤 수집분), 대표 표기·빈도 갱신 332개를 한 transaction으로 커밋했다. 재실행 dry-run은 inserts·updates 0이다. 키 15,331개(confirmed 2,904, pending 12,427).
- `scripts/wikidata_title_ko.py`: 저장된 VocaDB 곡 ID(P11100)와 MusicBrainz work ID(P435)로만 Wikidata 항목을 찾는다(이름 검색 없음). `export`는 DB 읽기 전용이며 SPARQL 응답은 Git 제외 `db-migration/reports/wikidata/`에 cache한다. 결정 파일은 `migrations/catalog/title-ko-wikidata-1.json`, 검토 목록은 `migrations/catalog/title-ko-wikidata-manual-1.json`이다. `apply`는 dry-run, `apply --apply`는 한 transaction으로 `title_ko`(비어 있을 때만), 한국어 별칭, `song_external_ids`(wikidata)를 쓰고 영수증과 곡별 `catalog_changes`(QID, 라벨, CC0)를 남긴다.
- 규칙: 곡의 ID들이 서로 다른 항목을 가리키거나 한 항목이 여러 곡에서 나오면 충돌로 두고 쓰지 않는다. 한국어 라벨은 한국어 위키백과식 구분 괄호(`나조 (코마츠 미호의 싱글)`)를 떼고, 한글이 있고 원제와 다를 때만 쓴다.
- 결과(요청 8회): ID 1,060개(VocaDB 419, MusicBrainz 641)로 항목이 있는 곡은 90곡뿐이다. 88곡에 QID를 저장한다. 충돌 2건은 `さんぽ`(1575)와 `となりのトトロ`(1576)가 한 항목(Q1391673)에 연결된 경우라 쓰지 않았다. 한국어 라벨은 22곡에 있었다.
  - 번역 제목 9곡은 `title_ko`로 쓴다(`ふわふわ時間`→`폭신한 시간`, `飾りじゃないのよ涙は`→`장식이 아니야, 눈물은`, `フライングゲット`→`플라잉겟` 등). 기존 `title_ko` 355곡도 번역이나 외래어 표기(`ドライフラワー`→`드라이 플라워`) 방식이다.
  - 일본어 읽기를 한글로만 옮긴 13곡(`世界に一つだけの花`→`세카이니히토츠다케노하나`, `負けないで`→`마케나이데` 등)은 `title_ko`가 아니라 한국어 별칭(`song_aliases`, locale ko, source wikidata)으로 넣는다.
- 운영 DB dry-run: 곡 88곡, `title_ko` 9, 한국어 별칭 13, Wikidata ID 88. 아직 적용하지 않았다.
- 한계: `title_ko`가 없는 곡은 912곡이다. 원제가 라틴 문자인 271곡을 빼면 641곡(가창 15,210건)이 남고, Wikidata로 채울 수 있는 것은 그중 9곡이다. 빈도 상위 100곡이 4,913건, 200곡이 8,058건, 400곡이 12,263건을 차지한다. 나머지는 계획대로 출처 있는 제안을 검수 후보로 만들어 승인한 값만 쓰는 방식이 필요하다.
- 로컬 fixture: Wikidata 테스트 4개(라벨 규칙, 항목·곡 충돌, 적용·별칭·재실행·변경 행 거부, SPARQL batch·cache) 포함 전체 `python -m pytest -q -p no:cacheprovider` 374 passed, 376 warnings(기존 deprecated 경고).

## 6단계 한국어 제목 후보: 상위 200곡 (2026-09-27, 검수 대기)

- `scripts/title_ko_candidates.py`: `prepare`(DB 읽기 전용)는 `title_ko`가 없고 원제가 라틴 문자가 아닌 곡을 가창 수 순으로 고르되 Wikidata 결정 파일이 제목을 주는 곡은 뺀다. 입력과 기존 `title_ko` 60개 예시(`conventions.json`)는 Git 제외 `db-migration/reports/title-ko/round-1/`에 둔다. `export`는 조사 결과와 부모 검토(`migrations/catalog/title-ko-candidates-manual-1.json`)를 합쳐 `migrations/catalog/title-ko-candidates-1.json`을 만든다. 출처(공식 한국 발매, 한국어 위키백과, 여러 한국 출처의 같은 제목)와 URL이 있고 신뢰도 high면 `accept`, 번역만 있으면 `review`, 후보가 없으면 `skip`이다. `apply --apply`는 `accept`만 빈 `title_ko`에 쓰고 영수증과 곡별 `catalog_changes`(근거·출처, reviewed)를 남긴다.
- 대상 200곡(가창 8,057건)을 서브에이전트 5개가 40곡씩 조사했다(곡당 검색 최대 2회, 나무위키 제외). `kirocrew-research` 에이전트 하나가 역할이 다르다며 작업을 거절해 그 묶음은 `kirocrew-worker`로 다시 돌렸다.
- 결과: 출처 있는 제목 7곡(한국 사용례 6, 한국어 위키백과 1)이고 나머지 193곡은 에이전트 번역이다. 공식 한국 발매명은 찾지 못했다. 출처가 있고 high인 3곡만 `accept`, 197곡은 `review`다.
- 사용자 표기 방침(2026-09-27): 곡 이름은 직역에 가까운 번역을 우선하고, 말장난·조어·다의어처럼 번역이 애매하면 일본어 발음을 한글로 옮긴다. 가타카나 외래어는 한국어 외래어 표기를 쓴다.
- 부모 검토로 15곡을 고쳤다(조사 제안은 대안으로 남김).
  - 뜻이 분명한 말을 직역: `ヒバナ`→`불꽃`, `タマシイレボリューション`→`영혼 레볼루션`, `ウミユリ海底譚`→`바다나리 해저담`, `さよーならまたいつか！`→`안녕, 또 언젠가!`, `さよならメモリーズ`→`안녕 메모리즈`, `アイマイモコ`→`애매모호`, `勇者`→`용사`, `金曜日のおはよう`→`금요일의 좋은 아침`, `きらり`→`반짝`, `深昏睡`→`깊은 혼수`, `一輪花`→`한 송이 꽃`, 말장난을 한자음으로 살린 `二息歩行`→`이식보행`.
  - 애매해서 발음 표기: `チノカテ`→`치노카테`, `寄り酔い`→`요리요이`, `憂、燦々`→`유, 산산`, `桜流し`→`사쿠라나가시`.
- 검수용 목록: Git 제외 `db-migration/reports/title-ko/round-1/review.md`. 사용자 검수 뒤 `decision`을 반영해 적용한다.

## 6단계 한국어 제목: 나무위키 확인 (2026-09-27, 상위 200곡)

- 사용자 결정: 나무위키에서 한국어 이름을 가져온다. 문서 제목에 없으면 문서 내용도 본다. robots.txt는 문서 경로 `/w/`를 허용한다(2026-09-27 확인). 본문은 CC BY-NC-SA 2.0 KR이며 이름과 문서 URL만 저장하고, URL은 후보 파일과 `catalog_changes` 출처로 남긴다. 이용약관 페이지는 확인하지 못했다.
- `scripts/namuwiki_title_ko.py`: `fetch`는 `/w/<원제>`, 없으면 `/w/<원제>(<아티스트>)`를 약 3초에 1회 요청해 Git 제외 `db-migration/reports/title-ko/round-1/namu/`에 cache한다. `artists`는 곡 문서가 없는 곡의 아티스트 문서를, `extract`는 읽을 발췌(문서 제목, 개요, 원제가 나오는 구절)를 cache에서 만든다(요청 없음). 요청은 곡 문서 295회, 아티스트 문서 50회였다.
- 곡 문서 148곡(제목이 한국어 62, 일본어 86), 문서 없음 52곡(아티스트 문서 곡 목록에 원제가 있는 곡 24). 발췌 172개를 서브에이전트 4개가 읽었다(네트워크 없음, 직접 번역 금지). 한 에이전트가 직접 읽지 않고 다시 위임한 채 끝나서 그 묶음은 다시 돌렸다. 문서 제목이 한국어여도 애니메이션·한자 사전·같은 제목의 다른 곡 문서로 넘어간 경우(`春擬き`, `栞`, `燈`, `カーテンコール`, `さよならメモリーズ`)는 그 제목을 쓰지 않았다.
- 결과: 이 곡의 나무위키 이름을 찾은 곡 148곡. `scripts/title_ko_candidates.py export`가 나무위키 이름을 첫 후보로 두고(근거 `korean_usage`, 출처 문서 URL), 문서 제목이거나 원제가 함께 적힌 구절이 근거이면서 조사 후보와 같으면 `accept`로 둔다. 다르면 조사 후보를 대안으로 두고 `review`다.
  - `accept` 89곡(나무위키 일치 88, 기존 출처 1, 가창 3,592건), `review` 111곡(나무위키 이름이 조사 후보와 다름 59, 근거 구절 약함 1, 번역만 51).
  - 다른 예: `ウミユリ海底譚` 바다나리→갯나리 해저담, `暁の車` 새벽의 차→여명의 수레바퀴, `うっせぇわ` 웃세와→시끄러워, `桜色舞うころ` 벚꽃빛 흩날릴 때→연분홍빛 춤출 무렵, `花人局` 화인국→미인계.
- 로컬 fixture: 나무위키 테스트 3개(이름·본문 처리, 아티스트 변형 조회·cache·발췌, 개요 뒤 구절)와 후보 테스트(나무위키 일치·불일치·근거 약함) 통과.

## 6단계 한국어 제목 적용: 상위 200곡 (2026-09-27)

- 사용자가 `review.md`에서 4곡을 고치고 나머지를 승인했다: `粉雪` 가랑눈→가루눈, `君が夜の海に還るまで` 네가 밤바다에 돌아올 때까지→네가 밤바다로 돌아갈 때까지, `君の脈で踊りたかった` 너의 맥박에 맞춰 춤추고 싶었어→너의 맥박에 춤추고 싶었어, `ロストメモリー` 로스트 메모리→로스트메모리. 앞의 둘은 나무위키 이름 대신 조사 후보를 고른 것이다. 편집본은 Git 제외 `review.user-edited.md`로 보존했다.
- 결정은 `migrations/catalog/title-ko-candidates-manual-1.json`의 `user_review`(수정 4곡, `approved: all`)에 기록했다. `export`는 사용자 제목을 근거 `user_review`로 쓰고 바뀐 후보를 대안으로 남기며, `approved: all`이면 제목이 있는 모든 곡을 `accept`로 둔다.
- `title_ko_candidates.py apply --apply`: import 381, 200곡의 빈 `title_ko`를 한 transaction으로 채웠다(근거 나무위키 148, 사용자 수정 4, 나머지는 조사 번역·부모 수정). 재실행은 `already_committed`, 운영 DB 값은 결정 파일과 200곡 모두 같다.
- 적용 뒤 `title_ko`가 있는 곡은 1,267곡 중 555곡, 그 곡들에 연결된 가창은 33,664건이다. Wikidata 결정 파일(번역 제목 9, 별칭 13, QID 88)은 아직 적용하지 않았다.


## 6단계 한국어 제목: 201위 이후 432곡 (2026-09-27, 적용)

- 사용자 요청 방식: 결과를 파일로 보고 사용자가 그 파일을 고친 뒤 승인한다. `title_ko_candidates.py review-import`가 편집본(`review.md`)을 `review.user-edited.md`로 보존하고, 후보 칸이 바뀐 행을 manual `user_review.titles`로(`-`나 빈칸은 제외), 승인은 `approved: all`로 기록한다. 그다음 `export` → `apply` 순서다. `wikidata_title_ko.py review-import`도 같은 방식으로 `db-migration/reports/wikidata/review-1.md`(제목·별칭·QID 표)를 결정 파일에 반영한다.
- 대상: 남은 비라틴 원제 곡 432곡(가창 6,975건, Wikidata가 제목을 주는 9곡 제외). 대체 번역은 서브에이전트 6개가 웹 검색 없이 만들었다(직역 우선, 애매하면 발음 표기). 원제가 기호가 섞인 라틴 문자인 5곡(`S・K・Y`, `Fire◎Flower` 등)은 제목이 필요 없어 `skip`, 가나를 그대로 돌려준 `らしさ`는 부모 검토로 `다움`.
- 나무위키: 곡 문서 요청 661회, 아티스트 문서 114회. 곡 문서 299곡, 문서 없음 133곡(아티스트 문서 곡 목록에 원제가 있는 곡 55). 발췌 354개를 서브에이전트 6개가 읽어 271곡에서 이 곡의 나무위키 이름을 찾았다.
- 결과: `accept` 164곡(나무위키 이름이 대체 번역과 같고 근거 확인, 가창 2,732건), `review` 263곡(나무위키 이름이 번역과 다름 102, 근거 구절 약함 5, 번역만 133, 발음 표기만 23), `skip` 5곡. 검수 파일은 Git 제외 `db-migration/reports/title-ko/round-2/review.md`다.

### 운영 적용 (2026-09-27)

- 사용자가 두 검수 파일을 고치고 승인했다. 432곡 파일은 제목 9곡 수정, Wikidata 파일은 제목 1곡 수정(`ふわふわ時間` → 폭신푹신 타임).
- `title_ko_candidates.py --round 2 apply --apply`: import 382, `accept` 427곡(나무위키 268, 번역 130, 발음 표기 20, 사용자 수정 9), `skip` 5곡.
- Wikidata: 432곡 적용으로 곡 version이 바뀌어 `changed since export`로 거부됐고, cache로 다시 내보낸 뒤(요청 0회) 사용자 편집본을 다시 반영했다. 이때 두 가지를 고쳤다.
  - 발음 표기 라벨은 곡에 `title_ko`가 생겨도 별칭으로 남긴다. 이전에는 `title_ko`가 비어 있을 때만 별칭을 만들어, 432곡 적용 뒤 별칭이 0개가 됐다. 라벨이 `title_ko`와 같으면(`謎` 나조, `大声ダイヤモンド`) 넣지 않는다.
  - `review-import`는 검수 파일에 없던 행의 제목·별칭을 뺀다. 사용자가 보지 않은 행은 승인한 것이 아니기 때문이다(200곡 적용 전 목록에서 빠졌던 별칭 2곡).
  - 적용: import 383, 곡 88곡, 제목 9, 별칭 9, QID 88.
- HACHI 명의 정정: 사용자 검수에서 `八月の蛍`, `ばいばい、テディベア`의 명의를 HACHI만으로 고쳤다. 원인은 2차 파일럿이 세트리스트 표기 `HACHI`를 ハチ의 `name_latin` `Hachi`에도 맞춰, HACHI 곡 4곡(`Rainy proof`, `Twilight Line` 포함)에 ハチ를 함께 넣은 것이다. `scripts/remove_song_credits.py`와 `migrations/catalog/song-credit-removals-1.json`으로 4곡의 ハチ 명의를 지웠다(import 384, `correction`, 삭제 행은 catalog_changes에 보존). 곡 명의에 이런 충돌이 더 있는지 운영 DB를 읽기 전용으로 확인했고 이 4곡뿐이었다. `match_song_candidates.py`는 이제 원어 이름·별칭과 맞는 아티스트가 있으면 라틴·한국어 이름 일치를 쓰지 않는다.
- 결과: 한국어 제목이 있는 곡 991/1,267곡, 그 곡들의 가창 40,733건. 비라틴 원제인데 제목이 없는 곡은 7곡(`skip`과 Wikidata 충돌 곡)이다.
- 검증: 로컬 임시 PostgreSQL 전체 테스트 387개 통과(2026-09-27). 세 적용 모두 재실행 `already_committed`.

- Wikidata 결정 파일은 200곡 적용 뒤 cache로 다시 내보냈다(요청 0회): 제목 9, 별칭 11(2곡은 200곡 적용으로 제목이 생겨 빠짐), QID 88, 충돌 2.


## 2단계 결과: 카탈로그 아티스트 Spotify 계정 (2026-09-28 적용)

대상은 `show_in_catalog=true`인 활성 아티스트 68명 중 Spotify 링크가 없는 66명이다(Aimer, NEUN은 기존 계정). `scripts/spotify_account_candidates.py research`가 운영 DB를 읽기 전용으로 조회하고 Wikidata SPARQL 1회, Spotify API 529회를 호출했다.

- 자동 판정 33명: Wikidata에서 우리 YouTube 채널 ID(P2397)와 같은 항목의 Spotify ID(P1902)가 이름이 같은 프로필을 가리킨 24명, 이름이 같은 후보가 하나이고 그 발매 제목이 우리 곡 또는 본인 채널 영상 제목과 일치한 9명. Wikidata가 멤버 프로필(`ryo (supercell)`)을 가리킨 supercell은 자동 판정하지 않았다.
- 웹 확인 33명(서브에이전트): 공식 TuneCore·레이블 페이지 링크, Spotify 프로필에 걸린 공식 X, 공식 발매곡 일치로 22명 확인. 11명은 등록하지 않는다. 동명 무관 아티스트만 있음(LITA, TINA, BAMBI, SAKUYA, MOCO, KAGURA), 그룹 프로필로만 발매(ヨミ·カスカ=VESPERBELL, TINA=KMNZ), 발매 전 신인(宮島ルシェル, 傘屋くぐる, 電信柱ちゃん).
- `焔魔るり`는 Wikidata의 `Ruri Enma`(곡 없음) 대신 최신 발매가 있는 `焔魔るり` 프로필, NERO는 이름 검색에 나오지 않은 `KMNZ NERO` 솔로 프로필(TuneCore 공식 링크)이다.
- dry-run: `external_accounts` 55행 생성(모두 `collection_enabled=false`), owner·대표 링크 55행, 기존 계정 재사용 0.
- 사용자 검수(`review-import`): LITA `KMNZ LITA`(7a8HjYl08NU5Pems4rziwY), TINA `KMNZ TINA`(4Qamyt82PzhtZ04u51z216) 솔로 프로필을 추가하고, 妃玖는 Wikidata의 `KISAKI` 대신 `妃玖`(0zbH7OGsExOBMjiME8YhlE)로 바꿨다. 수정은 `migrations/catalog/spotify-account-manual-1.json`에 기록했다.
- 운영 적용(import 385): 계정 57개와 owner·대표 링크 57개를 한 transaction으로 만들고 변경 이력 114행을 남겼다. 재실행은 `already_committed`. 읽기 전용 점검에서 카탈로그 아티스트 68명 중 59명이 Spotify 계정을 가지며, 결정 파일과 다른 링크·수집 활성·표시 순서 중복은 0건이다. 계정이 없는 9명은 ヨミ, カスカ, MOCO, BAMBI, SAKUYA, KAGURA, 電信柱ちゃん, 宮島ルシェル, 傘屋くぐる다. 수집 활성화는 아직 하지 않았다.

## 3단계: Spotify 수집과 ISRC (2026-09-28 운영 수집 시작)

- 운영 반영(2026-09-28): 사용자가 배포 후 005를 적용했고 `--verify` 통과(001-005). `start_spotify_collection.py --apply`로 계정 59개 수집 활성화와 첫 작업 59개(job 17275~)를 한 transaction에 커밋했고, 재실행 미리보기는 켤 계정·넣을 작업 0이다. 약 2분 뒤 읽기 전용 확인: 작업 3개 성공·1개 실행 중·오류 0, 앨범 30개, 녹음 331개, ISRC 331개, Spotify 트랙 ID 340개(9개는 같은 ISRC 녹음에 합류).

- migration 005가 `recording_external_ids.platform`에 `isrc`를 허용하고 형식을 검사한다(대문자 12자, 하이픈 없음). 기존 UNIQUE로 한 ISRC는 한 녹음에만 붙는다.
- 앨범 수록곡 API에는 ISRC가 없어서, 수집 작업이 트랙 상세(`GET /tracks?ids=`, 50개씩)를 추가로 조회한다. market을 보내지 않아 Spotify가 트랙 ID를 다른 ID로 바꿔 주지 않으며, 응답 ID가 요청과 다르면 작업을 실패시킨다. 2026-09-28 실제 API로 이 응답에 `external_ids.isrc`가 있는 것을 확인했다.
- 저장: 새 Spotify 트랙의 ISRC가 이미 활성 녹음에 있으면 새 녹음을 만들지 않고 그 녹음에 Spotify 트랙 ID와 앨범 수록 관계만 붙인다(`isrc_joined`). 제목·한국어 표기·크레딧·공식 영상은 바꾸지 않는다. ISRC가 보관된 녹음이나 먼저 커밋한 다른 작업에 잡혀 있으면 새 녹음은 ISRC 없이 만들고 영수증에 `isrc_conflict`로 남긴다. 기존 녹음을 재수집할 때는 ISRC가 비어 있고 다른 녹음에 없을 때만 추가한다.
- 수집 시작: `scripts/start_spotify_collection.py`가 카탈로그 아티스트의 owner Spotify 계정 59개의 `collection_enabled`를 켜고(영수증·변경 이력) 계정마다 첫 `spotify_collect` 작업(`request_run=initial`)을 넣는다. revision 005가 없으면 거부하고, 재실행은 새 작업을 만들지 않는다. 2026-09-28 운영 DB 미리보기(읽기 전용): 계정 59, 켤 계정 59, 넣을 작업 59.
- 운영 순서: 코드 배포 → `migrate_catalog.py --apply`/`--verify`(005) → `start_spotify_collection.py` 미리보기 → 승인 후 `--apply`. 작업은 배포된 worker가 `RUNTIME_CUTOVER_ENABLED`와 `AGENT_ENABLED`가 켜져 있을 때 처리한다. 계정당 앨범 10개씩 후속 작업이 이어지고 요청 간격은 기본 1초다.
- 시장 기준 변경(2026-09-28): 수집이 `market=KR`일 때 일부 일본 발매가 로마자·영어 제목으로 왔다(LEWNE `空想線` → `Kuusousen`, `ノクタンブルー` → `Nocturne Blue`). 수집 중 저장된 트랙 2,385개를 `market=JP`로 다시 읽기 전용 조회하니 13개 제목이 달랐다(`Sincerely Yours` → `草々不一` 등). 원제 보존을 위해 수집 adapter의 앨범 목록·앨범·수록곡 조회를 JP 시장으로 바꿨다. 배포 전 작업은 KR로 계속 돌며, 재수집은 기존 앨범·녹음 제목을 덮어쓰지 않으므로 이미 저장된 제목은 별도 검수 정정이 필요하다.
- 검증(2026-09-28, 로컬 임시 PostgreSQL·가짜 provider): ISRC 저장·다른 발매 합류·보관 녹음 충돌·형식 CHECK, 004→005 업그레이드와 옛 CHECK 복원 감지, 수집 시작 대상 선별·005 가드·재실행 멱등.


### 3단계 수집 결과 점검 (2026-09-28, `scripts/audit_spotify_collection.py`, 읽기 전용)

- 작업 200개 모두 성공(실패 0, 작업 시간 초과 재시도 1회 후 성공). 앨범 1,282, 녹음 6,338(모두 ISRC), Spotify 트랙 ID 7,379. ISRC로 기존 녹음에 합류한 트랙 1,041개(녹음 815개). `song_id`가 붙은 녹음은 아직 0.
- `review_candidate` 320건은 다른 계정 작업이 먼저 만든 공동 발매 앨범을 다시 만난 경우로, 설계대로 덮어쓰지 않았다. 다른 충돌은 0.
- 크레딧 없는 녹음 2,644개·앨범 256개: `appears_on`/`compilation` 앨범(OST, 옴니버스)의 다른 아티스트 트랙까지 앨범 전체로 저장된 결과다.
- 녹음 0인 계정 4개(羽緒, 妃玖, 焔魔るり, 水瀬凪): Spotify API가 KR·JP 모두 앨범 0을 돌려준다. 프로필은 있으나 API로 보이는 발매가 없다.
- JP 시장 재조회: 등록 계정 59개의 앨범 목록을 `market=JP`로 다시 읽으니 1,599개 중 274개가 저장된 것과 **다른 앨범 ID**였다(38개 계정, 그중 139개는 일본어 제목). JP 전용 판이 따로 있는 발매가 많다는 뜻이다. 같은 ID의 제목만 바뀌는 경우는 적다(트랙 13개 확인, `Kuusousen`은 JP로도 같은 ID·같은 제목). 따라서 JP 코드로 재수집하면 이 274개가 **새 앨범 행으로 중복 생성**되고 녹음만 ISRC로 합쳐진다. 재수집 전에 KR 판 앨범을 JP 판에 대응시켜 정정하거나 병합하는 단계가 필요하다.


### 3단계 재수집 준비: JP 시장·크레딧 트랙만 (2026-09-28 코드 완료, 운영 적용 대기)

- 사용자 결정: KR 시장으로 들어온 수집분을 지우고 JP 시장으로 다시 들여온다. 참여 앨범·컴필레이션은 등록 아티스트가 크레딧된 트랙만 저장한다.
- 수집 코드: 앨범 크레딧에 등록 아티스트가 없는 앨범(OST·옴니버스 등)은 등록 아티스트가 크레딧된 트랙만 남기고, 뺀 트랙 ID는 영수증 `skipped_other_tracks`에 남긴다. 본인 명의 앨범은 전 트랙을 저장한다.
- 녹음 0 계정 4개(羽緒, 妃玖, 焔魔るり, 水瀬凪): 계정 연결은 맞다. 네 프로필 모두 인기곡이 있고 그 곡의 앨범·트랙 크레딧이 등록 ID와 같다. `/artists/{id}/albums`만 모든 `include_groups`에서 0을 돌려준다(2026-09-28 확인). 이 API는 다른 계정에서도 발매를 빠뜨리는 것으로 알려져 있어(Spotify 개발자 커뮤니티 보고), 모든 계정의 마지막 목록 페이지 작업이 **검색 보완**을 함께 한다: 등록 ID의 프로필 이름으로 앨범·트랙 검색을 `next`가 없을 때까지(최대 offset 1000) 넘기고 인기곡을 더해, **등록 ID가 앨범이나 트랙에 크레딧된 앨범만** 모은다. 목록에 없고 아직 저장되지 않은 앨범은 10개씩 후속 작업(`album_ids`)으로 넣는다. 등록 ID가 유일한 신원이며 이름만 같은 결과는 쓰지 않는다. 검색 API는 한 페이지에 `limit`보다 적게 줄 수 있어(limit 10 → 5개) `next`로 끝을 판단한다. 웹 플레이어 내부 API는 접근 보호 우회·약관 문제로 쓰지 않는다. 효과 측정(2026-09-28, JP 시장 읽기 전용): 59개 계정의 목록 API 앨범 1,599개에 검색 보완이 **98개**를 더한다(24개 계정). 목록이 0인 4개 계정에서 32개(焔魔るり 14, 水瀬凪 11, 羽緒 4, 妃玖 3), 그 밖에 ヨノ 12, fhána 7, 瀬戸乃とと 7, やなぎなぎ·花譜 각 5 등.
- 삭제: `scripts/purge_spotify_collection.py`가 Spotify 앨범 ID가 있는 앨범과 Spotify 트랙 ID가 있는 녹음(수록·크레딧·외부 ID 포함)을 한 transaction으로 지우고, 행마다 이전 값을 `catalog_changes`(`delete`)에 남긴다. 곡 연결·한국어 제목·공식 영상·가사·변경 이력이 있거나 다른 앨범에 수록된 녹음이 있으면 거부한다. 운영 미리보기(읽기 전용): 앨범 1,282, 녹음 6,338, 수록 7,385, 외부 ID 13,717, 거부 사유 0.
- 재수집: `start_spotify_collection.py --run jp-1`이 계정 59개에 새 작업을 넣는다(`initial` 작업과 멱등 키가 다름). 운영 미리보기: 넣을 작업 59.
- 운영 순서: 코드 배포 → `purge_spotify_collection.py --apply` → `start_spotify_collection.py --run jp-1 --apply`.
