# 카탈로그 로컬 검수 구조 기록 (2026-09-20)

> 2026-11-23 로컬 관리자 앱(`admin-web/`, `app/admin/`) 삭제로 아래 구조는 현재 코드에 없다. 현재 원격 카탈로그 표는 [카탈로그 테이블·필드](../../catalog-schema.md)를 따른다. 이 문서는 2026-09-19~20 `catalog-schema.md`에 있던 로컬 검수 SQLite 설계와 입력·승인 흐름을 그대로 옮긴 기록이며, 당시 구현 범위는 [관리자 기록](admin-web-plan.md)에 있다.

## 저장소 구성 (당시)

| 내 PC의 관리자 SQLite | 9 | 원본 파일 목록, 편집 초안, 승인·보류, 반영 준비와 복구 |

SQLite의 UUID·시각·JSON은 TEXT로 저장하는 제안입니다. JSON은 파싱 검증하고 BOOLEAN은 INTEGER 0/1로 제한합니다. SQLite 내부 FK 검사를 활성화합니다. 원격 ID는 두 DB 사이에 실제 FK를 걸 수 없으므로 서버가 대상 카탈로그와 존재 여부를 확인합니다.

## 목차 (당시 G 그룹)

| 구역 | 테이블 | 설명 |
| --- | --- | --- |
| G | [import_batches](#import_batches) | 검수 배치 |
| G | [input_files](#input_files) | 입력 파일과 원본 보관 |
| G | [draft_entities](#draft_entities) | 검수 중인 자료 |
| G | [draft_relations](#draft_relations) | 초안 관계 검증용 목록 |
| G | [review_events](#review_events) | 검수 작업 이력 |
| G | [validation_issues](#validation_issues) | 오류·경고 목록 |
| G | [publish_plans](#publish_plans) | 고정된 반영 계획 |
| G | [publish_attempts](#publish_attempts) | 반영 시도·복구 이력 |
| G | [remote_id_map](#remote_id_map) | 로컬 초안과 원격 ID 대응 |

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

## JSON 필드 (로컬 표)

| 필드 | 제안하는 내부 항목 | 설명 |
| --- | --- | --- |
| draft_entities.original_payload / current_payload | 해당 유형의 필드, 종속 행, 타입이 명확한 *_ref | 원문과 현재 편집값을 비교. FK가 아직 없으면 client_ref로 연결 |
| draft_entities.provenance | source_url, extraction, generator | generator는 model/prompt_version 등 재현 정보. 기존 DB table/id는 포함하지 않음. 모르는 값은 생략 |
| review_events.change_data | fields, before, after 또는 이전/새 상태 | 편집·승인 취소 등의 이유를 추적 |
| publish_plans.manifest_payload | target_catalog_id, schema_version, batch_revision, entities, excluded, dependencies | entities에 draft_id/revision/approved_hash/operation/target_id/expected_version/승인 데이터 포함. 의존성도 revision/hash로 고정 |
| publish_attempts.remote_result | operation_id, import_id, manifest_hash, result_mapping, result_summary | 서버가 확인한 영수증 결과. 대상 DB ID와 함께 검증 |

화면의 검수 진행률은 draft_entities 상태를 조회해 계산했다.

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

당시 원격 문서 끝 문장: 승인/manifest 검사, 그룹·대표 계정·영상 길이·출연진/근거의 교차 데이터 검증은 관리자 API에서 수행했다.
