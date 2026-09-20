# 기존 세트리스트의 새 카탈로그 이관 계획

작성일: 2026-09-21. 이 문서는 이관 전 계획과 조사 결과를 기록한다. 이관은 같은 날 실행됐으며 실제 결과는 [이관 결과](setlist-migration-report.md)를 참조한다. 아래의 초기 DB 상태와 실행 순서는 당시의 사전 상태 및 계획이다.

## 목표와 범위

기존 PostgreSQL 덤프의 유튜브 라이브 세트리스트를 AI 정제·곡 마스터 병합 없이 새 카탈로그의 `videos` → `live_archives` → `performances`에 옮긴다. 원래 곡명·원곡자·타임스탬프를 `raw_*` 필드에 남기고, 원문 댓글이 있으면 `source_documents`와 `archive_sources`에도 보존한다. 기존 DB ID는 새 DB PK로 재사용하지 않는다.

1차 범위는 세트리스트가 있는 라이브다. 곡 마스터(`songs`, `song_artists`), 노래방 번호, 커버, 가사, 앨범, 수집기 설정은 이관 대상에서 제외한다. 이관한 `performances.song_id`는 NULL로 둔다. 기존 서비스 DB와 수집 경로는 계속 분리한다.

## 확인한 원본과 규모

- 원본: Git 제외 경로 `db-migration/archive/legacy-neon/neonDB-2026-09-21.dump`. PostgreSQL 18.6 custom dump, 12,064,663바이트. SHA-256: `0A059E007616E99CFE02D1980AB70AEB8B755084E92DC020B448483EF0C56B27`.
- 덤프의 `youtube_live_archives` 7,124행, 서로 다른 YouTube 영상 ID 6,851개. 영상 ID가 중복된 그룹 121개에 추가 아카이브 273행이 있다.
- `youtube_song_performances` 74,295행, 아카이브 5,838개. 고아 가창 행은 0건이다. 이 행들을 **1차 가창 원본**으로 쓴다. `youtube_live_archives.setlist` JSON은 원본 대조 자료로 보존한다.
- 영상 ID가 중복되지 않은 아카이브 중 가창 행이 있는 5,763개에 73,701행이 있다. 이 수는 후보 규모이며 아직 새 DB 충돌, 공백 값, 시간 범위, 참조 관계 검사를 통과한 확정 이관 건수가 아니다.
- 중복 영상 그룹 중 가창 행이 있는 그룹은 22개이며, 해당 그룹 전체의 가창은 594행이다. 자동 병합·삭제하지 않고 보류 목록으로 낸다.
- 가창 행이 있지만 `setlist` JSON이 빈 아카이브 135개에 1,253행이 있다. 반대로 JSON만 있고 가창 행이 없는 아카이브는 0개다. `pending` 상태에도 가창 행 2,392개가 있으므로 상태값만으로 제외하지 않는다.
- `top_comment`가 있는 아카이브 6,178개, `video_title`이 없는 아카이브 71개다. 가창 행이 있는 아카이브에는 빈 `video_title`이 없었다. 7,124개 영상 ID 모두 새 스키마의 YouTube ID 형식에 맞는다.

위 원본 수치는 덤프를 `pg_restore --data-only`로 **로컬에서 읽어 집계한 값**이다. 2026-09-21 `.env.catalog`의 `NEW_CATALOG_DATABASE_URL`로 새 카탈로그를 읽기 전용 확인했다. `catalog-v1`, 초기 반영 완료이며 `artists` 81건, `external_accounts` 155건, `artist_external_accounts` 155건, `videos`·`live_archives`·`performances`는 각각 0건이다. 실행 직전에는 이 상태와 충돌 여부를 다시 확인한다.

## 필드와 신뢰 수준

| 기존 자료 | 새 자료 | 규칙 |
| --- | --- | --- |
| `youtube_live_archives.youtube_video_id`, `video_title`, `published_at`, `duration_seconds` | `videos.platform='youtube'`, `platform_video_id`, `title`, `published_at`, `duration_seconds` | 영상 ID로 식별. 확인된 값만 입력. `availability='unknown'`. 기존 영상이 있으면 제목만으로 덮어쓰지 않는다. |
| 기존 아카이브의 `broadcast_at` | `live_archives.broadcast_at` | 값이 있을 때만 복사. 업로드 시각으로 대신 채우지 않는다. |
| 가창 행이 있는 아카이브 | `live_archives.setlist_state='partial'` | 미검수 이관 상태를 표시. `complete`는 이후 검수 시에만 사용. |
| `youtube_song_performances` 각 행 | `performances` 각 행 | `archive_id`는 새 ID로 재매핑. `ordinal`은 `(start_seconds, 기존 performance.id)` 순으로 1부터 부여. `start_seconds`, `song_title→raw_title`, `original_artist→raw_artist`, `timestamp_text→raw_timestamp`를 보존. `song_id=NULL`, `end_seconds=NULL`. 같은 곡·시각의 행도 원본이 별도 행이면 유지. |
| `youtube_live_archives.top_comment` | `source_documents.content_text`, `archive_sources` | 실제 댓글 텍스트가 있을 때만 `youtube_comment` 근거를 생성. 원본 아카이브 ID와 덤프 해시, 영상 ID를 `source_metadata`에 남긴다. 직접 댓글 주소·댓글 ID가 없으면 만들어 넣지 않는다. |
| 기존 아카이브/가창 ID | 반영 영수증·출처 메타데이터 | 새 PK에 복사하지 않는다. 배치별 대응표와 제외 사유를 로컬 보고서 및 반영 영수증에 남긴다. |

