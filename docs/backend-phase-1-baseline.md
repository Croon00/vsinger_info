# 백엔드 통합 1단계 — 선택 이전 조사 준비

기준: 2026-09-21. 최종 방향은 [신규 DB 일원화 계획](backend-consolidation-plan.md)을 따른다.

**상태: 1단계 완료.** 2026-09-21 두 DB를 읽기 전용으로 재조회해 계정 대응·선택 집합·writer 후보를 산출했다. 사용자 결정에 따라 연결된 X 계정의 수집 활성 상태를 신규 DB에 반영하고, 잘못된 X source 3개를 제외했으며, YouTube 서브 채널 5개를 등록했다. 실제 콘텐츠 이전·수집·전송·runtime 전환은 실행하지 않았다. 최종 미해결 매핑 충돌은 0개다.

## 1. 확정 사항

- API·수집기·Discord 봇의 운영 저장소는 신규 DB 하나다.
- 기존 DB는 SELECT만 허용하는 이전 소스로 취급한다. schema·데이터·권한·활성 플래그를 변경하지 않는다.
- 수집 재개·알림 중복 방지에 필요한 행·필드만 이전한다. 나머지는 기존 DB에 그대로 보존한다.
- X는 신규 `external_accounts`에서 수집한다. `collection_enabled`와 `archived_at`을 존중하며 별도 계정 명부를 만들지 않는다.
- Discord는 X 원문 URL 전송만 남긴다. 관리/조회 명령 전체, X 분류, X 글의 YouTube 자동 등록은 제거한다.
- 관리는 admin-web으로 모으되 개편은 후속 작업이다. 이번 조사나 봇 축소의 선행 조건이 아니다.
- Google Calendar는 데이터를 기존 DB에 보존하고 코드·설정·API를 legacy로 격리한다.
- 1단계의 조사는 읽기 전용으로 수행한다. 단, 이번에 사용자가 명시적으로 결정한 X `collection_enabled` 승계만 신규 DB에 감사 영수증과 함께 반영했다. 콘텐츠 이전·수집·전송·프로세스 정지·원격 명령 삭제는 실행하지 않는다.

관리 위치와 Google 처리 방식은 결정 완료다. 사용자에게는 실제 조사에서 발견한 매핑·소유권·cursor 충돌처럼 데이터에 따라 달라지는 사항만 묻는다.

## 2. 참고 기준선

### 2.1 기존 DB

2026-09-21의 기존 읽기 전용 조사에서 업무 테이블 20개와 migration revision 표 부재를 확인했다. 아래 건수는 **이전 목표 건수가 아니다.**

| 테이블 | 당시 행 수 | 이번 조사에서 판단할 범위 |
| --- | ---: | --- |
| `artists` | 94 | 프로필 이전 제외. 선택 route·작업에 필요한 소유권만 확인 |
| `artist_sources` | 84 | 신규 X 계정 대응·cursor·실행 상태 |
| `artist_agencies` | 3 | 이전 제외 |
| `event_candidates` | 357 | 이전 제외 |
| `google_oauth_tokens` | 0 | 이전 제외, 기존 DB 보존 |
| `source_items` | 10,510 | 선택 delivery 참조·확인된 미완료 처리·cursor 경계의 최소 원문 |
| `youtube_live_archives` | 7,153 | 필요한 수집 상태·외부 영상 ID만 검토, 콘텐츠 일괄 이전 제외 |
| `youtube_song_performances` | 79,513 | 이전 제외 |
| `youtube_cover_videos` | 9,790 | 이전 제외 |
| `youtube_cover_collaborators` | 2,419 | 이전 제외 |
| `karaoke_source_matches` | 3,191 | 기본 제외. 특정 수집 재개 필수 여부만 검토 |
| `youtube_channel_monitors` | 52 | 신규 YouTube 계정 대응·감시 설정 |
| `youtube_channel_videos` | 6,541 | 재개·중복 방지·미완료/재시도 상태만 선별 |
| `notification_routes` | 51 | 선택 계정의 route·채널·소유권 |
| `notification_deliveries` | 4,335 | 선택 route의 성공 전송 이력 |
| `calendar_syncs` | 0 | 이전 제외, 기존 DB 보존 |
| `songs` | 32 | 이전 제외 |
| `song_lyrics` | 2 | 이전 제외 |
| `spotify_track_title_translations` | 0 | 기본 제외 |
| `namuwiki_templates` | 1 | 이전 제외 |

