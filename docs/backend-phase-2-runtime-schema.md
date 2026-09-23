# 백엔드 통합 2단계 결과 — 운영 스키마와 연결 가드

완료일: 2026-09-21. 대상은 신규 PostgreSQL이며 기존 DB에는 연결·DDL·DML·migration을 수행하지 않았다.

## 적용 결과

신규 DB에 `002_runtime.sql`을 적용해 `catalog_instance.schema_version`을 `catalog-v2`로 올렸다. 기존 `001_initial.sql`, 카탈로그 31표의 구조, 음악 데이터와 검수 이력은 수정하지 않았다. 002가 추가한 운영 표는 다음 10개다.

| 표 | 책임 |
| --- | --- |
| `discord_users` | route 소유권에 필요한 최소 Discord 사용자 식별과 활성 상태 |
| `discord_guilds`, `discord_channels` | guild/channel 소속과 활성 상태 |
| `collection_states` | external account별 cursor, 마지막 외부 ID, poll/retry/lease 상태 |
| `source_items` | X 외부 ID·원문·원문 URL·게시/수집 시각. 분류 필드 없음 |
| `notification_routes` | external account에서 Discord channel로 가는 활성 route와 소유권 |
| `notification_deliveries` | route별 전송 대기·결과·재시도·lease·Discord message ID |
| `worker_jobs` | 독립 수집 작업의 idempotency key, 상태, 재시도, lease와 참조 |
| `runtime_migration_receipts` | 선택 이전 실행의 대상 DB·source fingerprint·manifest 영수증 |
| `runtime_legacy_id_map` | 구 테이블/ID에서 신규 운영 행으로의 명시적 대응 |

Google OAuth·Calendar 표, X 게시글 타입·confidence·추출 결과, X 글의 YouTube 링크 자동 등록 상태, Discord 명령 설정은 추가하지 않았다. `external_accounts.collection_enabled`가 수집 활성 여부의 단일 기준이고 `collection_states`는 실행 상태만 가진다.

## 보장하는 계약

- `(external_account_id, external_id)`로 X 원문 중복을 막는다.
- `(route_id, source_item_id)`로 같은 route의 같은 글 전송 작업을 중복 생성하지 않는다.
- route의 guild/channel 복합 FK로 다른 guild의 channel을 연결하지 못한다.
- sent delivery는 전송 시각과 Discord message ID가 있어야 한다.
- collection/delivery/job lease는 owner와 만료 시각을 함께 기록한다.
- worker job은 `(job_type, idempotency_key)`로 중복을 막고 완료 상태에 완료 시각을 요구한다.
- 이전 영수증과 legacy ID 대응은 UPDATE/DELETE할 수 없다.
- 관계 부모 삭제는 RESTRICT하며 기존 카탈로그 ID를 임의로 재해석하지 않는다.

## 설정과 연결 보호

2026-09-21 당시 `app/core/config.py`는 루트 `.env`와 과도기 `.env.catalog`를 함께 읽었다. 현재 단일 `DATABASE_URL` 계약은 [보완 5단계 결과](backend-service-step-5-migration.md)를 따른다. 선택적 `NEW_DATABASE_INSTANCE_ID`를 설정하면 고정 `catalog_instance.id`도 확인한다.

`app/db/catalog_session.py`는 session을 내주기 전에 revision `001`, `002`, `catalog-v2`, 선택적 instance ID를 검사한다. 불일치하면 503으로 중단한다. 현재 `app/core/db.py`의 구 SQL 연결 진입점은 호출 즉시 중단한다.

## 적용·검증 기록

로컬 PostgreSQL 18 임시 DB에서 14개 migration 테스트를 통과했다.

- 빈 DB에 001+002 원자 적용과 재실행
- 데이터가 있는 001 DB에 002만 적용하고 `external_accounts` 보존
- FK, guild/channel 소속, 원문·delivery·job 고유 제약
- delivery/job 상태와 lease 제약, 영수증 불변성
- revision/schema/instance identity 연결 가드
- 관리되지 않은 DB 거부, checksum/구조 drift 거부, 신규 DB의 legacy `init_db()` 차단

이후 신규 Neon DB에 002만 한 트랜잭션으로 적용했다. 별도 읽기 전용 연결에서 카탈로그 31표, 운영 10표, migration 표 1개, revision `001/002`, `catalog-v2`를 재검증했다. 신규 운영 표에는 아직 이전 데이터를 넣지 않았다. 기존 DB에는 어떤 확인 쿼리도 실행하지 않았다.

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_catalog_migration.py -q -p no:cacheprovider
.\.venv\Scripts\python.exe scripts/migrate_catalog.py --verify
```

다음 단계는 [3단계 선택 이전 도구](backend-consolidation-plan.md#3단계--선택-이전-도구와-검증)다. 도구의 dry-run과 재실행 안전성을 먼저 검증하고 실제 이전은 5단계 전환 시점에 수행한다.
