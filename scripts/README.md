# 운영 도구

프로젝트 루트에서 실행한다. 먼저 소스의 인자 처리와 기본 동작을 확인한다. `argparse`를 사용하는 도구는 `--help`로 인자를 확인할 수 있지만, `run_admin.py`처럼 바로 실행하는 파일도 있다. 아래 도구는 서버 시작이나 테스트에 자동 연결되지 않는다. 조회 API에서 호출하지 않는다.

| 도구 | 역할·실행 영향 |
| --- | --- |
| `music_jobs.py` | 신규 DB 음악 작업 요청 검증·등록·상태·취소·단일 실행·readiness. [2단계 계약](../docs/backend-service-step-2-jobs.md), [YouTube URL/범위 지정 수집](../docs/backend-service-step-3-youtube.md), [Spotify 계정 명시 수집](../docs/backend-service-step-4-spotify.md). 관리자 앱 없이 실행 |
| `run_admin.py` | 빌드된 `admin-web/`과 로컬 관리자 API 실행 |
| `start-local.ps1` | 프로젝트 가상환경의 API 8000, 조회 웹 5174를 숨김 실행. 사용 중인 포트는 건너뜀 |
| `register-local-startup.ps1` | Windows 로그인 시 `start-local.ps1`을 실행하는 예약 작업 등록 |
| `migrate_catalog.py` | 새 DB 상태/계약 검사. `--apply`는 명시적 스키마 생성 |
| `migrate_runtime_state.py` | `LEGACY_DATABASE_URL`을 읽기 전용으로 사용하는 선택 이전·receipt 확인 도구. 운영 DB 이전은 [2026-09-23 기록](../docs/backend-cutover-2026-09-23.md)대로 완료했다. 동일 manifest의 재실행은 적용 없이 receipt를 반환한다. 새 적용은 별도 대상·범위가 확정된 경우에만 검토 |
| `import_legacy_setlists.py` | 보존한 이전 DB 덤프의 세트리스트 검사·고정 배치 반영 (`--apply`, `--apply-safe-duplicates`) |
| `correct_legacy_group_live_hosts.py` | 그룹 채널 영상의 명시적 멤버 진행자 203건 검사·수정 (`--apply`) |
| `apply_reviewed_legacy_setlists.py` | 사용자 결정 파일에 따른 예외 영상 검사·반영 (`--apply`) |
| `backfill_performance_hosts.py` | 세트리스트 곡을 방송 대표 진행자의 임시 가창으로 연결 (`--apply`, 감사 기록) |
| `backfill_catalog_video_durations.py` | 새 카탈로그의 누락 영상 길이를 YouTube API로 조회 (`--fetch`)하고 검증된 값만 반영 (`--apply`) |
| `apply_reviewed_duration_conflict.py` | 사용자 검수로 바로잡은 곡 시각과 API 영상 길이를 함께 반영 (`--apply`) |
| `verify_legacy_setlist_import.py` | 새 카탈로그의 이관 건수·참조·예외 영상 읽기 전용 검증 |
| `audit_song_master_readiness.py` | 곡 마스터 1단계 읽기 전용 측정. 계정 보유율·원문 키 빈도·기존 곡 상태를 Git 제외 `db-migration/reports/song-master-audit/`에 저장 |
| `backfill_song_match_keys.py` | 세트리스트 원문을 `song_match_keys`로 집계. 기본 dry-run(004 적용 전에도 미리보기), `--apply`는 004 필요·영수증 기록. 기존 연결로만 상태를 유도하고 수동 판정은 유지. performances·songs는 변경하지 않음 |
| `review_partial_match_keys.py` | 일부만 연결된 원문 키 검토. `export`는 읽기 전용으로 `migrations/catalog/partial-match-key-decisions.json` 생성(정확 일치만 confirm 미리 채움), `apply`는 dry-run, `apply --apply`는 판정만 저장·영수증 기록. 내보낸 뒤 바뀐 키는 거부 |
| `link_performances_from_match_keys.py` | 확정 원문 키로 미연결 가창에 song_id 연결. YouTube 수집 경로와 같은 조회 규칙(정확 일치, 원곡자 원문이 없으면 `곡명 / 원곡자` 분리 쌍). 기본 읽기 전용 dry-run, `--apply`는 2,000 ID 단위로 영수증·행별 변경 이력(`match`: exact/split)과 함께 커밋. 원문·기존 연결은 변경하지 않고 보관·병합된 곡은 제외 |
| `match_song_candidates.py` | 곡 마스터 5단계 파일럿. 기존 곡(`--songs`)과 상위 pending 원문 키(`--keys N`)를 VocaDB → UtaiteDB → MusicBrainz에서 정확 제목으로 찾아 auto/review/none으로 분류. DB 읽기 전용, 보고서와 provider 응답 cache는 Git 제외 `db-migration/reports/song-master-candidates/` |
| `seed_song_master.py` | 곡 마스터 5단계 적용. `export`는 파일럿 보고서·아티스트 조사·1차 검수·`migrations/catalog/song-master-manual.json`을 합쳐 `migrations/catalog/song-master-decisions.json` 생성(DB 읽기 전용), `apply`는 dry-run, `apply --apply`는 새 아티스트·새 곡·외부 ID·빈 title_latin·키 확정을 한 transaction과 영수증·변경 이력으로 저장. 내보낸 뒤 바뀐 행이 있으면 전체 거부, 재실행은 no-op. 가창 연결은 하지 않음. `--round N`(2 이상)은 입력을 `db-migration/reports/song-master-candidates/round-N/`, 수동 결정을 `song-master-manual-N.json`, 결정 파일을 `song-master-decisions-N.json`으로 따로 쓰고, `--round N prepare`가 파일럿 보고서와 DB(읽기 전용)로 아티스트 조사·검수 입력을 만듦 |
| `merge_catalog_entities.py` | 같은 사람·같은 곡이 두 행으로 저장된 아티스트·곡 병합. 인자는 결정 파일(`migrations/catalog/entity-merges-N.json`). 기본 읽기 전용 dry-run, `--apply`는 한 transaction으로 원본을 가리키는 모든 행을 대상으로 옮기고(중복 행은 삭제해 감사 기록에 보존), 원본 이름을 별칭으로 남기고 원본을 보관, 곡은 `song_merges`에 기록. 모르는 외래 키가 있으면 거부, 재실행은 no-op |
| `remove_song_credits.py` | 다른 아티스트로 잘못 들어간 곡 명의(`song_artists`) 삭제. 인자는 결정 파일(`migrations/catalog/song-credit-removals-N.json`). 기본 읽기 전용 dry-run, `--apply`는 한 transaction으로 삭제하고 남은 명의 순번을 0부터 다시 매기며 삭제 행을 catalog_changes에 보존(`correction` 영수증). 없는 명의나 명의가 0개가 되는 곡은 전체 거부, 재실행은 no-op |
| `wikidata_title_ko.py` | 곡 마스터 6단계. `export`는 저장된 VocaDB 곡 ID(P11100)·MusicBrainz work ID(P435)로 Wikidata 항목을 찾아 `migrations/catalog/title-ko-wikidata-N.json` 생성(DB 읽기 전용, SPARQL cache는 `db-migration/reports/wikidata/`). 한글 번역 라벨은 `title_ko`(빈 곡만), 읽기만 옮긴 라벨(`title-ko-wikidata-manual-N.json`)은 한국어 별칭, QID는 `song_external_ids`. `apply`는 dry-run, `apply --apply`는 한 transaction·영수증·변경 이력, 재실행 no-op |
| `title_ko_candidates.py` | 곡 마스터 6단계 검수 후보. `prepare`는 `title_ko` 없는 비라틴 원제 곡을 가창 순으로 골라 조사 입력 생성(DB 읽기 전용, `db-migration/reports/title-ko/round-N/`), `export`는 조사 결과·부모 검토(`title-ko-candidates-manual-N.json`)를 `migrations/catalog/title-ko-candidates-N.json`으로 합침(출처 있는 high만 `accept`, 번역은 `review`). `apply`는 dry-run, `apply --apply`는 `accept`만 빈 `title_ko`에 기록, 재실행 no-op |
| `namuwiki_title_ko.py` | 곡 마스터 6단계 나무위키 확인. `fetch`는 후보 입력의 원제(없으면 `원제(아티스트)`) 문서를 약 3초에 1회 조회해 cache, `artists`는 곡 문서가 없는 곡의 아티스트 문서 조회, `extract`는 cache에서 읽기용 발췌 생성. 모두 Git 제외 `db-migration/reports/title-ko/round-N/`에 쓰고 DB는 건드리지 않음. 읽은 결과(`namu-found-*.json`)는 `title_ko_candidates.py export`가 합침 |
| `spotify_account_candidates.py` | 곡 마스터 2단계 Spotify 계정 후보. `research`는 카탈로그 표시 아티스트 중 Spotify 링크가 없는 행을 DB 읽기 전용으로 모아 Wikidata(YouTube 채널 ID→P1902)와 Spotify 이름 검색·앨범/인기곡 제목 대조로 후보 생성(응답은 Git 제외 `db-migration/reports/spotify-accounts/cache/`), `export`는 웹 확인 결과(`research-*.json`)·수동 파일(`spotify-account-manual-1.json`)을 합쳐 `migrations/catalog/spotify-account-decisions-1.json`과 `review.md` 생성, `review-import`는 수정한 `review.md`와 승인 기록. `apply`는 dry-run, `apply --apply`는 `accept`만 `external_accounts`(수집 비활성)와 owner 링크로 한 transaction에 기록, 재실행 no-op |
| `start_spotify_collection.py` | 곡 마스터 3단계 수집 시작. 카탈로그 표시 아티스트의 owner Spotify 계정을 미리보기(기본, 읽기 전용)하고, `--apply`는 revision 005 적용을 확인한 뒤 비활성 계정의 `collection_enabled`를 켜고(영수증·변경 이력) 계정마다 첫 `spotify_collect` 작업을 job repository로 등록. 재실행은 새 작업을 만들지 않음. 실제 수집은 배포된 worker가 처리 |