당시 X source는 모두 X 계정으로 활성 78·비활성 6개였다. route 51개는 모두 활성·source별·타입 all이며 default route는 없었다. delivery 4,335개는 모두 message ID가 있었다. 이는 성공 이력 승계의 참고 근거이지 신규 계정 활성화나 전체 이관의 근거가 아니다.

아티스트 소유권은 system 77·Discord 사용자 2·소유자 없음 15개였다. YouTube monitor 52개는 모두 활성이었고, archive 중 607개에 X source/item 참조가 있었다. 기존 X→YouTube 연결은 원 DB에 그대로 남기며 새 작업 생성의 근거로 쓰지 않는다.

### 2.2 신규 DB

앞선 읽기 전용 검증에서 다음을 확인했다.

| 항목 | 당시 확인 값 |
| --- | --- |
| schema revision / contract | `001` / `catalog-v1` |
| migration checksum | `e086e34bbe5a1c43635bc381fbd3926635e453dcb4ab53a7beb8445b6a4a864d` |
| 업무 / migration 테이블 | 31 / 1 |
| `initial_data_imported` | true |
| identity 외 전체 행 | 363,010 |
| `catalog_imports` | 246: 초기 1, batch 82, correction 163 |

영상·라이브·방송 출연자 연결은 각각 5,783개, 가창·가창자 연결은 각각 73,841개, source document/archive source는 각각 5,784개였다. 당시 참조·영상 길이·중복·근거 불일치 검사 결과는 0건이었다. 상세는 [세트리스트 이관 기록](setlist-migration-report.md)을 참고한다. 신규 DB를 비우거나 초기 데이터를 다시 주입하지 않는다.

스키마의 `external_accounts`에는 platform, nullable platform_id, handle, URL, collection_enabled, archived_at, version이 있다. `(platform, platform_id)` 고유 제약과 아티스트 연결 표를 사용한다.

로컬 관리자 SQLite 검수 장부는 그대로 유지한다. 서비스 운영 상태 이전과 함께 로컬 도구 저장소까지 변경하지 않는다.

### 2.3 이번 조사 결과

조사 도구는 기존 DB에 `SET TRANSACTION READ ONLY`를 적용하고 신규 DB도 매핑 조사 동안 읽기 전용으로 열었다. URL·토큰·원문은 출력하지 않았다. 산출물은 Git 제외 경로 `db-migration/reports/single-db-readiness/`에 저장했다.

| 항목 | 결과 |
| --- | ---: |
| 구 X source | 84 |
| 신규 계정에 연결된 source / 신규 계정 | 78 / 73 |
| `platform_id` 연결 source / 계정 | 74 / 71 |
| 유일한 handle 연결 source / 계정 | 4 / 2 |
| 신규 계정에 연결된 X source / 제외한 잘못된 source | 81 / 3 |
| 연결된 계정의 최종 활성 / 비활성 | 70 / 3 |
| 선택 route / delivery / 참조 원문 | 51 / 4,365 / 4,558 |
| 성공 이력 중 message ID 누락 | 0 |
| YouTube monitor 연결 / 누락 | 52 / 0 |
| 연결 monitor의 미완료 영상 작업 | 99 |

신규 DB의 X 계정은 조사 전 모두 `collection_enabled=false`였다. 사용자 결정에 따라 `platform_id` 또는 유일한 정규화 handle로 연결된 계정의 기존 `is_active`를 승계했다. 70개를 활성화하고 기존에서 비활성인 3개는 비활성으로 유지했다. 변경된 70개는 version·updated_at을 갱신했고 `catalog_imports` correction 영수증 1개와 계정별 `catalog_changes`를 같은 트랜잭션에 기록했다. 기존 DB는 수정하지 않았다.

