# 새 DB 전체 테이블·필드 설명서

작성일: 2026-09-19 · 문서 버전: 초안 2 — 사용자 간소화 결정 반영

**2026-09-19 원격 PostgreSQL에 음악 카탈로그 31표·276컬럼을 생성했다. 2026-09-21 운영 10표를 후속 revision 002로 추가해 기술용 migration 표를 포함한 public 표는 42개다. 이 문서는 카탈로그 31표와 로컬 검수 구조를 설명하며 운영 표는 [2단계 결과](backend-phase-2-runtime-schema.md)를 따른다. 기존 수집기·봇은 아직 기존 DB를 사용한다.**

실행 DDL과 DB가 강제하는 규칙/향후 API 검증의 구분은 [마이그레이션 안내](../migrations/catalog/README.md), 당시 확인 값은 [적용 보고서](../migrations/catalog/schema-application-report.json)를 참고하세요.

통합 아티스트 명부와 음악 카탈로그 우선 이전은 사용자 결정으로 확정했습니다. 원격 컬럼·타입·기본값·DB 제약은 migration 001에 반영했습니다. 관리자 서비스 검증과 로컬 검수 저장소도 구현했으며 실제 범위는 [관리자 안내](admin-web-plan.md)를 따릅니다. 초기 데이터는 사용자가 전체 반영 대상을 검수한 뒤에만 입력합니다. 아래 설계 설명과 실행 계약이 다르면 버전 고정 SQL 및 관리자 계약을 기준으로 확인합니다.

기준 문서: [DB 구조·이전 계획](db-renewal-plan.md), [관리자 웹 계획](admin-web-plan.md).
기존 세 schema_spec 문서는 참고 자료이며 이 문서는 통합 명부 결정과 후속 계획을 반영한 상세안입니다. 서로 다른 자료형/필드가 있으면 조용히 혼합하지 않고 이 상세안을 검토한 후 구현 계약을 확정합니다.

## 이번에 확정한 간소화 범위

- 유지: 곡의 title_latin(영문/로마자 표기), language_code(언어), karaoke_numbers(노래방 번호), 원어/한국어 곡명, 복수 원곡자 연결, 가사와 곡/녹음 구분.
- 제거: 이미지 출처 별도 필드, 별도 프로필 링크 표, 작사·작곡·편곡·프로듀서 크레딧, 곡 slug, 원곡자의 가창/제작 역할, 공연 출연진의 세부 역할, 기존 DB와 새 ID 대응표.
- 프로필 링크는 external_accounts와 artist_external_accounts에서 통합 관리합니다. 아티스트 slug와 방송/실제 가창자의 역할은 이번 간소화 대상이 아닙니다.
- 원본 덤프는 별도 백업 파일로 보관합니다. 기존 table/id를 새 음악 데이터·검수 payload·변경 provenance에 넣지 않으며 이전 즐겨찾기를 자동 승계하지 않습니다.
- 로컬 초안→새 DB ID 대응과 반영 영수증은 중복 저장 방지·복구에 사용하므로 유지합니다. 이는 기존 DB의 ID 대응표와 다릅니다.

## 읽는 방법

- **테이블**은 한 종류의 정보를 모은 표, **필드/컬럼**은 그 표의 항목입니다. 한 행은 아티스트 한 명, 가창 한 번 등 하나의 기록입니다.
- **PK**는 그 행의 고유 번호, **FK**는 다른 표에 있는 행의 번호를 참조하는 연결입니다.
- **NULL**은 아직 모르거나 해당하지 않아 비워 둔 상태입니다. 빈 문자열·0·가짜 날짜와 다릅니다.
- **UNIQUE**는 같은 값 또는 같은 값 조합을 중복 등록하지 못하게 하는 규칙입니다.
- **JSON/JSONB**는 구조를 가진 묶음 자료입니다. 원문·초안·반영 이력에 쓰며 확정된 곡/아티스트 관계를 대신하지 않습니다.
- **version/revision**은 동시에 수정했을 때 오래된 화면이 최신 값을 덮어쓰지 못하도록 비교하는 번호입니다.
- **manifest**는 이번에 반영할 데이터·버전·관계를 고정한 명세, **hash**는 그 내용이 달라졌는지 비교하는 지문입니다.
- 예시 번호·이름·주소·시각은 형식 설명용이며 검수 완료 데이터나 seed가 아닙니다. 모든 표에 ID와 시각 필드까지 명시했습니다.

### 저장소를 두 개로 나누는 이유

| 위치 | 표 수 | 역할 |
| --- | ---: | --- |
| 새 Neon PostgreSQL | 41 | 음악 카탈로그 31표와 수집·Discord·worker·이전 감사 운영 10표 |
| 내 PC의 관리자 SQLite | 9 | 원본 파일 목록, 편집 초안, 승인·보류, 반영 준비와 복구 |

음악 카탈로그의 31개 중 다수는 아티스트·곡 등을 연결하는 작은 표입니다. 관리자는 카탈로그 표를 직접 편집하지 않고 아티스트·곡·라이브·공연·앨범 폼으로 작업합니다. Discord·알림·수집 cursor 운영 표는 admin-web 개편 전까지 직접 관리 화면에 노출하지 않으며 Google 표는 추가하지 않았다.

SQLite의 UUID·시각·JSON은 TEXT로 저장하는 제안입니다. JSON은 파싱 검증하고 BOOLEAN은 INTEGER 0/1로 제한합니다. SQLite 내부 FK 검사를 활성화합니다. 원격 ID는 두 DB 사이에 실제 FK를 걸 수 없으므로 서버가 대상 카탈로그와 존재 여부를 확인합니다.

### 공통 규칙과 상세화한 제안

1. 원격 일반 행 ID는 INTEGER 자동 증가, catalog_instance.id와 저장 작업 ID는 UUID입니다. 관계 행에도 별도 ID를 주어 검수·변경 이력에서 식별합니다.
2. 필수 텍스트는 공백만 있는 값을 허용하지 않습니다. 선택 텍스트의 빈 값은 NULL로 정리하되 원문 스냅샷은 원래 값을 보존합니다.
3. 한국어 이름이 없으면 NULL입니다. 화면의 영어/원어 대체 표시는 프론트의 표시 규칙이며 DB에 중복 번역을 만들지 않습니다.
4. 주요 수정 대상에는 version과 archived_at을 제안합니다. archived_at은 이전 계획의 ‘사용 중지/숨김’을 구체화한 필드이며 자동 삭제 시각이 아닙니다. 복원 시 NULL로 돌리고 변경 이력을 남깁니다.
5. 아티스트의 show_in_catalog=false는 탐색 목록 숨김일 뿐 곡 연결·통계 삭제가 아닙니다. archived_at이 있는 자료는 기본 신규 선택/공개 조회에서 제외하되 연결 이력을 지우지 않습니다. 보관된 부모 아래 자료의 노출도 조회 서비스에서 일관되게 처리합니다.
6. 관계 표는 별도 version 대신 소유 부모의 version을 같은 트랜잭션에서 올립니다. 바뀐 관계가 영향을 주는 승인·검색 캐시도 무효화합니다.
7. 이름에는 전체 UNIQUE를 걸지 않습니다. 동명이인·동명곡을 허용하고 이름만으로 병합하지 않습니다.
8. TIMESTAMPTZ에는 offset이 있는 시각을 입력합니다. 시각 자체와 지역 시간대 이름은 별개이므로 공연의 timezone_name을 함께 둡니다. DATE는 날짜만 의미하며 시간 미정에 자정을 넣지 않습니다.
9. position은 0 이상, ordinal/disc_number/track_number는 1 이상입니다. 같은 position은 허용하고 마지막 정렬 기준으로 id를 사용합니다.
10. 원격 FK의 기본 삭제 정책은 RESTRICT입니다. 관계 표에서 소유 부모가 명시적으로 삭제될 때만 종속 행 CASCADE를 검토합니다. 연결된 다른 아티스트·곡·영상과 원문/영수증은 연쇄 삭제하지 않습니다.
11. URL은 http/https로 검증합니다. 출처 주소는 입력값으로 보존하지만 DB 암호·토큰·접속 문자열을 어떤 예시나 업무 테이블에도 넣지 않습니다.
12. 새 상태 값, archived_at, 영수증의 세부 필드와 모든 로컬 표의 상세 필드는 기존 개요를 구체화한 제안입니다. 추가로 합의됐거나 구현된 사실로 간주하지 않습니다.
13. 이 문서에 열거한 컬럼이 업무 설계 범위입니다. Alembic 등 도구가 생성할 버전 관리 표, PostgreSQL/SQLite 시스템 표와 인덱스 내부 구조는 제외합니다. 검색 키/집계 캐시는 계측 후 별도로 결정하며 숨겨진 필수 컬럼이 있다고 가정하지 않습니다.

## 전체 목차