### 아티스트·업로드 계정 연결

2026-09-21 로컬 검수 저장소 `review.sqlite3`의 **반영 완료 기록**에는 새 아티스트 ID 81건과 외부 계정 ID 155건이 있다. 새 DB의 같은 테이블 건수도 읽기 전용으로 일치함을 확인했다. 이름·ID·플랫폼 ID의 개별 대응은 이관 전 `catalog_instance.id`를 포함해 재검증한다.

기존 덤프에서 사용할 근거는 (1) `youtube_channel_videos.archive_id → monitor_id → youtube_channel_monitors.youtube_channel_id`, (2) `youtube_live_archives.youtube_video_id → youtube_channel_videos.youtube_video_id`, (3) `youtube_live_archives.source_id → artist_sources.artist_id/external_user_id`, (4) `performer_name`이다. 새 카탈로그에서는 YouTube/X의 `external_accounts.platform_id → artist_external_accounts.artist_id`, 아티스트의 `name_native`·`name_ko`·`name_latin`·`artist_aliases.alias`로 확인한다. **채널 ID와 X 사용자 ID는 서로 다른 플랫폼 식별자**로 취급한다.

가창 행이 있는 5,838개 아카이브를 로컬 반영 기록과 대조한 예비 결과:

| 근거 | 연결된 아카이브 | 해석 |
| --- | ---: | --- |
| 기존 채널 모니터의 YouTube 채널 ID가 새 YouTube 계정 ID에 단일 대응 | 5,751 | `videos.source_account_id` 후보. 업로드 계정이다. |
| 채널/X의 고정 플랫폼 ID가 단일 새 아티스트를 지목 | 5,834 | 대표 아티스트 판단 근거. 채널 소유자가 실제 진행자와 다를 수 있다. |
| 이름·계정 근거가 모두 같은 아티스트를 지목 | 5,833 | 자동 연결 후보. 원본 영상 ID 중복과 새 DB 충돌 검사는 별도. |
| 이름·계정 근거가 서로 다른 아티스트를 지목 | 5 | 수동 판정. 네 건은 HONK THE HORN 채널과 멤버 X 출처, 한 건은 VESPERBELL 채널과 YOMI 진행자 표기. |

`performer_name`에서 이름 단독 비교로 맞지 않은 표기는 6종이다. `Enma_Ruri`·`Minase_Nagi`·`Setono_Toto` 같은 밑줄 표기와 `KMNZ NERO`·`KMNZ TINA`·`KMNZ LITA` 같은 그룹 접두 표기가 포함된다. 무제한 유사도 검색 대신 정규화된 정확한 이름/별칭, 고정 플랫폼 ID, 명시적 소수 대응표만 사용한다. 채널 모니터 코드가 그룹 영상 제목에서 멤버를 고르는 특수 규칙도 검토한다.

필드별 반영 규칙:

1. `videos.source_account_id`: 기존 `archive_id` 연결을 우선하고, 없으면 영상 ID로 채널 모니터를 찾는다. 얻은 `youtube_channel_id`가 새 `external_accounts(platform='youtube', platform_id=...)` 한 건과 일치할 때만 채운다. X 게시자 계정을 YouTube 업로드 계정 자리에 넣지 않는다. 현 예비 자료에서 나머지 87개는 채널 근거가 없어 NULL 후보이다.
2. `live_archives.primary_artist_id`: 단독 대응된 `performer_name`과 채널 소유 아티스트가 같으면 그 아티스트를 쓴다. 진행자 이름이 별도 인물로 확인되면 실제 진행자를 우선하고, 채널 소유는 `source_account_id`에 유지한다. `source_id`의 X 작성자는 게시자 근거이며 자동으로 진행자나 게스트가 되지 않는다. 단서가 어긋나는 다섯 건은 작은 수동 대응표로 판정한다.
3. `archive_artists`: 확인된 대표 진행자를 `role='host'`로 연결한다. 추가 인물은 실제 출연 근거가 있을 때만 `guest`로 연결한다. 계정 소유 또는 X 게시 사실만으로 출연자를 추가하지 않는다. 관리자 검증에서는 `primary_artist_id`가 이 테이블에도 있어야 한다.
4. `performance_artists`: 아카이브의 대표 진행자를 모든 곡의 가창자로 일괄 복사하지 않는다. 곡별 가창자가 명시된 자료나 단독 가창이라고 검증된 좁은 범위에만 `lead`를 넣고, 통계에서 빠지는 건수를 별도 보고한다. 가창자를 넣었다면 해당 아티스트가 `archive_artists`에도 있어야 한다.