handle로 연결한 source는 `iori_m_RIOT` 2개와 `miona_s_RIOT` 2개이며 각각 신규 계정 하나로 합쳐졌다. 또한 교정된 handle로 `IMI_RKMusic`→`@IMI0131`, `HONKTHEHORN`→`@HONKTHEHORN_`, `haru_saruhi`→`@harusaruhi`를 기존 신규 계정에 연결했다. 세 계정은 이미 다른 정확한 source 연결을 통해 수집 활성 상태였으므로 추가 DB 변경은 없었다. 신규 계정의 `platform_id`는 구 값으로 덮어쓰지 않았다.

MEMESIA `@MEMESIA_0224`, supercell `@supercell_sc`, fhána `@fhana_jp`는 사용자가 잘못된 계정으로 확정했다. 신규 계정을 만들지 않고 수집·선택 이전 대상에서 제외한다. 기존 DB의 source 행은 변경하지 않는다.

YouTube monitor 52개는 모두 고정 channel ID로 연결됐다. 누락됐던 花譜, ヰ世界情緒, 理芽, 春猿火, 幸祜의 서브 채널은 공식 YouTube Data API로 channel ID·현재 handle·canonical URL·uploads playlist를 확인했고, 신규 DB의 정확한 아티스트에 등록했다. 모두 `relationship=owner`, `is_primary=false`, `position=1`, `label='YouTube sub'`, `collection_enabled=true`다. 각 아티스트의 기존 X 연결은 position 1에서 2로 이동했다. 계정 5개·관계 5개 생성과 X 관계 5개 변경은 단일 트랜잭션으로 적용하고 `catalog_imports` 및 `catalog_changes`에 기록했다. 등록 후 필드와 관계를 읽기 전용으로 재검증했다. 기존 channel video 4개는 모두 처리 완료 상태라 미완료 작업은 없다. 전체 monitor의 처리 완료 영상 ID 6,444개 중 5,742개는 신규 `videos`에 있고 702개는 없다. 완료 콘텐츠 전체를 작업 상태 명목으로 이전하지 않으며, 중복 방지 방식은 2단계 schema에서 확정한다.

같은 `Hao_RKM` 계정에 구 source 14(HAO)와 79779(羽緒)가 함께 연결된다. 두 cursor 값이 다르며 source 14의 cursor가 더 최신이다. source 14에는 route 1개·원문 291개·delivery 141개가 있고 source 79779에는 route와 delivery 없이 원문 81개가 있다. 두 source의 외부 게시글 ID 합집합은 292개다. 80개는 양쪽에 중복되고 URL·본문·게시 시각 충돌이 0개이며, source 79779에만 있는 게시글은 1개다. 사용자 결정에 따라 신규 `(account_id, external_id)` 중복 키로 291개와 고유 1개를 합쳐 292개를 이전 대상으로 확정했다. cursor는 source 14를 사용하고 delivery 141개는 그대로 연결한다. route를 신규 계정 기준으로 합쳤을 때 동일 계정·guild·channel 중복은 0개다.

교정된 `@HONKTHEHORN_`에는 구 source 87479와 87563이 함께 연결된다. 87479의 cursor가 더 최신이므로 이를 사용한다. 87563의 게시글 5개는 route·delivery가 없고 수집 재개에 필요하지 않아 이전하지 않으며 기존 DB에 보존한다.

## 3. 1단계 실행 절차

### A. 대상과 읽기 전용 경계 확인

1. 현재 설정 로더와 연결 대상 identity·revision을 확인한다. URL·키·토큰 값은 출력하지 않는다.
2. 기존 DB 연결은 읽기 전용 트랜잭션으로 제한한다. `init_db()`, migrate/apply, seed, repair, provider 로그인, Discord 로그인은 호출하지 않는다.
3. 기존 DB에 쓰는 API·runtime·scheduler·script·Google 소비자를 코드에서 추적한다. 실행 중인 프로세스 여부는 별도 읽기 전용 확인으로 구분하며 정지하지 않는다.
4. 조사 시각·신규 DB revision·계정 version을 기록한다. 테이블 건수는 필요한 집계만 재확인하고 원문/자격증명을 보고서에 덤프하지 않는다.

### B. 외부 계정·콘텐츠 참조 매핑