| `export_admin_contract.py` | 관리자 리소스에서 JSON 가져오기 계약 생성 |
| `migrate_avatars.py` | 프로필 이미지 준비·검수 보고서·명시적 반영 |
| `normalize_artist_names.py` | 기존 아티스트 별칭·소속 정규화 |
| `import_vsinger_profiles.py` | `data/seeds/` 프로필 반영 |
| `register_missing_youtube_channels.py` | 시드의 누락 채널 등록 |
| `register_riot_music_youtube_monitors.py` | RIOT MUSIC 채널 모니터 등록 |
| `backfill_youtube_channel.py` | 지정 채널 과거 영상 수집·저장 |
| `backfill_riot_music_youtube.py` | RIOT MUSIC 채널 과거 자료 수집·저장 |
| `backfill_youtube_covers.py` | 공식 커버 영상 수집·저장 |
| `retry_pending_youtube_setlists.py` | 미처리 세트리스트 재시도 |
| `translate_recent_youtube_setlists.py` | 최근 세트리스트 번역·저장 |
| `refresh_jpop_playlist_tj.py` | TJ 노래방 대조 자료 갱신 |
| `cache_x_profile_images.py` | X 프로필 이미지 수집·캐시 |

실행 전 각 도구의 dry-run/apply 기본값과 사용할 DB를 확인한다. 정상 실행은 단일 `DATABASE_URL`의 신규 DB만 사용한다. 이전 조사 도구에만 `LEGACY_DATABASE_URL`을 별도로 준다. 보존된 구 수집·번역 스크립트는 연결 진입점에서 차단되며 정상 worker가 호출하지 않는다. [백엔드 구조](../docs/backend-architecture.md)를 따른다.

프론트 화면 점검·성능 측정 스크립트는 `web/scripts/`에서 유지한다. 일회성 데이터 조사 스크립트와 출력은 `.tmp/`에, 보존할 원본은 `db-migration/archive/`에 둔다.
