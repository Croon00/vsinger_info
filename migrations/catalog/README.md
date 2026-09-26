# 새 카탈로그 DB 마이그레이션

최초 적용일: 2026-09-19. 운영 schema 적용일: 2026-09-21. 현재 revision은 `002`, 계약 버전은 `catalog-v2`다. 사용자 지정 Neon PostgreSQL 18.6에 실제 적용하고 별도 연결에서 읽기 전용 검증했다.

## 적용 결과

- 음악 카탈로그와 근거/반영 기록용 **31개 테이블, 276개 컬럼**을 유지한다.
- 수집·Discord 알림·worker·이전 감사용 운영 테이블 10개를 `002_runtime.sql`로 추가했다.
- 기술용 `catalog_schema_migrations` 1개를 더해 public 사용자 테이블은 총 42개다.
- `catalog_instance`는 `catalog-v2`, migration 이력은 `001`, `002`다. 기존 음악 데이터와 검수 이력은 보존했다.
- 제거하기로 한 이미지 출처 필드, 별도 프로필 링크 표, 음악 크레딧, 곡 slug, 원곡자/공연 세부 역할, 기존 ID 대응표는 생성하지 않았다.
- `title_latin`, `language_code`, 노래방 번호는 유지했다.
- 로컬 검수 SQLite 9개 표와 관리자 API/웹은 2026-09-20 별도로 구현했다. [관리자 안내](../../docs/admin-web-plan.md)를 따른다.

실행 후 집계: [적용 보고서](schema-application-report.json).
필드 설명: [전체 테이블 명세](../../docs/catalog-schema.md).

## 파일과 접속 설정

| 파일 | 역할 |
| --- | --- |
| 001_initial.sql | 버전 고정 DDL. 음악 seed/덤프 복원 없음 |
| 002_runtime.sql | 계정별 수집 상태, X 원문, Discord route/delivery, worker 작업, 이전 영수증 |
| 003_latin_ascii.sql | `artists.name_latin`, `songs.title_latin`을 발음 부호 없는 ASCII로 제한. 계약 버전 `catalog-v2` 유지 |
| 004_song_identity.sql | 곡 별칭·외부 ID·원문 키 판정·병합 기록 4개 표 추가. 기존 표·컬럼 변경 없음 |
| song-identity-columns.json | 004가 추가한 4개 표의 필드·타입·NULL 계약. runner는 revision별로 계약 파일을 합쳐 검증 |
| columns.json | 31개 표의 필드·타입·NULL 계약 |
| runtime-columns.json | 10개 운영 표의 필드·타입·NULL 계약 |
| expected-schema.json | 로컬 PostgreSQL에서 검증한 컬럼·제약·인덱스·트리거·함수 정의 |
| ../../scripts/migrate_catalog.py | 명시적 실행, 빈 DB 검사, 트랜잭션/체크섬 검증 |

새 접속 정보는 루트의 Git 제외 파일 `.env`에 `DATABASE_URL`로 저장한다.
환경변수에 같은 키가 있으면 환경변수가 우선한다. 이전 원본 DB의 `LEGACY_DATABASE_URL`은 schema 도구가 읽지 않는다.
프론트 VITE 변수·문서·로그에 DB URL을 넣지 않는다.

## 실행

프로젝트 루트에서 실행한다. CLI는 기본 상태 조회이며 자동 마이그레이션하지 않는다.

```powershell
.\.venv\Scripts\python.exe scripts/migrate_catalog.py
.\.venv\Scripts\python.exe scripts/migrate_catalog.py --verify --require-empty
```

빈 새 DB에 전체 구조를 준비하거나 관리 중인 DB에 미적용 후속 revision을 적용할 때만 명시적으로 실행한다.

```powershell
.\.venv\Scripts\python.exe scripts/migrate_catalog.py --apply
```

- 전체 DDL과 기술 메타데이터는 하나의 트랜잭션이다. 중간 실패 시 그 트랜잭션은 rollback한다.
- 트랜잭션 advisory lock으로 동시 실행을 직렬화한다.
- 기존 서비스 표나 관리되지 않는 public 객체가 있으면 중단한다. DROP/초기화로 덮어쓰지 않는다.
- 같은 revision/체크섬/구조로 다시 실행하면 검증만 하고 다시 생성하지 않는다. 기존 001 DB에는 002만 적용한다.
- 예상치 않은 구조·체크섬 변경은 중단한다. 적용된 001 SQL을 수정해서 재실행하지 않는다. .gitattributes로 SQL의 줄바꿈 바이트를 보존하여 checkout 시 체크섬이 달라지지 않게 한다. 이후 변경은 별도 revision과 runner 확장으로 관리한다.
- 응답 유실은 실패로 단정하지 않는다. 먼저 `--verify`로 실제 반영 여부를 확인한다.
- Neon pooled endpoint에서는 연결 후 SET LOCAL로 timeout/search_path를 설정한다. 연결 초기 options에 의존하지 않는다.
- 카탈로그 ID는 즐겨찾기·캐시의 새 namespace로 사용할 값이다. 기존 DB ID 대응이나 즐겨찾기 자동 승계는 제공하지 않는다.