1. 구 X source → 신규 X external_account는 provider 고정 ID를 우선하고, 없으면 같은 플랫폼의 유일한 정규화 handle로 매핑한다.
2. 구 YouTube monitor → 신규 YouTube external_account, 필요한 영상 ID → 신규 videos를 매핑한다.
3. handle·URL에서 얻은 handle이 계정 하나와 유일하게 일치하면 연결 근거를 기록한다. 신규 `platform_id`는 구 값으로 덮어쓰지 않는다. 후보가 여러 개면 보류한다. 1단계에서 외부 provider에 ID 검증 요청을 보내지 않는다.
4. 결과는 matched / missing_account / missing_platform_id / conflict / excluded로 구분하고 근거를 남긴다. 구 DB와 신규 DB의 숫자 ID가 같다는 이유로 연결하지 않는다.
5. 활성·보관 상태 차이는 매핑 성공 여부와 별도로 기록한다. 신규 비활성·보관 계정을 구 설정으로 활성화하지 않는다.
6. 같은 신규 계정으로 모이는 복수 source의 cursor·소유권·route를 비교한다. cursor 최댓값 선택이나 route 무조건 병합을 하지 않는다.

### C. 최소 이전 집합 산출

1. 매핑된 계정 중 전환 범위에 포함할 계정과 기존 route·monitor를 선택한다. 비활성 설정은 보존 필요성을 명시하고 활성화하지 않는다.
2. 선택 route의 재전송 방지 이력과 그 이력이 참조하는 원문을 포함한다. 필요한 원문에는 외부 ID·본문·URL·시각을 보존하고 분류 필드는 제외한다.
3. cursor 경계·수집 재개·중복 작업 방지·확인된 미완료/재시도에 필요한 행만 추가한다. 원문에 delivery가 없다는 이유만으로 pending을 만들지 않는다.
4. 이미 신규 DB에 있는 영상·라이브는 참조한다. 구 가창·커버·곡·가사·공연 후보·Google·템플릿을 함께 복제하지 않는다.
5. 각 원본 테이블에 대해 선택 조건·필드 허용 목록·참조 의존성·선택/제외 사유와 건수를 기록한다. 참조를 유지하는 데 필요한 최소 소유권 정보만 포함한다.
6. 어떤 비필수 데이터도 선택 명세에 없으면 이전하지 않도록 기본 제외 규칙을 둔다.

### D. 사용자 결정이 필요한 충돌 정리

다음 경우에만 근거·영향·권장안을 묶어 질문한다. 조사 자체는 충돌 없는 항목부터 계속할 수 있다.

- 구 수집 계정에 대응하는 신규 계정이 없거나 handle 후보가 여러 개인 경우.
- 신규 계정 비활성/보관과 현재 운영 source 활성 상태가 충돌하는 경우.
- 여러 source의 cursor가 달라 누락 또는 과거 재전송 위험이 있는 경우.
- 같은 계정·guild/channel으로 수렴하는 route의 소유권/전송 이력이 충돌하는 경우.
- 특정 작업 재개에 허용 목록 밖의 데이터가 반드시 필요한 경우.

해당 항목은 결정 전 보류한다. 소유자 없는 행에 임의 소유자를 부여하거나 새 계정을 자동 생성하지 않는다.

### E. 명세와 후속 검증 준비

1. 선택 행·필드·대응표·제외 사유·검증 기준으로 이전 명세를 확정한다.
2. 신규 계정 version과 원본 cursor/route 상태가 달라지면 명세 재검토가 필요하도록 기준값을 남긴다.
3. dry-run, FK/고유성, 제외 데이터 유입 0, 성공 알림의 pending 변환 0, 재실행 중복 0 검증 항목을 정의한다.
4. 기존 DB writer를 배포 시 어디서 정지할지 정리한다. 기존 DB의 활성 플래그 변경·계정 권한 변경을 정지 절차로 사용하지 않는다.
5. 2단계에 넘길 신규 schema 요구와 보류 목록을 기록한다. 이 단계에서 DDL이나 실제 이전은 실행하지 않는다.

## 4. 조사 산출물