| 구분 | 테이블 | 쉬운 설명 |
| --- | --- | --- |
| A | [artists](#artists) | 통합 아티스트 명부 |
| A | [artist_aliases](#artist_aliases) | 아티스트 검색 별칭 |
| A | [agencies](#agencies) | 소속사 |
| A | [artist_group_members](#artist_group_members) | 그룹과 멤버 관계 |
| A | [external_accounts](#external_accounts) | 외부 플랫폼 계정 |
| A | [artist_external_accounts](#artist_external_accounts) | 아티스트와 계정 연결 |
| B | [songs](#songs) | 곡 작품 마스터 |
| B | [song_artists](#song_artists) | 곡의 원곡 아티스트 |
| B | [karaoke_numbers](#karaoke_numbers) | 노래방 수록 번호 |
| C | [videos](#videos) | 공통 영상 정보 |
| C | [live_archives](#live_archives) | 라이브 방송 |
| C | [archive_artists](#archive_artists) | 방송 참여자 |
| C | [source_documents](#source_documents) | 원문·출처 스냅샷 |
| C | [archive_sources](#archive_sources) | 라이브의 근거 문서 연결 |
| C | [performances](#performances) | 세트리스트의 가창 한 건 |
| C | [performance_artists](#performance_artists) | 실제 가창자 연결 |
| D | [concerts](#concerts) | 공연 마스터 |
| D | [concert_artists](#concert_artists) | 공연 출연진 |
| D | [concert_ticket_windows](#concert_ticket_windows) | 티켓 판매 구간 |
| E | [albums](#albums) | 발매 앨범 |
| E | [album_artists](#album_artists) | 앨범 발매 명의 |
| E | [recordings](#recordings) | 녹음·음원 버전 |
| E | [recording_artists](#recording_artists) | 음원 가창자 |
| E | [recording_external_ids](#recording_external_ids) | 음원 외부 ID |
| E | [album_tracks](#album_tracks) | 앨범 내 수록 위치 |
| E | [recording_lyrics](#recording_lyrics) | 버전별 가사 |
| E | [covers](#covers) | 공식 커버 영상 |
| E | [cover_artists](#cover_artists) | 커버 참여자 |
| F | [catalog_instance](#catalog_instance) | 카탈로그 DB 식별 |
| F | [catalog_imports](#catalog_imports) | 원격 반영 영수증 |
| F | [catalog_changes](#catalog_changes) | 카탈로그 변경 이력 |
| G | [import_batches](#import_batches) | 검수 배치 |
| G | [input_files](#input_files) | 입력 파일과 원본 보관 |
| G | [draft_entities](#draft_entities) | 검수 중인 자료 |
| G | [draft_relations](#draft_relations) | 초안 관계 검증용 목록 |
| G | [review_events](#review_events) | 검수 작업 이력 |
| G | [validation_issues](#validation_issues) | 오류·경고 목록 |
| G | [publish_plans](#publish_plans) | 고정된 반영 계획 |
| G | [publish_attempts](#publish_attempts) | 반영 시도·복구 이력 |
| G | [remote_id_map](#remote_id_map) | 로컬 초안과 원격 ID 대응 |

## A. 아티스트·계정

<a id="artists"></a>

### 1. artists — 통합 아티스트 명부

**저장 위치:** 새 Neon PostgreSQL

원곡자·가창자·발매 참여자를 한 명부에 등록합니다. 같은 음악 활동 주체는 역할이 달라도 같은 ID를 사용합니다.

| 필드 | 자료형 | 필수 여부 / 기본값 | 설명·연결 대상 | 예시 |
| --- | --- | --- | --- | --- |
| `id` | INTEGER PK | 필수·자동 증가 | 이 테이블 행의 고유 번호. 새 번호는 DB가 발급하며 기존 DB 번호를 그대로 재사용하지 않음 | 1 |
| `slug` | TEXT | 필수·고유 | 주소에 사용할 고정 식별 문자열. 이름을 바꿔도 자동 변경하지 않음 | hachi |
| `name_native` | TEXT | 필수 | 공식 원어 이름 | HACHI |
| `name_ko` | TEXT | 선택·NULL | 검수한 한국어 이름. 임의 번역 금지 | 하치 |
| `name_latin` | TEXT | 선택·NULL | 공식 영어/로마자 표기. 원어와 같으면 생략 가능 | NULL |
| `entity_kind` | TEXT | 필수 | solo(개인 활동 주체), group(그룹) | solo |
| `is_virtual` | BOOLEAN | 선택·NULL | 가상 캐릭터 활동 여부. NULL은 아직 확인 안 됨 | true |
| `agency_id` | INTEGER FK | 선택·NULL | agencies.id. 소속사가 없거나 미확인일 때 비움 | 3 |
| `birthday_month` | SMALLINT | 선택·NULL | 생일 월. 생년은 저장하지 않음 | 8 |
| `birthday_day` | SMALLINT | 선택·NULL | 생일 일. 월과 함께 입력하거나 함께 비움 | 1 |
| `debut_date` | DATE | 선택·NULL | 정확히 확인된 데뷔 날짜. 연도만 알면 날짜를 만들지 않음 | 2020-08-01 |
| `bio` | TEXT | 선택·NULL | 검수된 프로필 소개 | 아티스트 소개문 |
| `theme_color` | TEXT | 선택·NULL | 캘린더 등에서 쓸 색상. #RRGGBB 형식 | #8B74D6 |
| `avatar_url` | TEXT | 선택·NULL | 프로필 이미지 주소. 없으면 화면의 이름 폴백 | https://example.com/avatar.jpg |
| `show_in_catalog` | BOOLEAN | 필수·기본 false | 사용자 탐색 목록에 노출할지. 수집 여부와 독립 | true |
| `created_at` | TIMESTAMPTZ | 필수·자동 | 새 DB에 이 행이 처음 등록된 시각. 공연/방송/원문 수집 시각과 별개 | 서버 현재 시각 |
| `updated_at` | TIMESTAMPTZ | 필수·자동 | 행이 마지막 변경된 시각. 서비스가 수정 때 갱신 | 서버 현재 시각 |
| `version` | INTEGER | 필수·기본 1 | 덮어쓰기 충돌을 막는 수정 번호. 저장 시 기대값을 대조하고 증가 | 1 → 2 |
| `archived_at` | TIMESTAMPTZ | 선택·기본 NULL | 사용 중지 시각. NULL이면 활성. 물리 삭제 대신 보관하는 제안 필드 | NULL |

**연결·검증 규칙**

- 이름은 UNIQUE가 아닙니다. 동명이인과 동일한 별칭을 허용합니다.
- 생일은 유효한 월/일 조합만 허용합니다. 2월 29일은 허용하지만 평년 일정을 임의 이동하지 않습니다.
- 그룹과 개인은 별도 활동 주체입니다. 같은 사람이 다른 활동 명의를 쓴다는 이유만으로 자동 병합하지 않습니다.

<a id="artist_aliases"></a>

### 2. artist_aliases — 아티스트 검색 별칭

**저장 위치:** 새 Neon PostgreSQL

표시 이름 외 영어 이름·별명·과거 표기로도 검색하기 위한 목록입니다.

| 필드 | 자료형 | 필수 여부 / 기본값 | 설명·연결 대상 | 예시 |
| --- | --- | --- | --- | --- |
| `id` | INTEGER PK | 필수·자동 증가 | 이 테이블 행의 고유 번호. 새 번호는 DB가 발급하며 기존 DB 번호를 그대로 재사용하지 않음 | 1 |
| `artist_id` | INTEGER FK | 필수 | 별칭의 주인. artists.id | 1 |
| `alias` | TEXT | 필수 | 사용자가 검색할 수 있는 별칭 원문 | 검색용 별명 |
| `normalized_alias` | TEXT | 필수·서버 생성 | NFKC·대소문자·공백 정리한 검색 키. 표시 원문을 대체하지 않음 | 정규화된 별명 |
| `created_at` | TIMESTAMPTZ | 필수·자동 | 새 DB에 이 행이 처음 등록된 시각. 공연/방송/원문 수집 시각과 별개 | 서버 현재 시각 |
| `updated_at` | TIMESTAMPTZ | 필수·자동 | 행이 마지막 변경된 시각. 서비스가 수정 때 갱신 | 서버 현재 시각 |

**연결·검증 규칙**

- UNIQUE(artist_id, normalized_alias). 다른 아티스트가 같은 별칭을 쓰는 것은 허용합니다.
- 수정 시 artists.version도 올립니다. 정규화 결과만으로 사람을 합치지 않습니다.

<a id="agencies"></a>

### 3. agencies — 소속사

**저장 위치:** 새 Neon PostgreSQL

같은 소속사를 철자만 다르게 여러 번 적는 것을 줄입니다.

| 필드 | 자료형 | 필수 여부 / 기본값 | 설명·연결 대상 | 예시 |
| --- | --- | --- | --- | --- |
| `id` | INTEGER PK | 필수·자동 증가 | 이 테이블 행의 고유 번호. 새 번호는 DB가 발급하며 기존 DB 번호를 그대로 재사용하지 않음 | 1 |
| `name_native` | TEXT | 필수 | 소속사 원어 이름 | 예시 소속사 |
| `name_ko` | TEXT | 선택·NULL | 한국어 표기 | 예시 소속사 한국어명 |
| `website_url` | TEXT | 선택·NULL | 공식 사이트 | https://example.com |
| `created_at` | TIMESTAMPTZ | 필수·자동 | 새 DB에 이 행이 처음 등록된 시각. 공연/방송/원문 수집 시각과 별개 | 서버 현재 시각 |
| `updated_at` | TIMESTAMPTZ | 필수·자동 | 행이 마지막 변경된 시각. 서비스가 수정 때 갱신 | 서버 현재 시각 |
| `version` | INTEGER | 필수·기본 1 | 덮어쓰기 충돌을 막는 수정 번호. 저장 시 기대값을 대조하고 증가 | 1 → 2 |
| `archived_at` | TIMESTAMPTZ | 선택·기본 NULL | 사용 중지 시각. NULL이면 활성. 물리 삭제 대신 보관하는 제안 필드 | NULL |

**연결·검증 규칙**

- 소속사는 artists와 다른 개념입니다. 소속사 이름만으로 자동 병합하지 않습니다.
- 현재 소속 하나를 연결하는 1차안이며 복수 소속·소속 변동 이력은 후속 확장입니다.

<a id="artist_group_members"></a>

### 4. artist_group_members — 그룹과 멤버 관계

**저장 위치:** 새 Neon PostgreSQL

그룹의 멤버 목록과 확인된 활동 기간을 저장합니다.

| 필드 | 자료형 | 필수 여부 / 기본값 | 설명·연결 대상 | 예시 |
| --- | --- | --- | --- | --- |
| `id` | INTEGER PK | 필수·자동 증가 | 이 테이블 행의 고유 번호. 새 번호는 DB가 발급하며 기존 DB 번호를 그대로 재사용하지 않음 | 1 |
| `group_id` | INTEGER FK | 필수 | 그룹인 artists.id | 10 |
| `member_id` | INTEGER FK | 필수 | 멤버인 artists.id | 1 |
| `joined_on` | DATE | 선택·NULL | 정확히 확인된 가입일 | 2023-04-01 |
| `left_on` | DATE | 선택·NULL | 정확히 확인된 탈퇴일. NULL만으로 현재 재적을 확정하지 않음 | NULL |
| `created_at` | TIMESTAMPTZ | 필수·자동 | 새 DB에 이 행이 처음 등록된 시각. 공연/방송/원문 수집 시각과 별개 | 서버 현재 시각 |
| `updated_at` | TIMESTAMPTZ | 필수·자동 | 행이 마지막 변경된 시각. 서비스가 수정 때 갱신 | 서버 현재 시각 |

**연결·검증 규칙**

- UNIQUE(group_id, member_id), group_id != member_id.
- group은 group, member는 solo인지 서비스에서 검증합니다. 둘 다 알면 left_on >= joined_on.
- 1차는 동일 그룹·멤버 쌍 한 행입니다. 재가입 이력과 날짜 미상 탈퇴 상태는 별도 확장 항목입니다.

<a id="external_accounts"></a>

### 5. external_accounts — 외부 플랫폼 계정

**저장 위치:** 새 Neon PostgreSQL

YouTube·Spotify 계정과 공식 사이트·팬클럽 표시 링크를 통합 관리합니다. 플랫폼 ID가 없는 링크는 URL만 저장합니다.

| 필드 | 자료형 | 필수 여부 / 기본값 | 설명·연결 대상 | 예시 |
| --- | --- | --- | --- | --- |
| `id` | INTEGER PK | 필수·자동 증가 | 이 테이블 행의 고유 번호. 새 번호는 DB가 발급하며 기존 DB 번호를 그대로 재사용하지 않음 | 1 |
| `platform` | TEXT | 필수 | youtube, spotify, x, website, fanclub 등 허용 종류 | youtube |
| `platform_id` | TEXT | 선택·NULL | 플랫폼의 고정 ID. @핸들과 구분 | 외부 채널 ID |
| `handle` | TEXT | 선택·NULL | 변할 수 있는 계정 핸들 | @example |
| `url` | TEXT | 필수 | 외부 계정의 공식 주소 | https://example.com/channel |
| `collection_enabled` | BOOLEAN | 필수·기본 false | 향후 수집 대상으로 사용할지. website/fanclub은 false로 제한; 실제 수집기 연결은 별도 | false |
| `created_at` | TIMESTAMPTZ | 필수·자동 | 새 DB에 이 행이 처음 등록된 시각. 공연/방송/원문 수집 시각과 별개 | 서버 현재 시각 |
| `updated_at` | TIMESTAMPTZ | 필수·자동 | 행이 마지막 변경된 시각. 서비스가 수정 때 갱신 | 서버 현재 시각 |
| `version` | INTEGER | 필수·기본 1 | 덮어쓰기 충돌을 막는 수정 번호. 저장 시 기대값을 대조하고 증가 | 1 → 2 |
| `archived_at` | TIMESTAMPTZ | 선택·기본 NULL | 사용 중지 시각. NULL이면 활성. 물리 삭제 대신 보관하는 제안 필드 | NULL |

**연결·검증 규칙**

- platform_id가 있으면 UNIQUE(platform, platform_id). ID 미상은 URL을 비교해 중복 후보로 안내합니다.
- 키·비밀번호·OAuth 토큰·수집 cursor는 여기에 저장하지 않습니다.

<a id="artist_external_accounts"></a>

### 6. artist_external_accounts — 아티스트와 계정 연결

**저장 위치:** 새 Neon PostgreSQL

한 그룹 채널을 여러 아티스트와 연결하거나 한 아티스트의 여러 계정을 연결합니다.

| 필드 | 자료형 | 필수 여부 / 기본값 | 설명·연결 대상 | 예시 |
| --- | --- | --- | --- | --- |
| `id` | INTEGER PK | 필수·자동 증가 | 이 테이블 행의 고유 번호. 새 번호는 DB가 발급하며 기존 DB 번호를 그대로 재사용하지 않음 | 1 |
| `artist_id` | INTEGER FK | 필수 | artists.id | 1 |
| `account_id` | INTEGER FK | 필수 | external_accounts.id | 20 |
| `relationship` | TEXT | 필수 | owner(명의/주체), member(공유 계정 참여자) | owner |
| `is_primary` | BOOLEAN | 필수·기본 false | 해당 아티스트의 해당 플랫폼 대표 계정 여부 | true |
| `label` | TEXT | 선택·NULL | 해당 아티스트 프로필에서 보일 버튼 이름. 비우면 종류별 기본 이름 | Official |
| `position` | INTEGER | 필수·기본 0 | 해당 아티스트의 프로필 링크 표시 순서 | 0 |
| `created_at` | TIMESTAMPTZ | 필수·자동 | 새 DB에 이 행이 처음 등록된 시각. 공연/방송/원문 수집 시각과 별개 | 서버 현재 시각 |
| `updated_at` | TIMESTAMPTZ | 필수·자동 | 행이 마지막 변경된 시각. 서비스가 수정 때 갱신 | 서버 현재 시각 |

**연결·검증 규칙**

- UNIQUE(artist_id, account_id). 같은 아티스트·플랫폼의 대표 계정은 최대 하나라는 서비스 검증을 둡니다.
- 공유 채널 연결이 곧 모든 영상의 실제 가창자라는 뜻은 아닙니다. 별도 artist_links 없이 이 관계의 label/position으로 프로필 버튼을 만듭니다.

## B. 곡·원곡자·노래방 번호

<a id="songs"></a>

### 7. songs — 곡 작품 마스터

**저장 위치:** 새 Neon PostgreSQL

특정 앨범이나 영상이 아니라 곡 자체를 저장합니다. 라이브·발매·커버의 공통 연결점입니다.

| 필드 | 자료형 | 필수 여부 / 기본값 | 설명·연결 대상 | 예시 |
| --- | --- | --- | --- | --- |
| `id` | INTEGER PK | 필수·자동 증가 | 이 테이블 행의 고유 번호. 새 번호는 DB가 발급하며 기존 DB 번호를 그대로 재사용하지 않음 | 1 |
| `title_native` | TEXT | 필수 | 원어 곡명 | Lemon |
| `title_ko` | TEXT | 선택·NULL | 한국어 표기. 영어 원어를 복사해 채우지 않음 | NULL |
| `title_latin` | TEXT | 선택·NULL | 영어/로마자 표기 | NULL |
| `language_code` | TEXT | 선택·NULL | 가사의 언어 코드. 다국어는 mul 등 계약으로 처리 | ja |
| `created_at` | TIMESTAMPTZ | 필수·자동 | 새 DB에 이 행이 처음 등록된 시각. 공연/방송/원문 수집 시각과 별개 | 서버 현재 시각 |
| `updated_at` | TIMESTAMPTZ | 필수·자동 | 행이 마지막 변경된 시각. 서비스가 수정 때 갱신 | 서버 현재 시각 |
| `version` | INTEGER | 필수·기본 1 | 덮어쓰기 충돌을 막는 수정 번호. 저장 시 기대값을 대조하고 증가 | 1 → 2 |
| `archived_at` | TIMESTAMPTZ | 선택·기본 NULL | 사용 중지 시각. NULL이면 활성. 물리 삭제 대신 보관하는 제안 필드 | NULL |

**연결·검증 규칙**

- 동명곡을 허용합니다. 제목·원곡자 문자열만으로 자동 병합하지 않습니다.
- 원곡자를 모르는 곡도 검수 후 저장할 수 있습니다. 상세 주소는 숫자 ID를 사용합니다. title_latin·language_code·노래방 번호는 유지하고 음악 크레딧은 저장하지 않습니다. Spotify ID는 recordings 쪽에 연결합니다.

<a id="song_artists"></a>

### 8. song_artists — 곡의 원곡 아티스트

**저장 위치:** 새 Neon PostgreSQL

표시·검색·통계에 사용할 원곡 명의를 여러 명 연결합니다. 가창/제작 세부 역할은 구분하지 않습니다.

| 필드 | 자료형 | 필수 여부 / 기본값 | 설명·연결 대상 | 예시 |
| --- | --- | --- | --- | --- |
| `id` | INTEGER PK | 필수·자동 증가 | 이 테이블 행의 고유 번호. 새 번호는 DB가 발급하며 기존 DB 번호를 그대로 재사용하지 않음 | 1 |
| `song_id` | INTEGER FK | 필수 | songs.id | 301 |
| `artist_id` | INTEGER FK | 필수 | artists.id | 2 |
| `position` | INTEGER | 필수·기본 0 | 원곡 명의 표시 순서 | 0 |
| `created_at` | TIMESTAMPTZ | 필수·자동 | 새 DB에 이 행이 처음 등록된 시각. 공연/방송/원문 수집 시각과 별개 | 서버 현재 시각 |
| `updated_at` | TIMESTAMPTZ | 필수·자동 | 행이 마지막 변경된 시각. 서비스가 수정 때 갱신 | 서버 현재 시각 |

**연결·검증 규칙**

- UNIQUE(song_id, artist_id), position >= 0.
- 공식 발표 명의를 검수해 연결합니다. 보컬로이드 P와 가창 캐릭터를 반드시 모두 등록하도록 요구하지 않습니다.

<a id="karaoke_numbers"></a>

### 9. karaoke_numbers — 노래방 수록 번호

**저장 위치:** 새 Neon PostgreSQL

같은 곡의 TJ·KY 번호를 여러 개 저장할 수 있습니다.

| 필드 | 자료형 | 필수 여부 / 기본값 | 설명·연결 대상 | 예시 |
| --- | --- | --- | --- | --- |
| `id` | INTEGER PK | 필수·자동 증가 | 이 테이블 행의 고유 번호. 새 번호는 DB가 발급하며 기존 DB 번호를 그대로 재사용하지 않음 | 1 |
| `song_id` | INTEGER FK | 필수 | songs.id | 301 |
| `provider` | TEXT | 필수 | tj 또는 ky | tj |
| `number` | TEXT | 필수 | 노래방 번호. 계산용 숫자가 아니므로 문자열로 보존 | 012345 |
| `source_url` | TEXT | 선택·NULL | 번호를 확인한 출처 | https://example.com/catalog |
| `created_at` | TIMESTAMPTZ | 필수·자동 | 새 DB에 이 행이 처음 등록된 시각. 공연/방송/원문 수집 시각과 별개 | 서버 현재 시각 |
| `updated_at` | TIMESTAMPTZ | 필수·자동 | 행이 마지막 변경된 시각. 서비스가 수정 때 갱신 | 서버 현재 시각 |

**연결·검증 규칙**

- UNIQUE(song_id, provider, number). 동일 provider+number가 다른 곡에 연결되면 충돌 후보를 검수합니다.
- 자동 매칭 결과를 검수 없이 확정 번호로 넣지 않습니다.

## C. 영상·라이브·세트리스트

<a id="videos"></a>

### 10. videos — 공통 영상 정보

**저장 위치:** 새 Neon PostgreSQL

같은 YouTube 영상을 라이브와 커버에서 각각 복제하지 않도록 영상 자체를 한 번 저장합니다.

| 필드 | 자료형 | 필수 여부 / 기본값 | 설명·연결 대상 | 예시 |
| --- | --- | --- | --- | --- |
| `id` | INTEGER PK | 필수·자동 증가 | 이 테이블 행의 고유 번호. 새 번호는 DB가 발급하며 기존 DB 번호를 그대로 재사용하지 않음 | 1 |
| `platform` | TEXT | 필수 | 1차 허용 플랫폼 youtube. 추후 확장은 계약 변경 | youtube |
| `platform_video_id` | TEXT | 필수 | 플랫폼의 영상 고유 ID | 검수된 11자리 YouTube ID |
| `source_account_id` | INTEGER FK | 선택·NULL | 업로드 계정. external_accounts.id | 20 |
| `title` | TEXT | 필수 | 확인한 영상 제목 | 라이브 아카이브 제목 |
| `published_at` | TIMESTAMPTZ | 선택·NULL | 영상 공개/업로드 시각. 실제 방송 시각과 다를 수 있음 | 2026-09-20T10:00:00Z |
| `duration_seconds` | INTEGER | 선택·NULL | 영상 전체 길이(초). 모르면 0 대신 NULL | 7200 |
| `availability` | TEXT | 필수·기본 unknown | public, unlisted, private, deleted, unknown 제안값 | public |
| `created_at` | TIMESTAMPTZ | 필수·자동 | 새 DB에 이 행이 처음 등록된 시각. 공연/방송/원문 수집 시각과 별개 | 서버 현재 시각 |
| `updated_at` | TIMESTAMPTZ | 필수·자동 | 행이 마지막 변경된 시각. 서비스가 수정 때 갱신 | 서버 현재 시각 |
| `version` | INTEGER | 필수·기본 1 | 덮어쓰기 충돌을 막는 수정 번호. 저장 시 기대값을 대조하고 증가 | 1 → 2 |
| `archived_at` | TIMESTAMPTZ | 선택·기본 NULL | 사용 중지 시각. NULL이면 활성. 물리 삭제 대신 보관하는 제안 필드 | NULL |

**연결·검증 규칙**

- UNIQUE(platform, platform_video_id). YouTube ID는 11자리 허용 문자로 검증하고 URL은 ID에서 만듭니다.
- duration_seconds >= 0. 제목·썸네일 URL만으로 영상 동일성을 판단하지 않습니다.

<a id="live_archives"></a>

### 11. live_archives — 라이브 방송

**저장 위치:** 새 Neon PostgreSQL

영상 한 개를 라이브 아카이브로 분류하고 방송 일시·세트리스트 준비 상태를 저장합니다.

| 필드 | 자료형 | 필수 여부 / 기본값 | 설명·연결 대상 | 예시 |
| --- | --- | --- | --- | --- |
| `id` | INTEGER PK | 필수·자동 증가 | 이 테이블 행의 고유 번호. 새 번호는 DB가 발급하며 기존 DB 번호를 그대로 재사용하지 않음 | 1 |
| `video_id` | INTEGER FK | 필수·고유 | videos.id. 한 영상에 라이브 행 하나 | 100 |
| `primary_artist_id` | INTEGER FK | 선택·NULL | 화면에 대표로 보여줄 artists.id. 단독 가창자를 뜻하지 않음 | 1 |
| `broadcast_at` | TIMESTAMPTZ | 선택·NULL | 확인된 실제 방송 시각. 업로드 시각 자동 복사 금지 | 2026-09-20T18:00:00+09:00 |
| `setlist_state` | TEXT | 필수·기본 unprocessed | unprocessed(미정리), partial(일부), complete(완료), unavailable(확보 불가) | partial |
| `created_at` | TIMESTAMPTZ | 필수·자동 | 새 DB에 이 행이 처음 등록된 시각. 공연/방송/원문 수집 시각과 별개 | 서버 현재 시각 |
| `updated_at` | TIMESTAMPTZ | 필수·자동 | 행이 마지막 변경된 시각. 서비스가 수정 때 갱신 | 서버 현재 시각 |
| `version` | INTEGER | 필수·기본 1 | 덮어쓰기 충돌을 막는 수정 번호. 저장 시 기대값을 대조하고 증가 | 1 → 2 |
| `archived_at` | TIMESTAMPTZ | 선택·기본 NULL | 사용 중지 시각. NULL이면 활성. 물리 삭제 대신 보관하는 제안 필드 | NULL |

**연결·검증 규칙**

- 대표 아티스트와 확인된 가창자는 archive_artists에도 연결합니다. 방송 참여자 수에 인원 제한을 두지 않습니다.
- 공개 여부는 videos.availability, 세트리스트 준비 상태는 setlist_state입니다. 승인 여부와 혼용하지 않습니다.
- 방송 날짜만 아는 경우 broadcast_at에 자정을 임의 입력하지 않습니다. 원문에 남기고 날짜 정밀도 확장은 별도 결정합니다.

<a id="archive_artists"></a>

### 12. archive_artists — 방송 참여자

**저장 위치:** 새 Neon PostgreSQL

누가 방송을 진행하거나 게스트로 출연했는지 저장합니다.

| 필드 | 자료형 | 필수 여부 / 기본값 | 설명·연결 대상 | 예시 |
| --- | --- | --- | --- | --- |
| `id` | INTEGER PK | 필수·자동 증가 | 이 테이블 행의 고유 번호. 새 번호는 DB가 발급하며 기존 DB 번호를 그대로 재사용하지 않음 | 1 |
| `archive_id` | INTEGER FK | 필수 | live_archives.id | 200 |
| `artist_id` | INTEGER FK | 필수 | artists.id | 1 |
| `role` | TEXT | 필수 | host(진행), guest(게스트). 불명확하면 관계 승인을 보류 | host |
| `position` | INTEGER | 필수·기본 0 | 출연진 표시 순서 | 0 |
| `created_at` | TIMESTAMPTZ | 필수·자동 | 새 DB에 이 행이 처음 등록된 시각. 공연/방송/원문 수집 시각과 별개 | 서버 현재 시각 |
| `updated_at` | TIMESTAMPTZ | 필수·자동 | 행이 마지막 변경된 시각. 서비스가 수정 때 갱신 | 서버 현재 시각 |

**연결·검증 규칙**

- UNIQUE(archive_id, artist_id). 하나의 방송에서 같은 사람을 여러 번 세지 않습니다.
- 이 명단에 있어도 모든 세트리스트 곡을 불렀다는 뜻은 아닙니다.

<a id="source_documents"></a>

### 13. source_documents — 원문·출처 스냅샷

**저장 위치:** 새 Neon PostgreSQL

댓글·영상 설명·공식 공지 등 판단 근거를 수정하지 않는 사본으로 보존합니다.

| 필드 | 자료형 | 필수 여부 / 기본값 | 설명·연결 대상 | 예시 |
| --- | --- | --- | --- | --- |
| `id` | INTEGER PK | 필수·자동 증가 | 이 테이블 행의 고유 번호. 새 번호는 DB가 발급하며 기존 DB 번호를 그대로 재사용하지 않음 | 1 |
| `source_kind` | TEXT | 필수 | youtube_comment, video_description, announcement, official_page, manual_note 제안값 | youtube_comment |
| `source_url` | TEXT | 선택·NULL | 원문 주소. 외부 원문이 없으면 비움 | https://example.com/source |
| `external_id` | TEXT | 선택·NULL | 댓글/게시글 등 외부 식별자. 수정본도 같은 ID일 수 있음 | 외부 댓글 ID |
| `captured_at` | TIMESTAMPTZ | 선택·NULL | 실제로 원문을 확보한 시각. 모르면 현재 시각으로 꾸미지 않음 | 2026-09-19T02:00:00Z |
| `content_text` | TEXT | 선택·NULL | 댓글·설명·공지 원문 | 15:30 곡명 / 원곡자 |
| `content_hash` | TEXT | 필수·서버 생성 | 본문과 메타데이터를 정해진 방식으로 정규화한 SHA-256 | 64자리 해시 |
| `source_metadata` | JSONB | 필수·기본 {} | 승인에 필요한 원본 메타데이터·추출 출처. 비밀·계정 토큰 제외 | 영상 ID 및 확인한 공식 출처 |
| `created_at` | TIMESTAMPTZ | 필수·자동 | 새 DB에 이 행이 처음 등록된 시각. 공연/방송/원문 수집 시각과 별개 | 서버 현재 시각 |

**연결·검증 규칙**

- 외부 ID만으로 UNIQUE를 걸지 않습니다. 같은 댓글의 편집 전후를 별도 스냅샷으로 보존할 수 있습니다.
- 본문 또는 의미 있는 메타데이터 중 하나는 있어야 합니다. 해시만 같다고 서로 다른 출처를 자동 병합하지 않습니다.
- 불변 자료입니다. 정정 시 새 스냅샷을 추가하고 관계를 변경합니다.

<a id="archive_sources"></a>

### 14. archive_sources — 라이브의 근거 문서 연결

**저장 위치:** 새 Neon PostgreSQL

한 방송에 여러 세트리스트 댓글과 메타데이터 출처를 연결합니다.

| 필드 | 자료형 | 필수 여부 / 기본값 | 설명·연결 대상 | 예시 |
| --- | --- | --- | --- | --- |
| `id` | INTEGER PK | 필수·자동 증가 | 이 테이블 행의 고유 번호. 새 번호는 DB가 발급하며 기존 DB 번호를 그대로 재사용하지 않음 | 1 |
| `archive_id` | INTEGER FK | 필수 | live_archives.id | 200 |
| `document_id` | INTEGER FK | 필수 | source_documents.id | 300 |
| `role` | TEXT | 필수 | setlist_evidence(세트리스트 근거), metadata_evidence(방송 정보 근거) | setlist_evidence |
| `created_at` | TIMESTAMPTZ | 필수·자동 | 새 DB에 이 행이 처음 등록된 시각. 공연/방송/원문 수집 시각과 별개 | 서버 현재 시각 |
| `updated_at` | TIMESTAMPTZ | 필수·자동 | 행이 마지막 변경된 시각. 서비스가 수정 때 갱신 | 서버 현재 시각 |

**연결·검증 규칙**

- UNIQUE(archive_id, document_id, role). 새 댓글을 연결해도 기존 원문을 덮어쓰지 않습니다.

<a id="performances"></a>

### 15. performances — 세트리스트의 가창 한 건

**저장 위치:** 새 Neon PostgreSQL

방송 안에서 어떤 곡을 언제 불렀는지 저장합니다. 같은 곡을 두 번 불렀다면 두 행입니다.

| 필드 | 자료형 | 필수 여부 / 기본값 | 설명·연결 대상 | 예시 |
| --- | --- | --- | --- | --- |
| `id` | INTEGER PK | 필수·자동 증가 | 이 테이블 행의 고유 번호. 새 번호는 DB가 발급하며 기존 DB 번호를 그대로 재사용하지 않음 | 1 |
| `archive_id` | INTEGER FK | 필수 | live_archives.id | 200 |
| `ordinal` | INTEGER | 필수 | 방송 안 세트리스트 순번. 1부터 시작 | 3 |
| `song_id` | INTEGER FK | 선택·NULL | songs.id. 검수된 미매칭 상태는 허용 | 301 |
| `start_seconds` | INTEGER | 필수 | 영상 시작부터 노래 시작까지 초. 근거 없는 0 입력 금지 | 930 |
| `end_seconds` | INTEGER | 선택·NULL | 노래 종료 시점(초) | 1170 |
| `raw_title` | TEXT | 필수 | 입력 원문에서의 곡명. 정규 곡명으로 덮어쓰지 않음 | 수집 당시 곡명 |
| `raw_artist` | TEXT | 선택·NULL | 원문의 원곡 아티스트 표기 | 수집 당시 원곡자 |
| `raw_timestamp` | TEXT | 선택·NULL | 원문 시각 문자열. 수동 등록이면 생략 가능 | 15:30 |
| `source_document_id` | INTEGER FK | 선택·NULL | 이 행의 근거. source_documents.id | 300 |
| `created_at` | TIMESTAMPTZ | 필수·자동 | 새 DB에 이 행이 처음 등록된 시각. 공연/방송/원문 수집 시각과 별개 | 서버 현재 시각 |
| `updated_at` | TIMESTAMPTZ | 필수·자동 | 행이 마지막 변경된 시각. 서비스가 수정 때 갱신 | 서버 현재 시각 |
| `version` | INTEGER | 필수·기본 1 | 덮어쓰기 충돌을 막는 수정 번호. 저장 시 기대값을 대조하고 증가 | 1 → 2 |
| `archived_at` | TIMESTAMPTZ | 선택·기본 NULL | 사용 중지 시각. NULL이면 활성. 물리 삭제 대신 보관하는 제안 필드 | NULL |

**연결·검증 규칙**

- UNIQUE(archive_id, ordinal). start_seconds >= 0, end_seconds > start_seconds.
- 영상 길이가 알려졌다면 시작/끝이 그 범위인지 서비스에서 검증합니다. 같은 시작 시각은 일괄 중복 금지 대신 경고합니다.
- 시점 자체를 모르는 자료는 현재안에서 승인 가창 행으로 만들지 않고 로컬 보류합니다.
- source_document_id가 있으면 해당 방송의 archive_sources에도 연결합니다. 순번 변경과 가창자 변경은 방송/가창 version에 반영합니다.

<a id="performance_artists"></a>

### 16. performance_artists — 실제 가창자 연결

**저장 위치:** 새 Neon PostgreSQL

듀엣·합창을 인원 제한 없이 표현합니다.

| 필드 | 자료형 | 필수 여부 / 기본값 | 설명·연결 대상 | 예시 |
| --- | --- | --- | --- | --- |
| `id` | INTEGER PK | 필수·자동 증가 | 이 테이블 행의 고유 번호. 새 번호는 DB가 발급하며 기존 DB 번호를 그대로 재사용하지 않음 | 1 |
| `performance_id` | INTEGER FK | 필수 | performances.id | 400 |
| `artist_id` | INTEGER FK | 필수 | artists.id | 1 |
| `role` | TEXT | 필수 | lead(주 가창), guest(함께 부른 게스트) | lead |
| `position` | INTEGER | 필수·기본 0 | 가창자 표시 순서 | 0 |
| `created_at` | TIMESTAMPTZ | 필수·자동 | 새 DB에 이 행이 처음 등록된 시각. 공연/방송/원문 수집 시각과 별개 | 서버 현재 시각 |
| `updated_at` | TIMESTAMPTZ | 필수·자동 | 행이 마지막 변경된 시각. 서비스가 수정 때 갱신 | 서버 현재 시각 |

**연결·검증 규칙**

- UNIQUE(performance_id, artist_id). 동일인은 해당 가창에서 한 번만 계산합니다.
- 실제 가창자를 모르면 관계를 비워 검수된 미상으로 둘 수 있습니다. 채널 주인으로 자동 채우지 않습니다.

## D. 공연·티켓

<a id="concerts"></a>

### 17. concerts — 공연 마스터

**저장 위치:** 새 Neon PostgreSQL

날짜 정확도·시간대·장소·상태를 표현하여 공연 캘린더와 상세 팝업에 사용합니다.

| 필드 | 자료형 | 필수 여부 / 기본값 | 설명·연결 대상 | 예시 |
| --- | --- | --- | --- | --- |
| `id` | INTEGER PK | 필수·자동 증가 | 이 테이블 행의 고유 번호. 새 번호는 DB가 발급하며 기존 DB 번호를 그대로 재사용하지 않음 | 1 |
| `title` | TEXT | 필수 | 공연 공식 타이틀 | 예시 ONE-MAN LIVE |
| `event_format` | TEXT | 필수 | onsite(현장), online(온라인), hybrid(병행) | onsite |
| `event_date` | DATE | 선택·NULL | 공연 기준 시간대의 현지 날짜. 날짜 미정이면 비움 | 2026-09-20 |
| `starts_at` | TIMESTAMPTZ | 선택·NULL | 확인된 실제 시작 시각. 시간 미정이면 00:00 대신 NULL | 2026-09-20T18:00:00+09:00 |
| `ends_at` | TIMESTAMPTZ | 선택·NULL | 확인된 종료 시각 | NULL |
| `timezone_name` | TEXT | 선택·NULL | IANA 시간대 이름. 정확한 시작 시각이 있으면 필수 | Asia/Tokyo |
| `time_precision` | TEXT | 필수·기본 unknown | unknown(날짜 미정), date(날짜만), datetime(시각까지) | date |
| `city` | TEXT | 선택·NULL | 개최 도시. 온라인이거나 미확인이면 비움 | 도쿄 |
| `venue` | TEXT | 선택·NULL | 공연장 이름. 미확인 장소를 만들어 넣지 않음 | 예시 홀 |
| `status` | TEXT | 필수 | scheduled, postponed, cancelled, completed 중 검수한 상태 | scheduled |
| `source_document_id` | INTEGER FK | 선택·NULL | 기준 공지의 source_documents.id | 310 |
| `created_at` | TIMESTAMPTZ | 필수·자동 | 새 DB에 이 행이 처음 등록된 시각. 공연/방송/원문 수집 시각과 별개 | 서버 현재 시각 |
| `updated_at` | TIMESTAMPTZ | 필수·자동 | 행이 마지막 변경된 시각. 서비스가 수정 때 갱신 | 서버 현재 시각 |
| `version` | INTEGER | 필수·기본 1 | 덮어쓰기 충돌을 막는 수정 번호. 저장 시 기대값을 대조하고 증가 | 1 → 2 |
| `archived_at` | TIMESTAMPTZ | 선택·기본 NULL | 사용 중지 시각. NULL이면 활성. 물리 삭제 대신 보관하는 제안 필드 | NULL |

**연결·검증 규칙**

- unknown이면 event_date/starts_at/ends_at NULL. date이면 event_date 필수, starts_at/ends_at NULL. datetime이면 event_date/starts_at/timezone_name 필수.
- datetime의 event_date는 starts_at을 timezone_name으로 변환한 날짜와 같아야 합니다. ends_at이 있으면 starts_at보다 뒤여야 합니다.
- 날짜만 아는 일정을 UTC 자정으로 변환하지 않습니다. 정확한 시각의 캘린더 표시 시간대는 API 계약에서 명시합니다.
- 온라인/현장 여부가 불명확하면 현장으로 추정하지 않고 로컬에서 보류합니다. 장소 미상은 저장 가능하지만 검수 경고를 표시합니다.

<a id="concert_artists"></a>

### 18. concert_artists — 공연 출연진

**저장 위치:** 새 Neon PostgreSQL

공동 공연의 출연자를 여러 명 연결합니다. 주최 업체와 출연자는 구분합니다.

| 필드 | 자료형 | 필수 여부 / 기본값 | 설명·연결 대상 | 예시 |
| --- | --- | --- | --- | --- |
| `id` | INTEGER PK | 필수·자동 증가 | 이 테이블 행의 고유 번호. 새 번호는 DB가 발급하며 기존 DB 번호를 그대로 재사용하지 않음 | 1 |
| `concert_id` | INTEGER FK | 필수 | concerts.id | 500 |
| `artist_id` | INTEGER FK | 필수 | artists.id | 1 |
| `position` | INTEGER | 필수·기본 0 | 출연진 표시 순서. 첫 출연자를 대표 이름·색상으로 사용 | 0 |
| `created_at` | TIMESTAMPTZ | 필수·자동 | 새 DB에 이 행이 처음 등록된 시각. 공연/방송/원문 수집 시각과 별개 | 서버 현재 시각 |
| `updated_at` | TIMESTAMPTZ | 필수·자동 | 행이 마지막 변경된 시각. 서비스가 수정 때 갱신 | 서버 현재 시각 |

**연결·검증 규칙**

- UNIQUE(concert_id, artist_id). 즐겨찾기 아티스트가 여러 명 출연해도 공연 한 건으로 표시합니다.
- 주최자·기획사는 출연자로 등록하지 않습니다. 대표 아티스트는 position, id 순서의 첫 항목이며 출연자가 없으면 중립 표시를 사용합니다.

<a id="concert_ticket_windows"></a>

### 19. concert_ticket_windows — 티켓 판매 구간

**저장 위치:** 새 Neon PostgreSQL

선행·일반·온라인 관람권 등 여러 판매 기간과 링크를 저장합니다.

| 필드 | 자료형 | 필수 여부 / 기본값 | 설명·연결 대상 | 예시 |
| --- | --- | --- | --- | --- |
| `id` | INTEGER PK | 필수·자동 증가 | 이 테이블 행의 고유 번호. 새 번호는 DB가 발급하며 기존 DB 번호를 그대로 재사용하지 않음 | 1 |
| `concert_id` | INTEGER FK | 필수 | concerts.id | 500 |
| `label` | TEXT | 선택·NULL | 판매 구간 이름 | 일반 예매 |
| `opens_at` | TIMESTAMPTZ | 선택·NULL | 정확한 예매 시작 시각 | 2026-08-01T12:00:00+09:00 |
| `closes_at` | TIMESTAMPTZ | 선택·NULL | 정확한 예매 종료 시각 | 2026-09-19T23:59:00+09:00 |
| `url` | TEXT | 선택·NULL | 공식 예매/안내 주소 | https://example.com/tickets |
| `price_text` | TEXT | 선택·NULL | 통화·좌석별 조건을 포함한 안내 문구 | 지정석 9,800엔 |
| `created_at` | TIMESTAMPTZ | 필수·자동 | 새 DB에 이 행이 처음 등록된 시각. 공연/방송/원문 수집 시각과 별개 | 서버 현재 시각 |
| `updated_at` | TIMESTAMPTZ | 필수·자동 | 행이 마지막 변경된 시각. 서비스가 수정 때 갱신 | 서버 현재 시각 |

**연결·검증 규칙**

- 둘 다 있으면 closes_at >= opens_at. 날짜만 아는 판매 시각을 임의 자정으로 채우지 않습니다.
- 동일 공연의 여러 판매 구간을 허용합니다. 전부 빈 내용의 행은 생성하지 않습니다.
- 별도 판매 시간대 이름·날짜 정밀도는 1차 필드에 없으며 필요 시 확장합니다. 정확한 시각은 offset 포함으로 입력하고 원문을 보존합니다.

## E. 앨범·녹음·가사·커버

<a id="albums"></a>

### 20. albums — 발매 앨범

**저장 위치:** 새 Neon PostgreSQL

싱글·EP·정규 앨범의 발매 정보를 저장합니다. 공동 발매 명의는 별도 연결합니다.

| 필드 | 자료형 | 필수 여부 / 기본값 | 설명·연결 대상 | 예시 |
| --- | --- | --- | --- | --- |
| `id` | INTEGER PK | 필수·자동 증가 | 이 테이블 행의 고유 번호. 새 번호는 DB가 발급하며 기존 DB 번호를 그대로 재사용하지 않음 | 1 |
| `title_native` | TEXT | 필수 | 원어 앨범명 | 예시 앨범 |
| `title_ko` | TEXT | 선택·NULL | 한국어 앨범명 | NULL |
| `album_type` | TEXT | 필수 | single, ep, album, compilation, other 제안값. 외부 플랫폼 값을 검수하여 분류 | album |
| `release_year` | SMALLINT | 선택·NULL | 확인한 발매 연도 | 2026 |
| `release_month` | SMALLINT | 선택·NULL | 확인한 발매 월. 월이 있으면 연도도 필수 | 9 |
| `release_day` | SMALLINT | 선택·NULL | 확인한 발매 일. 일이 있으면 연/월도 필수 | 20 |
| `cover_image_url` | TEXT | 선택·NULL | 앨범 자켓 이미지 주소 | https://example.com/album.jpg |
| `spotify_album_id` | TEXT | 선택·NULL·값 있으면 고유 | Spotify 앨범 식별자 | 검수한 외부 앨범 ID |
| `created_at` | TIMESTAMPTZ | 필수·자동 | 새 DB에 이 행이 처음 등록된 시각. 공연/방송/원문 수집 시각과 별개 | 서버 현재 시각 |
| `updated_at` | TIMESTAMPTZ | 필수·자동 | 행이 마지막 변경된 시각. 서비스가 수정 때 갱신 | 서버 현재 시각 |
| `version` | INTEGER | 필수·기본 1 | 덮어쓰기 충돌을 막는 수정 번호. 저장 시 기대값을 대조하고 증가 | 1 → 2 |
| `archived_at` | TIMESTAMPTZ | 선택·기본 NULL | 사용 중지 시각. NULL이면 활성. 물리 삭제 대신 보관하는 제안 필드 | NULL |

**연결·검증 규칙**

- 월/일을 모르는데 1월 1일을 넣지 않습니다. 연도 1~9999, 월 1~12, 실제 달력에 존재하는 날짜를 검증합니다.
- 정확한 날짜가 있어도 발매일은 DATE 의미이며 타임존 시각으로 만들지 않습니다.

<a id="album_artists"></a>

### 21. album_artists — 앨범 발매 명의

**저장 위치:** 새 Neon PostgreSQL

공동 앨범과 여러 아티스트가 참여한 발매를 표현합니다.

| 필드 | 자료형 | 필수 여부 / 기본값 | 설명·연결 대상 | 예시 |
| --- | --- | --- | --- | --- |
| `id` | INTEGER PK | 필수·자동 증가 | 이 테이블 행의 고유 번호. 새 번호는 DB가 발급하며 기존 DB 번호를 그대로 재사용하지 않음 | 1 |
| `album_id` | INTEGER FK | 필수 | albums.id | 600 |
| `artist_id` | INTEGER FK | 필수 | artists.id | 1 |
| `position` | INTEGER | 필수·기본 0 | 공식 발매 명의 표시 순서 | 0 |
| `created_at` | TIMESTAMPTZ | 필수·자동 | 새 DB에 이 행이 처음 등록된 시각. 공연/방송/원문 수집 시각과 별개 | 서버 현재 시각 |
| `updated_at` | TIMESTAMPTZ | 필수·자동 | 행이 마지막 변경된 시각. 서비스가 수정 때 갱신 | 서버 현재 시각 |

**연결·검증 규칙**

- UNIQUE(album_id, artist_id). 실제 각 트랙 가창자는 recording_artists에 따로 저장합니다.

<a id="recordings"></a>

### 22. recordings — 녹음·음원 버전

**저장 위치:** 새 Neon PostgreSQL

같은 작품의 스튜디오 녹음·라이브 녹음 등 실제 음원 버전을 구분합니다.

| 필드 | 자료형 | 필수 여부 / 기본값 | 설명·연결 대상 | 예시 |
| --- | --- | --- | --- | --- |
| `id` | INTEGER PK | 필수·자동 증가 | 이 테이블 행의 고유 번호. 새 번호는 DB가 발급하며 기존 DB 번호를 그대로 재사용하지 않음 | 1 |
| `song_id` | INTEGER FK | 선택·NULL | 공통 작품 songs.id. 미확정이면 비움 | 301 |
| `title_native` | TEXT | 필수 | 발매 음원 원어 제목. 작품 제목과 버전 표기가 다를 수 있음 | 예시 곡 (Live) |
| `title_ko` | TEXT | 선택·NULL | 검수한 한국어 음원 제목 | NULL |
| `version_label` | TEXT | 선택·NULL | 버전 설명. 없다고 원본 버전으로 단정하지 않음 | Live version |
| `duration_ms` | INTEGER | 선택·NULL | 재생 길이(밀리초) | 215000 |
| `official_video_id` | INTEGER FK | 선택·NULL | 대표 공식 MV의 videos.id | 101 |
| `created_at` | TIMESTAMPTZ | 필수·자동 | 새 DB에 이 행이 처음 등록된 시각. 공연/방송/원문 수집 시각과 별개 | 서버 현재 시각 |
| `updated_at` | TIMESTAMPTZ | 필수·자동 | 행이 마지막 변경된 시각. 서비스가 수정 때 갱신 | 서버 현재 시각 |
| `version` | INTEGER | 필수·기본 1 | 덮어쓰기 충돌을 막는 수정 번호. 저장 시 기대값을 대조하고 증가 | 1 → 2 |
| `archived_at` | TIMESTAMPTZ | 선택·기본 NULL | 사용 중지 시각. NULL이면 활성. 물리 삭제 대신 보관하는 제안 필드 | NULL |

**연결·검증 규칙**

- duration_ms >= 0. 단일 대표 MV를 연결하는 1차안입니다.
- 동일 녹음임을 검수했다면 여러 앨범에 공유할 수 있습니다. 재녹음·리마스터 등은 별도 버전 여부를 검수합니다.

<a id="recording_artists"></a>

### 23. recording_artists — 음원 가창자

**저장 위치:** 새 Neon PostgreSQL

앨범 전체 명의와 구별하여 실제 음원의 참여 가수를 연결합니다.

| 필드 | 자료형 | 필수 여부 / 기본값 | 설명·연결 대상 | 예시 |
| --- | --- | --- | --- | --- |
| `id` | INTEGER PK | 필수·자동 증가 | 이 테이블 행의 고유 번호. 새 번호는 DB가 발급하며 기존 DB 번호를 그대로 재사용하지 않음 | 1 |
| `recording_id` | INTEGER FK | 필수 | recordings.id | 700 |
| `artist_id` | INTEGER FK | 필수 | artists.id | 1 |
| `role` | TEXT | 필수 | primary(주 가창), featured(피처링) | primary |
| `position` | INTEGER | 필수·기본 0 | 가창 명의 표시 순서 | 0 |
| `created_at` | TIMESTAMPTZ | 필수·자동 | 새 DB에 이 행이 처음 등록된 시각. 공연/방송/원문 수집 시각과 별개 | 서버 현재 시각 |
| `updated_at` | TIMESTAMPTZ | 필수·자동 | 행이 마지막 변경된 시각. 서비스가 수정 때 갱신 | 서버 현재 시각 |

**연결·검증 규칙**

- UNIQUE(recording_id, artist_id). 그룹 음원이라고 모든 멤버를 자동 추가하지 않습니다.

<a id="recording_external_ids"></a>

### 24. recording_external_ids — 음원 외부 ID

**저장 위치:** 새 Neon PostgreSQL

같은 녹음의 플랫폼 식별자를 저장합니다. 작품 ID와 구분합니다.

| 필드 | 자료형 | 필수 여부 / 기본값 | 설명·연결 대상 | 예시 |
| --- | --- | --- | --- | --- |
| `id` | INTEGER PK | 필수·자동 증가 | 이 테이블 행의 고유 번호. 새 번호는 DB가 발급하며 기존 DB 번호를 그대로 재사용하지 않음 | 1 |
| `recording_id` | INTEGER FK | 필수 | recordings.id | 700 |
| `platform` | TEXT | 필수 | 1차 spotify. 추가 플랫폼은 허용 목록 확장 | spotify |
| `external_id` | TEXT | 필수 | 플랫폼의 트랙 고유 ID | 검수한 Spotify 트랙 ID |
| `created_at` | TIMESTAMPTZ | 필수·자동 | 새 DB에 이 행이 처음 등록된 시각. 공연/방송/원문 수집 시각과 별개 | 서버 현재 시각 |
| `updated_at` | TIMESTAMPTZ | 필수·자동 | 행이 마지막 변경된 시각. 서비스가 수정 때 갱신 | 서버 현재 시각 |

**연결·검증 규칙**

- UNIQUE(platform, external_id). 같은 플랫폼의 서로 다른 ID도 확인 후 하나의 녹음에 여러 개 연결할 수 있습니다.
- 같은 제목·재생 길이만으로 서로 다른 외부 ID의 녹음을 자동 병합하지 않습니다.

<a id="album_tracks"></a>

### 25. album_tracks — 앨범 내 수록 위치

**저장 위치:** 새 Neon PostgreSQL

어느 앨범의 몇 번째 디스크·트랙에 어떤 녹음이 실렸는지 저장합니다.

| 필드 | 자료형 | 필수 여부 / 기본값 | 설명·연결 대상 | 예시 |
| --- | --- | --- | --- | --- |
| `id` | INTEGER PK | 필수·자동 증가 | 이 테이블 행의 고유 번호. 새 번호는 DB가 발급하며 기존 DB 번호를 그대로 재사용하지 않음 | 1 |
| `album_id` | INTEGER FK | 필수 | albums.id | 600 |
| `recording_id` | INTEGER FK | 필수 | recordings.id | 700 |
| `disc_number` | INTEGER | 필수·기본 1 | 디스크 번호 | 1 |
| `track_number` | INTEGER | 필수 | 디스크 안의 트랙 번호 | 3 |
| `created_at` | TIMESTAMPTZ | 필수·자동 | 새 DB에 이 행이 처음 등록된 시각. 공연/방송/원문 수집 시각과 별개 | 서버 현재 시각 |
| `updated_at` | TIMESTAMPTZ | 필수·자동 | 행이 마지막 변경된 시각. 서비스가 수정 때 갱신 | 서버 현재 시각 |

**연결·검증 규칙**

- UNIQUE(album_id, disc_number, track_number). 디스크/트랙 번호는 1 이상입니다.
- 같은 녹음이 다른 앨범에 수록돼도 가사를 복제하지 않습니다. 트랙 제목은 연결된 녹음에서 읽습니다.

<a id="recording_lyrics"></a>

### 26. recording_lyrics — 버전별 가사

**저장 위치:** 새 Neon PostgreSQL

가사·한국어 번역·독음을 녹음 버전에 연결합니다.

| 필드 | 자료형 | 필수 여부 / 기본값 | 설명·연결 대상 | 예시 |
| --- | --- | --- | --- | --- |
| `id` | INTEGER PK | 필수·자동 증가 | 이 테이블 행의 고유 번호. 새 번호는 DB가 발급하며 기존 DB 번호를 그대로 재사용하지 않음 | 1 |
| `recording_id` | INTEGER FK | 필수·고유 | recordings.id. 녹음당 가사 묶음 최대 하나 | 700 |
| `original_lyrics` | TEXT | 필수 | 검수한 원문 가사. 줄바꿈 보존 | 설명용 가사 자리 |
| `translation_ko` | TEXT | 선택·NULL | 한국어 번역 | NULL |
| `pronunciation_ko` | TEXT | 선택·NULL | 한국어 독음 | NULL |
| `source_document_id` | INTEGER FK | 선택·NULL | 확인 근거 source_documents.id | 320 |
| `created_at` | TIMESTAMPTZ | 필수·자동 | 새 DB에 이 행이 처음 등록된 시각. 공연/방송/원문 수집 시각과 별개 | 서버 현재 시각 |
| `updated_at` | TIMESTAMPTZ | 필수·자동 | 행이 마지막 변경된 시각. 서비스가 수정 때 갱신 | 서버 현재 시각 |
| `version` | INTEGER | 필수·기본 1 | 덮어쓰기 충돌을 막는 수정 번호. 저장 시 기대값을 대조하고 증가 | 1 → 2 |
| `archived_at` | TIMESTAMPTZ | 선택·기본 NULL | 사용 중지 시각. NULL이면 활성. 물리 삭제 대신 보관하는 제안 필드 | NULL |

**연결·검증 규칙**

- 가사가 없으면 이 테이블의 행을 만들지 않습니다. 음악 크레딧은 수집·저장하지 않습니다.
- 1차는 전체 텍스트입니다. 줄별 동기화·여러 번역본·카라오케 타이밍은 후속 확장입니다.

<a id="covers"></a>

### 27. covers — 공식 커버 영상

**저장 위치:** 새 Neon PostgreSQL

라이브 방송의 가창과 별도로 제작·업로드한 공식 커버 영상을 관리합니다.

| 필드 | 자료형 | 필수 여부 / 기본값 | 설명·연결 대상 | 예시 |
| --- | --- | --- | --- | --- |
| `id` | INTEGER PK | 필수·자동 증가 | 이 테이블 행의 고유 번호. 새 번호는 DB가 발급하며 기존 DB 번호를 그대로 재사용하지 않음 | 1 |
| `video_id` | INTEGER FK | 필수·고유 | videos.id. 영상당 커버 분류 한 건 | 102 |
| `song_id` | INTEGER FK | 선택·NULL | 커버한 작품 songs.id | 302 |
| `created_at` | TIMESTAMPTZ | 필수·자동 | 새 DB에 이 행이 처음 등록된 시각. 공연/방송/원문 수집 시각과 별개 | 서버 현재 시각 |
| `updated_at` | TIMESTAMPTZ | 필수·자동 | 행이 마지막 변경된 시각. 서비스가 수정 때 갱신 | 서버 현재 시각 |
| `version` | INTEGER | 필수·기본 1 | 덮어쓰기 충돌을 막는 수정 번호. 저장 시 기대값을 대조하고 증가 | 1 → 2 |
| `archived_at` | TIMESTAMPTZ | 선택·기본 NULL | 사용 중지 시각. NULL이면 활성. 물리 삭제 대신 보관하는 제안 필드 | NULL |

**연결·검증 규칙**

- 제목·업로드 날짜·영상 ID는 videos에서 읽습니다. 커버 등록은 라이브 가창 횟수를 늘리지 않습니다.
- 메들리는 단일 song_id에 억지로 연결하지 않습니다. cover_songs 확장 여부는 미확정입니다.
- 같은 영상에 라이브·커버 분류가 동시에 붙으면 중복 집계를 피하도록 검수 경고를 표시합니다.

<a id="cover_artists"></a>

### 28. cover_artists — 커버 참여자

**저장 위치:** 새 Neon PostgreSQL

커버의 실제 가창자·콜라보 참여자를 인원 제한 없이 연결합니다.

| 필드 | 자료형 | 필수 여부 / 기본값 | 설명·연결 대상 | 예시 |
| --- | --- | --- | --- | --- |
| `id` | INTEGER PK | 필수·자동 증가 | 이 테이블 행의 고유 번호. 새 번호는 DB가 발급하며 기존 DB 번호를 그대로 재사용하지 않음 | 1 |
| `cover_id` | INTEGER FK | 필수 | covers.id | 800 |
| `artist_id` | INTEGER FK | 필수 | artists.id | 1 |
| `role` | TEXT | 필수 | vocal(가창 명의), featured(피처링) | vocal |
| `position` | INTEGER | 필수·기본 0 | 참여자 표시 순서 | 0 |
| `created_at` | TIMESTAMPTZ | 필수·자동 | 새 DB에 이 행이 처음 등록된 시각. 공연/방송/원문 수집 시각과 별개 | 서버 현재 시각 |
| `updated_at` | TIMESTAMPTZ | 필수·자동 | 행이 마지막 변경된 시각. 서비스가 수정 때 갱신 | 서버 현재 시각 |

**연결·검증 규칙**

- UNIQUE(cover_id, artist_id). 업로더와 가창자가 다를 수 있으므로 계정 소유자를 자동 확정하지 않습니다.

## F. 원격 출처 추적·반영 이력

<a id="catalog_instance"></a>

### 29. catalog_instance — 카탈로그 DB 식별

**저장 위치:** 새 Neon PostgreSQL

어느 DB에 저장하는지 구별합니다. 기존 DB와 새 DB에서 같은 숫자 ID가 다른 사람을 가리키는 문제를 막습니다.

| 필드 | 자료형 | 필수 여부 / 기본값 | 설명·연결 대상 | 예시 |
| --- | --- | --- | --- | --- |
| `id` | UUID PK | 필수·최초 생성 | 이 카탈로그의 고정 UUID. 서버 재시작마다 바꾸지 않음 | 카탈로그 UUID |
| `singleton_key` | SMALLINT | 필수·기본 1·고유 | 한 DB에 한 행만 두기 위한 값. CHECK = 1 | 1 |
| `schema_version` | TEXT | 필수·마이그레이션 관리 | 앱이 기대하는 스키마 계약 버전. 실제 migration revision과 시작 시 대조 | catalog-v2 |
| `initial_import_id` | INTEGER FK | 선택·NULL | 최초 반영이 완료되면 catalog_imports.id. 초기 반영 전에는 NULL | NULL |
| `initialized_at` | TIMESTAMPTZ | 선택·NULL | 최초 데이터 반영 완료 시각. 초기 반영 영수증과 같은 트랜잭션으로 기록 | NULL |
| `created_at` | TIMESTAMPTZ | 필수·자동 | 빈 스키마를 준비하며 카탈로그 식별 행을 만든 시각 | 서버 현재 시각 |
| `updated_at` | TIMESTAMPTZ | 필수·자동 | 버전/초기화 상태를 마지막 변경한 시각 | 서버 현재 시각 |

**연결·검증 규칙**

- singleton_key·initial_import_id·initialized_at은 기존 계획의 ‘초기 구축 완료 상태’를 구체화한 제안 필드입니다.
- 초기화 상태가 NULL이면 초기 승인 절차를 통과한 일괄 반영만 허용합니다. UI 표시를 바꾸는 것만으로 우회할 수 없습니다.
- 원형 FK는 모든 테이블 생성 후 추가했습니다. 기술용 catalog_schema_migrations(version, checksum, applied_at)도 생성했으며 업무 표 수와 별도로 집계합니다.

<a id="catalog_imports"></a>

### 30. catalog_imports — 원격 반영 영수증

**저장 위치:** 새 Neon PostgreSQL

사용자가 승인한 저장 작업이 실제로 완료됐는지 기록합니다. 같은 작업 재시도 시 중복 저장을 막습니다.

| 필드 | 자료형 | 필수 여부 / 기본값 | 설명·연결 대상 | 예시 |
| --- | --- | --- | --- | --- |
| `id` | INTEGER PK | 필수·자동 증가 | 이 테이블 행의 고유 번호. 새 번호는 DB가 발급하며 기존 DB 번호를 그대로 재사용하지 않음 | 1 |
| `operation_id` | UUID | 필수·고유 | 한 논리 저장 작업의 ID. 재시도에도 같은 값 | 작업 UUID |
| `catalog_instance_id` | UUID FK | 필수 | 대상 catalog_instance.id | 카탈로그 UUID |
| `manifest_hash` | TEXT | 필수 | 승인된 반영 내용의 SHA-256. 수동 저장도 같은 규칙 | 64자리 해시 |
| `source_kind` | TEXT | 필수 | initial_import, batch_import, manual, merge, correction 제안값 | initial_import |
| `committed_at` | TIMESTAMPTZ | 필수·서버 생성 | 반영 트랜잭션 안에서 기록하는 영수증 시각. 물리 COMMIT 완료 시각과 완전히 같다는 뜻은 아님 | 서버 현재 시각 |
| `result_mapping` | JSONB | 필수·기본 [] | client_ref/유형별 새 ID와 결과 version 대응 목록 | 반영된 ID 목록 |
| `result_summary` | JSONB | 필수·기본 {} | 생성·수정·제외 등의 수량 요약 | created_count 등 |
| `created_at` | TIMESTAMPTZ | 필수·자동 | 새 DB에 이 행이 처음 등록된 시각. 공연/방송/원문 수집 시각과 별개 | 서버 현재 시각 |

**연결·검증 규칙**

- 음악 데이터 변경과 같은 트랜잭션에서 INSERT합니다. 실패한 작업은 원격 영수증이 남지 않고 로컬 attempts에 기록됩니다.
- 같은 operation_id+hash는 기존 결과 반환, 다른 hash는 충돌입니다. 초기 완료 여부는 영수증이 보이는지로 확인합니다.

<a id="catalog_changes"></a>

### 31. catalog_changes — 카탈로그 변경 이력

**저장 위치:** 새 Neon PostgreSQL

관리자가 언제 어떤 저장 작업으로 무엇을 바꿨는지 추적합니다.

| 필드 | 자료형 | 필수 여부 / 기본값 | 설명·연결 대상 | 예시 |
| --- | --- | --- | --- | --- |
| `id` | INTEGER PK | 필수·자동 증가 | 이 테이블 행의 고유 번호. 새 번호는 DB가 발급하며 기존 DB 번호를 그대로 재사용하지 않음 | 1 |
| `import_id` | INTEGER FK | 필수 | catalog_imports.id. 수동 저장도 영수증에 연결 | 1 |
| `entity_type` | TEXT | 필수 | 변경한 테이블/리소스 유형 | artists |
| `entity_id` | INTEGER | 필수 | 변경 대상 ID. 이력 대상이므로 일반 다형 FK는 아님 | 1 |
| `action` | TEXT | 필수 | create, update, archive, restore, merge, delete 제안값 | update |
| `before_data` | JSONB | 선택·NULL | 변경 전 값. 신규 생성이면 NULL | 이전 프로필 값 |
| `after_data` | JSONB | 선택·NULL | 변경 후 값. 물리 삭제라면 NULL | 변경된 프로필 값 |
| `provenance` | JSONB | 필수·기본 {} | 원본/근거 문서 ID·승인 내용 해시 등 검수 근거. 비밀·로컬 검토 메모 제외 | document_ids 등 |
| `applied_at` | TIMESTAMPTZ | 필수·자동 | 트랜잭션 안에서 변경을 적용한 시각 | 서버 현재 시각 |
| `created_at` | TIMESTAMPTZ | 필수·자동 | 새 DB에 이 행이 처음 등록된 시각. 공연/방송/원문 수집 시각과 별개 | 서버 현재 시각 |

**연결·검증 규칙**

- 변경 이력은 덮어쓰지 않습니다. 되돌리기는 현재 version과 대조한 새로운 변경 작업입니다.
- create/update/archive/restore에 맞는 before/after 값의 존재를 검증합니다. 관계 변경도 소유 엔티티 변경과 함께 기록합니다.

## G. 로컬 관리자 검수 저장소

<a id="import_batches"></a>

### 32. import_batches — 검수 배치

**저장 위치:** 내 PC SQLite

이번에 함께 검수하고 반영할 자료 묶음입니다. 초기 배치와 이후 추가 배치를 구분합니다.

| 필드 | 자료형 | 필수 여부 / 기본값 | 설명·연결 대상 | 예시 |
| --- | --- | --- | --- | --- |
| `id` | TEXT UUID PK | 필수·앱 생성 | 로컬 행의 고유 UUID. 입력 파일이 지정한 승인/이력 ID는 그대로 신뢰하지 않음 | 로컬 UUID |
| `name` | TEXT | 필수 | 사람이 알아보기 쉬운 배치 이름 | 초기 아티스트·라이브 검수 |
| `batch_kind` | TEXT | 필수 | initial 또는 incremental | initial |
| `status` | TEXT | 필수·기본 reviewing | reviewing, frozen, published, cancelled 제안값 | reviewing |
| `target_catalog_id` | TEXT UUID | 선택·NULL | 대상 원격 catalog_instance.id. 스키마 준비 전 비움; 반영 전 필수 | 대상 UUID |
| `notes` | TEXT | 선택·NULL | 검수 범위·제외 기준 등 로컬 메모 | 1차 반영 대상 메모 |
| `revision` | INTEGER | 필수·기본 1 | 배치 구성/상태 변경 번호 | 1 |
| `created_at` | TEXT UTC | 필수·앱 기록 | 이 로컬 행을 처음 만든 UTC ISO 8601 시각 | 2026-09-19T02:00:00Z |
| `updated_at` | TEXT UTC | 필수·앱 기록 | 이 로컬 행을 마지막 수정한 시각 | 2026-09-19T02:00:00Z |

**연결·검증 규칙**

- 승인/보류 개수는 draft_entities에서 계산하며 별도 누적 숫자를 진실의 원본으로 쓰지 않습니다.
- frozen 이후 입력 내용이 바뀌면 기존 반영 계획을 무효화하고 새 revision/계획을 만듭니다.

<a id="input_files"></a>

### 33. input_files — 입력 파일과 원본 보관

**저장 위치:** 내 PC SQLite

읽어들인 JSON 파일을 해시로 식별하고 원본 스냅샷을 보관합니다.

| 필드 | 자료형 | 필수 여부 / 기본값 | 설명·연결 대상 | 예시 |
| --- | --- | --- | --- | --- |
| `id` | TEXT UUID PK | 필수·앱 생성 | 로컬 행의 고유 UUID. 입력 파일이 지정한 승인/이력 ID는 그대로 신뢰하지 않음 | 로컬 UUID |
| `batch_id` | TEXT UUID FK | 필수 | import_batches.id | 배치 UUID |
| `relative_path` | TEXT | 필수 | 허용된 input 폴더 기준 상대 경로 | input-001.json |
| `file_hash` | TEXT | 필수 | 원본 파일 바이트의 SHA-256 | 64자리 해시 |
| `byte_size` | INTEGER | 필수 | 파일 크기(바이트) | 2048 |
| `schema_version` | TEXT | 선택·NULL | 읽어낸 입력 JSON 계약 버전. 파싱 실패 시 NULL | 1 |
| `snapshot_path` | TEXT | 필수 | workspace 기준 보관 사본 상대 경로 | snapshots/해시.json |
| `parse_status` | TEXT | 필수·기본 pending | pending, valid, invalid | valid |
| `error_message` | TEXT | 선택·NULL | 비밀 제거한 파싱/검증 오류 요약 | entities 필드 형식 오류 |
| `imported_at` | TEXT UTC | 선택·NULL | 초안 생성 완료 시각 | 2026-09-19T02:00:00Z |
| `created_at` | TEXT UTC | 필수·앱 기록 | 이 로컬 행을 처음 만든 UTC ISO 8601 시각 | 2026-09-19T02:00:00Z |
| `updated_at` | TEXT UTC | 필수·앱 기록 | 이 로컬 행을 마지막 수정한 시각 | 2026-09-19T02:00:00Z |

**연결·검증 규칙**

- UNIQUE(batch_id, file_hash), byte_size >= 0. 같은 파일을 다시 읽어도 초안을 중복 생성하지 않습니다.
- 파일이 수정되면 새 해시/원본 사본으로 등록합니다. 같은 client_ref 충돌은 기존 초안의 새 revision으로 검수합니다.
- 허용 폴더 바깥 경로·..·junction 우회는 거부합니다. snapshot_path에 파일이 실제 존재하는지 검증합니다.

<a id="draft_entities"></a>

### 34. draft_entities — 검수 중인 자료

**저장 위치:** 내 PC SQLite

음악 데이터를 실제 DB에 넣기 전 수정하고 승인하는 초안입니다.

| 필드 | 자료형 | 필수 여부 / 기본값 | 설명·연결 대상 | 예시 |
| --- | --- | --- | --- | --- |
| `id` | TEXT UUID PK | 필수·앱 생성 | 로컬 행의 고유 UUID. 입력 파일이 지정한 승인/이력 ID는 그대로 신뢰하지 않음 | 로컬 UUID |
| `batch_id` | TEXT UUID FK | 필수 | import_batches.id | 배치 UUID |
| `input_file_id` | TEXT UUID FK | 선택·NULL | input_files.id. 완전 수동 초안이면 NULL | 파일 UUID |
| `client_ref` | TEXT | 필수 | 배치 안에서 사용할 임시 고유 이름 | artist:hachi |
| `entity_type` | TEXT | 필수 | 허용된 카탈로그 입력 유형 | artists |
| `operation` | TEXT | 필수 | create 또는 update. 병합은 별도 검수 작업 | create |
| `target_id` | INTEGER | 선택·NULL | update할 원격 행 ID. create면 NULL | 1 |
| `expected_version` | INTEGER | 선택·NULL | update가 기준으로 삼은 원격 부모 version | 3 |
| `original_payload` | TEXT JSON | 필수 | 최초 입력값을 변경하지 않고 보관. 새 파일 원본은 input_files에도 보존 | 원본 JSON 객체 |
| `current_payload` | TEXT JSON | 필수 | 현재 편집된 데이터와 타입이 있는 관계 참조 | 수정한 JSON 객체 |
| `provenance` | TEXT JSON | 필수·기본 {} | 공식 출처·원문 위치·생성 모델/프롬프트 버전. 기존 DB table/id 제외 | 출처 객체 |
| `revision` | INTEGER | 필수·기본 1 | 초안 변경마다 증가하는 번호 | 2 |
| `status` | TEXT | 필수·기본 pending | pending, editing, blocked, approved, held, excluded, publishing, published | editing |
| `approved_revision` | INTEGER | 선택·NULL | 사람이 승인한 초안 revision. 승인 해제 시 NULL | 2 |
| `approved_hash` | TEXT | 선택·NULL | 승인한 payload와 참조 의존성의 정규화 SHA-256 | 64자리 해시 |
| `approved_at` | TEXT UTC | 선택·NULL | 로컬에서 실제 승인한 시각 | NULL |
| `review_note` | TEXT | 선택·NULL | 검수 메모·보류/제외 이유. 원격에 자동 복사하지 않음 | 원곡자 확인 필요 |
| `ai_confidence` | REAL | 선택·NULL | AI가 제공한 0~1 참고 점수. 승인 판단을 대신하지 않음 | 0.8 |
| `created_at` | TEXT UTC | 필수·앱 기록 | 이 로컬 행을 처음 만든 UTC ISO 8601 시각 | 2026-09-19T02:00:00Z |
| `updated_at` | TEXT UTC | 필수·앱 기록 | 이 로컬 행을 마지막 수정한 시각 | 2026-09-19T02:00:00Z |

**연결·검증 규칙**

- UNIQUE(batch_id, client_ref). 원격 대상은 배치 target_catalog_id와 target_id의 조합으로 식별합니다.
- update는 target_id/expected_version 필수, create는 둘 다 NULL. version이 없는 종속 행은 소유 부모를 편집 단위로 묶습니다.
- 값·관계·의존 초안이 바뀌면 승인 필드를 비우고 재검수합니다. AI 입력의 approved 필드는 승인 기록으로 인정하지 않습니다.
- 연결 테이블 한 행마다 반드시 별도 초안을 만들 필요는 없습니다. 라이브와 세트리스트처럼 하나의 폼 단위 payload 안에 종속 행을 포함할 수 있습니다.

<a id="draft_relations"></a>

### 35. draft_relations — 초안 관계 검증용 목록

**저장 위치:** 내 PC SQLite

초안 payload 안의 아티스트·곡 연결을 추출해 누락·제외된 참조를 찾습니다.

| 필드 | 자료형 | 필수 여부 / 기본값 | 설명·연결 대상 | 예시 |
| --- | --- | --- | --- | --- |
| `id` | TEXT UUID PK | 필수·앱 생성 | 로컬 행의 고유 UUID. 입력 파일이 지정한 승인/이력 ID는 그대로 신뢰하지 않음 | 로컬 UUID |
| `source_draft_id` | TEXT UUID FK | 필수 | 관계를 갖는 draft_entities.id | 초안 UUID |
| `field_path` | TEXT | 필수 | payload에서 관계의 위치. JSON Pointer 형식 | /performers/0/artist_ref |
| `target_type` | TEXT | 필수 | 참조할 카탈로그 유형 | artists |
| `target_draft_id` | TEXT UUID FK | 선택·NULL | 로컬에서 연결된 draft_entities.id | 다른 초안 UUID |
| `target_catalog_id` | TEXT UUID | 선택·NULL | 이미 있는 원격 자료의 카탈로그 ID | 카탈로그 UUID |
| `target_entity_id` | INTEGER | 선택·NULL | 이미 있는 원격 자료의 ID | 1 |
| `unresolved_ref` | TEXT | 선택·NULL | 아직 못 찾은 원래 client_ref | artist:unknown |
| `is_required` | INTEGER BOOLEAN | 필수 | 입력 계약에서 반드시 있어야 하는 관계인지 | 1 |
| `source_revision` | INTEGER | 필수 | 어느 초안 revision에서 추출했는지 | 2 |
| `created_at` | TEXT UTC | 필수·앱 기록 | 이 로컬 행을 처음 만든 UTC ISO 8601 시각 | 2026-09-19T02:00:00Z |
| `updated_at` | TEXT UTC | 필수·앱 기록 | 이 로컬 행을 마지막 수정한 시각 | 2026-09-19T02:00:00Z |

**연결·검증 규칙**

- UNIQUE(source_draft_id, field_path). 초안 참조 / 원격 참조 쌍 / 미해결 문자열 중 정확히 한 방식으로 저장합니다.
- current_payload가 편집 원본이고 이 표는 같은 로컬 트랜잭션에서 재생성하는 검증용 파생 목록입니다. 두 곳을 따로 편집하지 않습니다.
- 의도적으로 NULL인 선택 관계는 이 표에 행을 만들지 않습니다. 존재하지 않는 ref와 검수된 미매칭 NULL은 다릅니다.

<a id="review_events"></a>

### 36. review_events — 검수 작업 이력

**저장 위치:** 내 PC SQLite

누가 어떤 초안을 수정·승인·보류했는지 추적합니다.

| 필드 | 자료형 | 필수 여부 / 기본값 | 설명·연결 대상 | 예시 |
| --- | --- | --- | --- | --- |
| `id` | TEXT UUID PK | 필수·앱 생성 | 로컬 행의 고유 UUID. 입력 파일이 지정한 승인/이력 ID는 그대로 신뢰하지 않음 | 로컬 UUID |
| `draft_id` | TEXT UUID FK | 필수 | draft_entities.id | 초안 UUID |
| `action` | TEXT | 필수 | edit, approve, hold, exclude, reopen, invalidate_approval, publish 제안값 | approve |
| `actor_label` | TEXT | 필수·앱 기록 | 로컬 운영자 식별 표시. AI 파일에서 신뢰하여 복사하지 않음 | local_operator |
| `revision` | INTEGER | 필수 | 해당 동작 시점 초안 revision | 2 |
| `payload_hash` | TEXT | 선택·NULL | 동작 대상 payload/의존성 해시. approve면 필수 | 64자리 해시 |
| `change_data` | TEXT JSON | 필수·기본 {} | 수정 필드·전후 값 또는 상태 변경 정보 | 수정 내역 |
| `note` | TEXT | 선택·NULL | 승인·보류·제외 설명 | 원문 확인 완료 |
| `created_at` | TEXT UTC | 필수·앱 기록 | 이 로컬 행을 처음 만든 UTC ISO 8601 시각 | 2026-09-19T02:00:00Z |

**연결·검증 규칙**

- append-only 이력입니다. 승인 취소도 기존 승인 행을 지우지 않고 새 이력으로 기록합니다.
- 같은 revision이어도 의존성이 바뀌면 승인 hash가 달라지므로 기존 승인을 재사용하지 않습니다.

<a id="validation_issues"></a>

### 37. validation_issues — 오류·경고 목록

**저장 위치:** 내 PC SQLite

왜 반영할 수 없는지, 어떤 정보가 미확정인지 필드별로 안내합니다.

| 필드 | 자료형 | 필수 여부 / 기본값 | 설명·연결 대상 | 예시 |
| --- | --- | --- | --- | --- |
| `id` | TEXT UUID PK | 필수·앱 생성 | 로컬 행의 고유 UUID. 입력 파일이 지정한 승인/이력 ID는 그대로 신뢰하지 않음 | 로컬 UUID |
| `batch_id` | TEXT UUID FK | 필수 | import_batches.id | 배치 UUID |
| `draft_id` | TEXT UUID FK | 선택·NULL | 초안 관련 오류면 draft_entities.id | 초안 UUID |
| `input_file_id` | TEXT UUID FK | 선택·NULL | 파일 수준 오류면 input_files.id | 파일 UUID |
| `checked_revision` | INTEGER | 선택·NULL | 검증한 초안 revision. 파일 오류면 NULL | 2 |
| `field_path` | TEXT | 선택·NULL | 문제 필드의 JSON Pointer | /starts_at |
| `severity` | TEXT | 필수 | error(차단) 또는 warning(검토 필요) | warning |
| `code` | TEXT | 필수 | 기계가 구별하는 안정적인 오류 코드 | UNKNOWN_SONG |
| `message` | TEXT | 필수 | 사람이 읽는 이유·해결 방향 | 곡 연결을 확인해 주세요 |
| `status` | TEXT | 필수·기본 open | open, resolved, acknowledged, superseded | open |
| `resolution_note` | TEXT | 선택·NULL | 해결/경고 수용 이유 | 원곡 미상으로 확인 |
| `resolved_at` | TEXT UTC | 선택·NULL | 해결 또는 경고 수용 시각 | NULL |
| `created_at` | TEXT UTC | 필수·앱 기록 | 이 로컬 행을 처음 만든 UTC ISO 8601 시각 | 2026-09-19T02:00:00Z |
| `updated_at` | TEXT UTC | 필수·앱 기록 | 이 로컬 행을 마지막 수정한 시각 | 2026-09-19T02:00:00Z |

**연결·검증 규칙**

- draft/file 참조가 있으면 같은 batch인지 검증합니다. 둘 다 NULL인 배치 전체 오류도 허용합니다.
- error는 단순 수용으로 우회하지 못합니다. warning은 이유를 남겨 수용할 수 있습니다.
- 초안 수정 후 과거 revision 오류를 현재 오류로 표시하지 않도록 superseded 처리하고 다시 검사합니다.

<a id="publish_plans"></a>

### 38. publish_plans — 고정된 반영 계획

**저장 위치:** 내 PC SQLite

승인한 자료·의존 관계·대상 DB를 묶어 확정한 목록입니다. 버튼을 누르기 전에 차이를 보여줍니다.

| 필드 | 자료형 | 필수 여부 / 기본값 | 설명·연결 대상 | 예시 |
| --- | --- | --- | --- | --- |
| `id` | TEXT UUID PK | 필수·앱 생성 | 로컬 행의 고유 UUID. 입력 파일이 지정한 승인/이력 ID는 그대로 신뢰하지 않음 | 로컬 UUID |
| `batch_id` | TEXT UUID FK | 필수 | import_batches.id | 배치 UUID |
| `operation_id` | TEXT UUID | 필수·고유 | 이 반영 작업의 재시도 공통 ID | 작업 UUID |
| `target_catalog_id` | TEXT UUID | 필수 | 원격 catalog_instance.id | 카탈로그 UUID |
| `expected_schema_version` | TEXT | 필수 | 검토한 원격 스키마 계약 버전 | catalog-v2 |
| `manifest_payload` | TEXT JSON | 필수 | 정렬된 포함/제외 목록·revision·hash·원격 version·의존성·승인 데이터 | 고정된 반영 내용 |
| `manifest_hash` | TEXT | 필수 | manifest 정규화 SHA-256 | 64자리 해시 |
| `status` | TEXT | 필수·기본 ready | ready, publishing, committed, invalidated, cancelled | ready |
| `frozen_at` | TEXT UTC | 필수·앱 기록 | 내용을 고정한 시각 | 2026-09-19T02:00:00Z |
| `created_at` | TEXT UTC | 필수·앱 기록 | 이 로컬 행을 처음 만든 UTC ISO 8601 시각 | 2026-09-19T02:00:00Z |
| `updated_at` | TEXT UTC | 필수·앱 기록 | 이 로컬 행을 마지막 수정한 시각 | 2026-09-19T02:00:00Z |

**연결·검증 규칙**

- manifest 내용과 hash는 생성 후 불변입니다. 대상/초안 변경 시 기존 계획을 invalidated로 바꾸고 새 계획을 만듭니다.
- 자동 승인 없이 사용자 확인 후 반영합니다. 만료 시간만으로 승인 내용을 바꾸지 않습니다.

<a id="publish_attempts"></a>

### 39. publish_attempts — 반영 시도·복구 이력

**저장 위치:** 내 PC SQLite

원격 저장 도중 끊겼을 때 실패인지 성공 후 응답 유실인지 구분합니다.

| 필드 | 자료형 | 필수 여부 / 기본값 | 설명·연결 대상 | 예시 |
| --- | --- | --- | --- | --- |
| `id` | TEXT UUID PK | 필수·앱 생성 | 로컬 행의 고유 UUID. 입력 파일이 지정한 승인/이력 ID는 그대로 신뢰하지 않음 | 로컬 UUID |
| `plan_id` | TEXT UUID FK | 필수 | publish_plans.id | 계획 UUID |
| `attempt_number` | INTEGER | 필수 | 같은 계획의 시도 순번 | 1 |
| `state` | TEXT | 필수·기본 started | started, committed, failed, unknown | unknown |
| `started_at` | TEXT UTC | 필수·앱 기록 | 이번 네트워크 반영 시도 시작 시각 | 2026-09-19T02:00:00Z |
| `finished_at` | TEXT UTC | 선택·NULL | 결과가 확인된 시각 | NULL |
| `remote_import_id` | INTEGER | 선택·NULL | 성공 확인 후 원격 catalog_imports.id | 1 |
| `error_code` | TEXT | 선택·NULL | 분류 가능한 오류 코드 | RESPONSE_LOST |
| `error_message` | TEXT | 선택·NULL | 비밀을 제거한 오류 요약 | 반영 결과 확인 필요 |
| `remote_result` | TEXT JSON | 선택·NULL | 원격 영수증에서 확인한 결과 ID·건수 | 확인된 저장 결과 |
| `created_at` | TEXT UTC | 필수·앱 기록 | 이 로컬 행을 처음 만든 UTC ISO 8601 시각 | 2026-09-19T02:00:00Z |
| `updated_at` | TEXT UTC | 필수·앱 기록 | 이 로컬 행을 마지막 수정한 시각 | 2026-09-19T02:00:00Z |

**연결·검증 규칙**

- UNIQUE(plan_id, attempt_number), attempt_number >= 1. 재시도에도 plan.operation_id는 유지합니다.
- timeout은 unknown일 수 있습니다. 같은 작업 ID의 원격 영수증을 확인한 뒤 재시도 여부를 판단합니다.
- 원격 COMMIT과 로컬 SQLite 갱신이 하나의 트랜잭션이라고 가정하지 않습니다.

<a id="remote_id_map"></a>

### 40. remote_id_map — 로컬 초안과 원격 ID 대응

**저장 위치:** 내 PC SQLite

반영 완료된 초안이 새 DB에서 어떤 ID가 됐는지 찾는 로컬 장부입니다.

| 필드 | 자료형 | 필수 여부 / 기본값 | 설명·연결 대상 | 예시 |
| --- | --- | --- | --- | --- |
| `id` | TEXT UUID PK | 필수·앱 생성 | 로컬 행의 고유 UUID. 입력 파일이 지정한 승인/이력 ID는 그대로 신뢰하지 않음 | 로컬 UUID |
| `draft_id` | TEXT UUID FK | 필수 | draft_entities.id | 초안 UUID |
| `target_catalog_id` | TEXT UUID | 필수 | 원격 catalog_instance.id | 카탈로그 UUID |
| `entity_type` | TEXT | 필수 | 대응된 원격 카탈로그 유형 | artists |
| `entity_id` | INTEGER | 필수 | 원격 자료 ID | 1 |
| `remote_version` | INTEGER | 선택·NULL | 마지막 확인한 원격 version. 관계 행 등 version 없으면 NULL | 1 |
| `operation_id` | TEXT UUID | 필수 | 대응을 확정한 publish_plans.operation_id 또는 확인된 수동 작업 ID | 작업 UUID |
| `mapped_at` | TEXT UTC | 필수·앱 기록 | 영수증에서 대응을 확인한 시각 | 2026-09-19T02:00:00Z |
| `created_at` | TEXT UTC | 필수·앱 기록 | 이 로컬 행을 처음 만든 UTC ISO 8601 시각 | 2026-09-19T02:00:00Z |
| `updated_at` | TEXT UTC | 필수·앱 기록 | 이 로컬 행을 마지막 수정한 시각 | 2026-09-19T02:00:00Z |

**연결·검증 규칙**

- UNIQUE(draft_id, target_catalog_id, entity_type, entity_id). 한 묶음 초안이 여러 종속 원격 행을 생성할 수 있습니다.
- 로컬에서 원격 DB로 직접 FK를 걸 수 없습니다. 영수증과 대상 카탈로그를 대조하여 검증합니다.

## H. 소유 관계와 수정·삭제 기준

‘소유 부모’는 그 연결을 어느 편집 화면에서 관리하는지 뜻합니다. 아래 관계를 수정하면 해당 부모의 version과 updated_at을 갱신합니다. 다른 쪽 대상은 함께 삭제하지 않습니다.

| 연결 표 | 소유 부모 | 삭제하지 않을 연결 대상 |
| --- | --- | --- |
| artist_aliases, artist_external_accounts | artists | 외부 계정 |
| artist_group_members | 그룹인 artists | 멤버 artists |
| song_artists, karaoke_numbers | songs | 아티스트 |
| archive_artists, archive_sources | live_archives | 아티스트·원문 |
| performance_artists | performances 및 소속 live_archives | 아티스트 |
| concert_artists, concert_ticket_windows | concerts | 아티스트 |
| album_artists, album_tracks | albums | 아티스트·녹음 |
| recording_artists, recording_external_ids | recordings | 아티스트 |
| cover_artists | covers | 아티스트 |

recording_lyrics 변경은 자신의 version과 녹음의 version도 올리는 안입니다. 원문(source_documents), 반영 영수증(catalog_imports), 변경 이력(catalog_changes)은 일반 편집 폼에서 직접 덮어쓰지 않습니다. 사용 중인 곡·아티스트·녹음의 물리 삭제는 제한하고 보관 처리를 우선합니다.

연결 대상이 보관 상태라는 이유로 과거 가창·공연 이력을 지우지 않습니다. 보관 자료가 포함된 과거 결과를 어떻게 표시할지는 조회 DTO에 상태를 명시하여 일관되게 처리해야 합니다.

## I. JSON 필드에는 무엇이 들어가는가

아래는 구조 설명입니다. JSON 내부를 고정 관계 테이블의 대체물로 사용하지 않습니다. 실제 입력 JSON Schema v1은 구현 단계에서 이 구조에 맞춰 검증 계약으로 작성합니다.

| 필드 | 제안하는 내부 항목 | 설명 |
| --- | --- | --- |
| source_documents.source_metadata | provider, external_ids, extraction | 플랫폼 식별, 원문 확보·추출 방법/버전. 기존 DB table/id와 대응 정보는 저장하지 않음. 원본에 없던 정보는 만들지 않음 |
| catalog_imports.result_mapping | client_ref, entity_type, entity_id, version의 객체 배열 | 초안 이름을 어느 확정 ID로 저장했는지. version 없는 관계 행은 null |
| catalog_imports.result_summary | created_count, updated_count, archived_count, excluded_count | 결과 요약. 서로 다른 의미의 행 수를 섞지 않도록 유형별 수량을 추가할 수 있음 |
| catalog_changes.before_data / after_data | 해당 리소스의 변경 전후 필드와 관계 | 비밀번호나 관리자 세션은 포함하지 않음. 부모 묶음으로 저장하면 관계 변경도 식별 가능해야 함 |
| catalog_changes.provenance | document_ids, approved_hash | 검수 근거. 로컬 보류 메모/AI 점수는 자동 전송하지 않음 |
| draft_entities.original_payload / current_payload | 해당 유형의 필드, 종속 행, 타입이 명확한 *_ref | 원문과 현재 편집값을 비교. FK가 아직 없으면 client_ref로 연결 |
| draft_entities.provenance | source_url, extraction, generator | generator는 model/prompt_version 등 재현 정보. 기존 DB table/id는 포함하지 않음. 모르는 값은 생략 |
| review_events.change_data | fields, before, after 또는 이전/새 상태 | 편집·승인 취소 등의 이유를 추적 |
| publish_plans.manifest_payload | target_catalog_id, schema_version, batch_revision, entities, excluded, dependencies | entities에 draft_id/revision/approved_hash/operation/target_id/expected_version/승인 데이터 포함. 의존성도 revision/hash로 고정 |
| publish_attempts.remote_result | operation_id, import_id, manifest_hash, result_mapping, result_summary | 서버가 확인한 영수증 결과. 대상 DB ID와 함께 검증 |

초기 JSON 예시에서는 entity_type을 artist처럼 단수로 표현했습니다. 이 상세안은 저장 대상 식별에 artists 등 표 이름을 사용합니다. 최종 JSON v1에서 단수 입력을 허용한다면 명시적 변환표로 처리하고, 사용자 문자열을 SQL 테이블명으로 직접 실행하지 않습니다.

해시는 키 정렬·문자 인코딩·배열 순서 등 동일한 정규화 규칙으로 서버가 계산합니다. 사람의 이름을 비교하는 검색 정규화와 승인 payload 해시 규칙은 다른 목적입니다.

## J. 화면에서 보이지만 저장 컬럼으로 만들지 않는 것

| 화면 정보 | 어디서 구하는가 |
| --- | --- |
| 아티스트의 ‘원곡자/가창자’ 분류 | song_artists, performance_artists 등의 관계 존재 여부 |
| 한국어 이름이 없을 때 원어 이름 | name_ko/title_ko가 NULL이면 화면에서 원어로 대체 |
| YouTube 재생 URL·일반 썸네일 후보 주소 | videos.platform_video_id로 생성. 실제 응답 실패는 별도 폴백 |
| 15:30 같은 재생 시각 | performances.start_seconds로 계산. 수집 원문은 raw_timestamp로 보존 |
| 라이브 개수·부른 횟수·고유 곡 수 | 참여 방송·가창 행·song_id를 집계 |
| 월별 활동량 | 방송 시각을 계약된 시간대로 변환하여 월별 집계 |
| 아티스트 순위·가창 비율 | 곡의 원곡자와 가창 기록 관계에서 계산. 공동 원곡 비율 정책은 미확정 |
| 앨범 수록곡의 곡 정보·가사 | album_tracks → recordings → songs / recording_lyrics |
| 출처 URL 버튼 | 연결된 source_documents.source_url 또는 링크 필드 |
| 검수 진행률 | draft_entities 상태를 조회해 계산 |

추후 속도를 위해 집계표·캐시를 도입할 수 있지만 원본 사실을 저장하는 표와 구분합니다. 이 문서에는 아직 결정하지 않은 캐시 컬럼을 필수 필드처럼 추가하지 않았습니다.

## K. 실제 입력 흐름 예시

1. 로컬 input_files가 입력 파일을 기록하고 원본 사본을 보관합니다.
2. draft_entities에서 아티스트·곡·라이브 초안을 편집합니다. draft_relations와 validation_issues가 연결 누락을 안내합니다.
3. 사람이 승인하면 review_events에 기록하고 승인한 revision/hash를 고정합니다. 수정하면 승인을 해제합니다.
4. 초기 배치의 모든 자료가 승인 또는 제외여야 publish_plans를 만들 수 있습니다. 보류·오류·깨진 참조가 있으면 차단합니다.
5. 반영 버튼을 누르면 현재 대상 DB·스키마·revision·원격 version을 다시 확인합니다.
6. 새 DB의 음악 자료, catalog_imports, catalog_changes를 한 트랜잭션으로 저장합니다. 초기 반영이면 catalog_instance의 완료 표시도 함께 저장합니다.
7. COMMIT 결과를 확인한 후 로컬 publish_attempts와 remote_id_map을 갱신합니다. 연결이 끊기면 operation_id로 원격 영수증을 먼저 조회합니다.
8. 초기 구축 후 수동 등록은 사람이 입력하고 저장한 행위를 승인으로 취급합니다. 매번 별도 배치 검수를 강제하지 않지만 version·영수증·변경 이력은 동일하게 적용합니다.

예를 들어 HACHI가 Lemon을 부른 한 번의 가창은 artists(HACHI), artists(원곡자), songs(Lemon), song_artists(원곡자 연결), videos(영상), live_archives(방송), performances(시점), performance_artists(HACHI 연결)로 이어집니다. 다음 방송에서 같은 노래를 부르면 아티스트·곡을 다시 만들지 않고 새 방송/가창 행만 추가합니다.

## L. 아직 확정하지 않은 정책과 이번에 만들지 않는 것

| 항목 | 현재 설계 상태 |
| --- | --- |
| 통합 아티스트 명부 / 음악 카탈로그 우선 | 사용자 확정 |
| 모든 초기 데이터의 사용자 검수 후 반영 | 사용자 요구. 계획 전체에 적용 |
| 공동 원곡자의 순위 비율 | 1/n 기여도 배분 권장안과 중복 포함 비율 중 최종 결정 필요 |
| 방송 개수·활동량 범위 | 참여 방송 전체 권장, host만 보기 별도. 최종 표시 정책 결정 필요 |
| 날짜 미정/날짜만 확인된 방송 | 가짜 시각 없이 원문 보존. 월별 통계 제외 및 날짜 정밀도 확장 검토 |
| 커버 메들리 | 단일 곡에 강제 연결하지 않음. cover_songs 추가 또는 1차 보류 결정 필요 |
| 그룹 재가입·날짜 미상 탈퇴 / 복수 소속 | 현재 단순 관계의 한계. 필요 시 기간·상태 구조 확장 |
| 티켓 판매의 날짜만 아는 정보·별도 시간대 | 정확한 시각만 입력, 원문 보존. 정밀도 확장 여부 검토 |
| 곡 약칭 별도 표 song_aliases | 1차 제외. 원어/한국어/영문 필드 검색 |
| 동기화 가사·여러 번역본·다중 공식 MV | 현재 단순 필드 범위 밖 |
| 사용자 계정·즐겨찾기 동기화·Google | 별도 단계. Google 데이터는 기존 DB에 보존 |
| Discord·수집 운영 이력 | migration 002에 추가. 상세 계약은 2단계 결과 참조 |
| 기술용 migration 버전 표 | catalog_schema_migrations(version, checksum, applied_at)에 001·002 적용 완료 |
| 원격 DDL·인덱스·트리거 | migration 001·002 적용·검증 완료. 실제 구현 범위는 마이그레이션 안내 참조 |
| 로컬 검수 DB·관리자 API/웹 | 2026-09-20 1차 구현. 사용자 조회 API 전환은 후속 |

이 문서는 원격 업무 구조와 로컬 검수 계획을 함께 설명합니다. 원격 DDL은 적용했고 초기 음악 데이터는 입력하지 않았습니다. 승인/manifest 검사, 그룹·대표 계정·영상 길이·출연진/근거의 교차 데이터 검증은 관리자 API에서 수행합니다. 실제 운영 범위와 후속 개선은 [관리자 안내](../docs/admin-web-plan.md)를 참고하세요.