## DB가 현재 강제하는 규칙

- 필수/선택 필드, 외래키, 고유 번호와 복합 중복 방지.
- 날짜만/시간까지/미정 구분, 유효한 날짜·시간대, 공연 날짜와 현지 시작일의 일치.
- 생일 월/일의 쌍과 유효성, 연/월만 확인한 앨범 발매일.
- 시점/길이/순번의 기본 범위, 티켓 기간의 순서.
- 웹사이트/팬클럽 링크의 수집 비활성.
- 수정 시 timestamp/version 갱신, 관계 변경 시 소유 부모 version 갱신.
- 원문 스냅샷·반영 영수증·변경 이력의 UPDATE/DELETE 거부.
- revision 003(2026-09-27 운영 DB 적용, `--verify` 통과): latin 이름·제목은 출력 가능 ASCII만 허용. 001 스냅샷(`expected-schema.json`)은 이 제약을 제외하고 비교하며 `--verify`가 별도로 존재를 확인한다. 앱 revision 검사는 001-002와 001-003을 모두 허용한다.
- revision 004(2026-09-27 작성, 운영 DB 미적용): 곡 식별 4개 표. 외부 ID provider별 형식, 같은 외부 ID의 중복 연결 금지, 판정 상태와 song_id·판정자의 일치, 병합 기록 불변. 앱 revision 검사는 001-002부터 001-004까지 허용한다.
- 부모 자료 참조 보호. 명시적으로 소유된 연결 행만 부모 삭제 시 CASCADE.

정확한 규칙은 SQL과 로컬 테스트가 기준이다. 일반 FK·CHECK로 다른 행의 의미까지 모두 검증한다고 해석하지 않는다.
PostgreSQL의 CHECK와 행 간 제약의 범위는 [공식 제약조건 문서](https://www.postgresql.org/docs/18/ddl-constraints.html)를 참고한다.

## 관리자 정책과 조회 전환

2026-09-20 별도 관리자 API에 Pydantic 입력 계약, HTTP(S) 주소·날짜 검증, 별칭 정규화,
승인 hash, 그룹/멤버·대표 계정·영상 길이·출연진/근거 일관성 검사를 구현했다.
승인 취소, manifest 의존성 검사, 초기 반영 관문, 영수증 기반 복구도 구현했다.
수정 대상과 소유 부모 행을 잠근 상태에서 기대 버전을 비교하여 덮어쓰기를 거부한다.

2026-09-20 새 DB용 사용자 조회 DTO·통계·검색과 `web/` 연결을 구현했다. 현재 계약은 [조회 API v2](../../docs/read-api-v2.md)를 따른다.
DB 소유자의 직접 SQL은 관리자 검수 정책을 우회할 수 있다.
기존 init_db/수집기/구형 관리 API를 새 DB에 실행하지 않는다.
위 적용 결과의 음악 데이터 0건은 2026-09-19 검증 당시 값이다. 이 문서는 현재 운영 데이터 건수를 재조회한 기록이 아니다.

## 검증

2026-09-21 로컬 PostgreSQL 18의 임시 클러스터/임시 DB에서 합성 자료로 14개 테스트 통과.
로컬 테스트는 기존 .env와 Neon 접속 정보를 읽지 않으며, 원격으로 대체 실행하지 않는다.

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_catalog_migration.py -q -p no:cacheprovider
```

검증 범위: 전체 구조·초기 빈 상태·재실행, 001→002 데이터 보존 업그레이드, 기존 DB 거부,
실패 시 DDL rollback, 음악 카탈로그 제약, 운영 FK·guild/channel 소속·원문/delivery/job 중복 방지,
상태·lease 계약, 영수증 불변성, identity/revision guard, legacy init 차단, checksum·구조 drift 검출.

Windows 로컬 PostgreSQL 18의 initdb/pg_ctl이 필요하다. 다른 설치 경로는 POSTGRES_BIN으로 지정한다.
테스트 서버는 127.0.0.1 임시 포트에만 열고 종료 시 중단한다. 진단 로그는 Git 제외 .tmp 아래에 남는다.
Neon에는 합성 테스트 행을 넣지 않았다. 실제 검증은 적용된 스키마와 기존 데이터 보존 상태의 읽기 전용 확인이다. 운영 표의 선택 이전 데이터는 3단계 도구 검증 후 5단계 전환 시 반영한다.