실행 시 Git 제외 경로인 `db-migration/reports/single-db-readiness/`에 다음 파일을 생성한다. **현재는 산출물 규격만 정했으며 파일을 생성하지 않았다.** 실제 저장 전 ignore 여부를 확인하고 접근을 제한한다.

| 파일 | 내용 |
| --- | --- |
| `account-mapping.json` | 원본 source/monitor ID, 신규 account/video ID, 고정 ID 근거, 상태·활성 차이 |
| `selection-manifest.json` | 선택/제외 조건, 필드 허용 목록, 원본 행 식별자·대상 참조, 건수·검증 기준값 |
| `conflicts.json` | 충돌 원인·영향·권장안·사용자 결정 또는 보류 상태 |
| `writer-inventory.json` | 기존 DB 쓰기 진입점, 초기화 경로, 전환·정지 방법 |

문서에는 비밀정보와 상세 사용자/채널 ID를 제외한 집계만 기록한다. 원문 덤프·OAuth token·DB URL은 산출물에 포함하지 않는다. 실제 이전 때 필요한 원문은 허용 목록에 따라 직접 읽어 신규 DB에 반영한다.

## 5. 소비자와 전환 준비 목록

| 현재 소비자 | 조사·후속 처리 |
| --- | --- |
| `app/core/config.py`, `app/db/session.py`, `app/core/db.py` | 현재 DATABASE_URL 소비자·직접 SQL·초기화 차단 위치 조사 |
| `app/db/catalog_session.py`, `app/admin/config.py` | 공통 Settings·신규 DB 연결 재사용, 읽기/쓰기 경계 유지 |
| migration/import·avatar 설정과 scripts | .env.catalog 직접 로딩 목록화. DB 외 이미지 설정도 공통화 |
| scheduler의 X source/artist JOIN | external_accounts와 계정별 상태로 전환 |
| notification repository | 계정 참조·route별 권한·내구성 있는 delivery로 전환, item_type 제외 |
| YouTube monitor/live·Spotify·가사·노래방 | 신규 콘텐츠 참조와 필요한 작업 상태를 구분. 전체 구 콘텐츠 이전 금지 |
| artists.py·songs.py 및 service/repository | 신규 마스터 계약으로 통합하고 수집·소유권·생성 책임 분리 |
| `web/` | /api/v2 DTO·ID를 유지하며 최종 /api로 이동 |
| `web.bak/`·구 API | 기존 DB 쓰기 경로 종료 후 legacy 격리 |
| `admin-web/`·로컬 검수 SQLite | 현재 기능 유지. 운영 설정 화면 개편은 후속 |
| Google OAuth·Calendar | 정상 mount·refresh·sync·설정 연결 제거 후 legacy 격리 |

현재 구 API는 `/api`와 prefix 없는 경로로, 신규 조회는 `/api/v2`로 mount된다. artists 등의 ID·응답 충돌을 조사하며 단순 prefix 제거로 통합하지 않는다.

현재 `init_db()`에는 DDL뿐 아니라 아티스트/source 시드, route 중복 정리, event 날짜 보정, 표시명 정규화가 섞여 있다. API·봇·scheduler·일부 script에서 호출하므로 연결 URL만 바꾸면 안 된다. 기존 DB baseline이나 revision 표를 추가하지 않고 신규 DB에만 후속 migration을 설계한다.

## 6. 기능 제거·보존 목록

### Discord 명령 전체 제거

코드에 정의된 32개 명령이 대상이다. 실제 원격 등록 개수와 동일하다는 의미는 아니다.

| 그룹 | 명령 |
| --- | --- |
| 아티스트·source·route | artist_add, artist_list, artist_delete, source_list, source_disable, source_enable, route_add, route_list, route_delete, route_test, source_test, route_replay |
| Google | google_connect |
| YouTube | youtube_live_add, youtube_riotmusic_add_all, youtube_riotmusic_backfill_all, youtube_channel_add, youtube_channel_list, youtube_channel_delete, youtube_channel_check, youtube_live_list, youtube_live_show, youtube_songs_by_artist, youtube_song_search |
| 곡·가사 | lyrics_source, song_save, song_show, song_show_by_id, song_lyrics_update |
| 로컬 tree에서 이미 숨긴 나무위키 | namuwiki_template_add, namuwiki_template_list, namuwiki_render |

