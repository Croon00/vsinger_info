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
