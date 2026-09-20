# 기존 세트리스트 이관 결과

실행일: 2026-09-21. 대상은 `.env.catalog`의 `NEW_CATALOG_DATABASE_URL`이 가리키는 `catalog-v1`이다. 비밀 연결 문자열은 기록하지 않았다. 원본은 Git에서 제외한 `db-migration/archive/legacy-neon/neonDB-2026-09-21.dump`이며 SHA-256은 `0A059E007616E99CFE02D1980AB70AEB8B755084E92DC020B448483EF0C56B27`이다.

## 반영 결과

새 카탈로그에 YouTube 영상 5,783건, 라이브 아카이브 5,783건, 진행자 연결 5,783건, 세트리스트 곡 73,841건을 넣었다. 원문 근거 `source_documents` 및 아카이브 연결은 각각 5,784건이다. 원래 댓글과 사용자가 수정한 FHo 목록은 별개 문서로 보존했다. 새 DB의 기존 아티스트 81건과 외부 계정 155건을 재사용했다.

영상 5,743건의 `source_account_id`는 기존 YouTube 채널의 고정 ID와 새 외부 계정을 대조해 채웠다. 채널 근거가 없는 40건은 NULL이다. 대표 아티스트는 기존 진행자 표기와 계정 소유자, 그룹 소속을 함께 대조했다. KMNZ/VESPERBELL 그룹 채널에서 제목이 멤버를 명시한 203건은 해당 멤버로 수정하고 변경 전후 값과 근거를 감사 이력에 기록했다. 업로드 계정은 그룹 채널 계정으로 유지했다.

일반 아카이브 5,761건을 고정 ID 배치로 이관했다. 중복 영상 ID 중 목록이 같거나 한 목록이 다른 목록의 부분집합인 20건은 더 완전한 아카이브 하나를 선택해 142곡을 이관했고, 중복 원본 아카이브 ID는 이관 영수증의 대응표에 남겼다. 원본 곡 행 427건은 이 과정에서 중복으로 접었다.

| 영상 ID | 사용자 결정과 반영 |
| --- | --- |
| `xF44iE-Sok0` | 10곡 목록이 있는 기존 아카이브 4136만 반영. 다른 1곡 목록은 제외. |
| `tR4jmnavtDk` | 라이브 아카이브가 아니므로 새 DB에 반영하지 않음. |
| `cyRZGtNx_a4` | 조회수 이정표 행이므로 새 DB에 반영하지 않음. |
| `FHoFxjx8QGU` | 사용자 제공 8곡을 반영. 6번 시작 시각은 확인한 영상 길이 4,499초 이내인 `00:51:31`(3,091초)로 수정. 기존 댓글과 수정 목록을 별개 근거로 저장. 영상 제목의 `#KMNZTINA`에 따라 대표 진행자는 KMNZ TINA. |

제외는 **새 DB 이관에서 제외**한다는 뜻이다. 원본 덤프와 원본 ID는 감사와 재현을 위해 보존한다. 결정 내용은 [`legacy-setlist-decisions.json`](../migrations/catalog/legacy-setlist-decisions.json)에 기록했다.

## 검증과 후속 범위

실제 새 DB를 읽기 전용으로 재검증했다. 영상·라이브 건수가 각각 5,783건, 곡이 73,841건이며, 대표 아티스트와 `archive_artists` 연결 불일치, 영상 길이 밖의 곡 시작, 중복 YouTube 영상 ID, 곡의 출처 문서와 아카이브 출처 연결 불일치는 모두 0건이다. 제외한 두 영상도 새 DB에서 0건이다. `xF44iE-Sok0`은 10곡, `FHoFxjx8QGU`는 8곡이며 FHo의 시작 초는 `738, 1014, 2188, 2455, 2793, 3091, 3961, 4232`로 확인했다. 그룹 멤버 수정 영수증은 203건이다. 로컬 PostgreSQL을 사용하는 이관 테스트는 `3 passed`(2026-09-21)였다.

곡 마스터 연결은 이번 범위가 아니므로 `performances.song_id`는 NULL이다. 아카이브의 `setlist_state`는 미검수 원본임을 나타내는 `partial`이다. 이름이 정제됐더라도 원본 곡명·원곡자·시각의 품질은 개별 검수를 거치지 않았다. 대표 아티스트가 숨김 상태인 기존 아티스트의 라이브가 있을 수 있으며 공개 설정은 변경하지 않았다.

### 추가 반영: 임시 가창자 연결

2026-09-21 사용자 요청에 따라 모든 세트리스트 곡 73,841건에 방송 대표 진행자를 `performance_artists(role='lead')`로 임시 연결했다. 이 연결은 곡별 실제 가창자 검수 결과가 아니며, 게스트 가창이나 합창은 나중에 수정해야 한다. 37개 배치의 영수증과 곡별 `catalog_changes`에 `review_status=provisional`을 남겼다. 반영 뒤 가창자 연결 누락·대표 진행자와 연결 불일치는 각각 0건이고, KMNZ TINA의 통계 대상 곡은 556건으로 확인했다. 이관 테스트 4건과 새 카탈로그 조회 테스트 3건이 통과했다.

재현/감사 도구는 `scripts/import_legacy_setlists.py`, `scripts/correct_legacy_group_live_hosts.py`, `scripts/apply_reviewed_legacy_setlists.py`, `scripts/backfill_performance_hosts.py`, `scripts/verify_legacy_setlist_import.py`다. 쓰기 도구는 기본적으로 dry-run이고 `--apply`에서만 새 DB에 쓴다. `catalog_imports`의 고정 operation ID와 manifest 해시, `catalog_changes`의 행별 감사 기록으로 재실행을 확인한다. 세부 로컬 점검 결과는 Git에서 제외된 `db-migration/reports/`에 있다.