CommandTree·interaction·명령 전용 SQL/import·attachment·backfill task·자동 sync도 제거한다. Discord lifecycle, channel 조회와 URL 전송 adapter는 유지한다. 배포 때 해당 애플리케이션의 global/guild 등록 범위를 확인한 뒤 삭제하며 1단계에서 로그인하거나 원격 명령을 수정하지 않는다.

### X 경로

- 제거: item_type·classification_confidence·notice 고정 기록, 타입별 route/message, music_graph, X 분류/공연 추출 schema·prompt·helper, 링크 페이지 본문 수집, event/Calendar helper.
- 제거: scheduler의 `_register_youtube_live_links`와 X 글에서 YouTube 등록을 시작하는 보조 호출.
- 보존: provider adapter, 게시글 원문·외부 ID·URL·시각, 중복 방지, 검증된 cursor, 계정별 route·전송 이력.
- 보존: 독립 YouTube channel polling·pending live/setlist, Spotify·가사·노래방 작업. setlist 추출과 OpenAI 소비자는 X 분류 삭제만을 이유로 제거하지 않는다.
- 구 DB의 분류 컬럼·X→YouTube 참조·Google 데이터는 그대로 둔다. 새 저장 계약에서 사용하지 않는다.

기존 코드에서 확인한 위험: 최근 글 기본 한도 5·pagination 부재, 원문/cursor/delivery의 분리 commit, bot offline 시 pending 미생성, 중복 원문 skip 시 미전송 재시도 누락, 성공 delivery만 저장하는 구조다. 후속 구현에서 고치며 1단계는 현재 상태를 수정하지 않는다.

## 7. 완료 조건과 다음 실행

### 준비 완료

- [x] 신규 DB 단일 운영·기존 DB 무변경·최소 선택 이전 원칙을 확정했다.
- [x] external_accounts 기반 수집과 활성/보관 상태 처리 기준을 정했다.
- [x] admin-web 후속 개편과 Google legacy 격리를 반영했다.
- [x] 읽기 전용 조사 절차·보고서 규격·충돌 질문 기준을 정했다.

### 실행 결과와 남은 항목

- [x] 대상 identity/revision과 기존 DB 읽기 전용 경계를 확인했다.
- [x] X·YouTube 계정과 필요한 영상의 실제 대응표를 작성했다.
- [x] route·delivery·원문·작업의 최소 선택 행/필드 명세를 작성했다.
- [x] 연결된 X 계정의 기존 활성 상태를 신규 DB에 영수증과 함께 반영했다.
- [x] 기존 DB writer·초기화 후보 42개 파일을 정적 목록화했다. 실제 실행 경로별 정지 지점은 2단계 코드 분리와 함께 확정한다.
- [x] 잘못된 X source 3개를 신규 생성·수집·이전 대상에서 제외했다.
- [x] 교정된 X handle 3개를 기존 신규 계정에 연결하고 활성 상태를 확인했다.
- [x] `Hao_RKM`의 source 14 cursor와 route/delivery 사용을 확정했다.
- [x] source 79779에만 있는 게시글 1개를 포함해 `Hao_RKM` 원문 합집합 292개를 이전 대상으로 확정했다.
- [x] 공식 정보로 조사한 YouTube 서브 채널 5개를 확인받아 등록하고 X position을 2로 이동했다.
- [x] 결정을 반영해 선택 명세와 2단계 schema 요구를 확정했으며 미해결 매핑 충돌은 0개다.

실제 콘텐츠 이전과 runtime 전환은 아직 시작하지 않았다. 1단계 명세는 완료됐으며 다음 작업은 2단계 신규 운영 schema·공통 설정 기반이다.

검증: 2026-09-21 조사 스크립트 문법 검사, 두 DB identity/revision 및 매핑의 읽기 전용 재조회, 활성 상태 반영 후 재조회, 보고서 재생성을 수행했다. 실제 Discord·provider·Google·LLM은 호출하지 않았다.