자동 연결과 수동 판정 결과에는 사용한 기존 ID·플랫폼 ID·이름 규칙·새 아티스트/계정 ID를 남긴다. 새 DB 읽기 전용 확인에서 로컬 반영 기록과 불일치하면 해당 대응을 중단한다.

## 실행 순서

1. **사전 점검**: 덤프 해시를 재확인하고 새 DB를 읽기 전용으로 접속한다. `catalog_instance`의 스키마 버전·초기 반영 상태, 기존 `videos`/`live_archives`/`performances` 수, 영상 ID 충돌, 기존 영수증을 기록한다. 대상 백업 또는 복구 지점을 확보한다. 빈 DB라고 가정하지 않는다.
2. **변환·분류**: 덤프에서 필요한 3개 테이블과 댓글만 읽어 로컬 staging 자료를 만든다. 영상 ID별 그룹을 만들고 중복 그룹, 기존 새 DB 영상과의 충돌, 필수값 공백, 음수·비정상 시각, 중복 순번, 부모 참조 오류를 검출한다. 중복 없는 5,763개 후보를 우선 처리하고, 각 제외 사유와 원본 ID를 보고서에 기록한다. `setlist` JSON과 가창 행의 차이는 검수 후보로만 표시한다.
3. **로컬 시험**: 새 DDL과 일부 실제 덤프 행을 임시 로컬 PostgreSQL에 적용해 FK/CHECK/UNIQUE, 한글·일본어 텍스트, 동일 시각의 여러 곡, 163곡짜리 긴 세트리스트, 재실행을 시험한다. 실제 자료 시험 결과는 fixture 테스트와 분리해 기록한다.
4. **이관 도구**: 별도 명시적 CLI를 만든다. 기본 동작은 dry-run이며 `--apply`만 새 DB에 쓴다. 일정 수의 아카이브를 한 트랜잭션으로 묶고, 각 배치에 고정 `operation_id`와 입력 manifest 해시를 사용한다. `catalog_imports`의 `batch_import` 영수증과 `catalog_changes` 이력, 새 ID 대응표를 같은 트랜잭션으로 기록한다. 현재 초기 반영은 완료 상태이므로, 실행 직전에 이 상태가 달라졌다면 중단해 원인을 확인한다.
5. **충돌 정책**: `(platform, platform_video_id)`가 이미 있으면 자동 덮어쓰지 않는다. 같은 덤프·같은 배치의 기존 영수증이면 결과를 조회해 재사용한다. 새 DB의 다른 자료와 충돌하거나 원본의 영상 ID가 중복된 그룹은 비교 보고서로 보내고 수동 선택 뒤 별도 배치로 반영한다. 이름만으로 아티스트나 곡을 병합하지 않는다.
6. **검증·공개**: 배치별 입력/삽입/재사용/보류/실패 건수와 원본→새 ID 대응을 대조한다. 원본 74,295 가창 행이 새 `performances`에 정확히 한 번씩 들어갔거나 사유가 있는 보류 목록에 있는지 확인한다. 새 API의 라이브 상세·전역 검색을 샘플 검사하고 아티스트별 목록/통계의 미연결 건수를 별도 표시한다. 영수증과 DB 상태를 읽어서 완료를 판정한다.

## 실행 관문과 복구

- 실행 전 산출물: 원본 해시, 새 DB 현재 상태, 대상 충돌 목록, dry-run 건수, 필드 변환 규칙, 배치 manifest. 실제 반영은 이 산출물이 나온 뒤 별도 실행한다.
- 중간 실패: 해당 배치 전체를 rollback한다. 응답 유실 시 같은 `operation_id`의 영수증을 먼저 조회한다. 입력·정책이 바뀌면 새 manifest와 새 배치 ID를 쓴다.
- 이미 반영된 행의 정정: 새 원문/변경 이력을 남기는 별도 correction 배치로 처리한다. 전체 재복원이나 기존 행 삭제로 복구하지 않는다.
- 새 API 표시: `show_in_catalog`가 false이거나 아티스트 연결이 없는 라이브는 아티스트 목록에서 접근하기 어렵다. 1차 이관 완료와 아티스트별 탐색·통계 완성을 별도 완료 기준으로 보고한다.
