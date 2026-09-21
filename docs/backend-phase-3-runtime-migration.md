# 백엔드 통합 3단계 결과 — 선택 이전 도구와 검증

완료일: 2026-09-21. 이 단계에서는 기존 DB와 신규 DB를 모두 읽기 전용으로 확인했다. 실제 운영 데이터 이전은 실행하지 않았다.

## 도구 계약

[`scripts/migrate_runtime_state.py`](../scripts/migrate_runtime_state.py)는 기본 실행이 dry-run이다. 기존 DB의 `DATABASE_URL`과 신규 DB의 `NEW_DATABASE_URL`이 같으면 중단하며, 기존 DB에는 항상 읽기 전용 트랜잭션을 사용한다.

도구는 매 실행마다 1단계의 고정 ID·handle 매핑과 제외 source를 다시 검증하고 다음 순서로 계획을 만든다.

1. X source와 YouTube monitor를 신규 `external_accounts`에 대응한다.
2. 계정 version, cursor 선택, route 소유권·guild/channel 소속을 검사한다.
3. 성공 delivery가 참조하는 원문과 검토된 `Hao_RKM` 합집합만 선택한다.
4. 같은 account/external ID 원문은 payload가 같을 때만 합치고 가장 이른 수집 시각을 보존한다.
5. Discord message ID가 있는 성공 delivery만 `sent` 이전 대상으로 만든다.
6. YouTube의 완료 작업은 제외하고 미완료 작업만 `worker_jobs` 후보로 만든다.
7. 선택 내용 전체의 source snapshot hash와 공개 manifest hash를 생성한다.

Google, X 분류, X→YouTube 자동 등록, 기존 음악 카탈로그, 완료 YouTube 작업은 허용 목록 밖이라 기본 제외한다.

## 적용 안전장치

`--apply`는 dry-run manifest의 `approved_for_apply`가 명시적으로 `true`이고 나머지 필드와 hash가 현재 재조회 결과와 정확히 같을 때만 진행한다. 적용 직전 다음 조건도 다시 검사한다.

- 대상은 동일한 `catalog_instance`, `catalog-v2`, revision `001/002`다.
- 선택된 모든 external account version이 dry-run 때와 같다.
- 같은 영수증이 없으면 운영 표가 비어 있어야 한다.
- route·원문·delivery·job 참조가 모두 계획 안에서 해소된다.
- 적용은 한 트랜잭션이며 `runtime_migration_receipts`와 `runtime_legacy_id_map`을 함께 기록한다.
- 같은 승인 manifest 재실행은 기존 영수증을 확인하고 새 행을 만들지 않는다.

실제 적용 승인은 5단계 전환 시점의 최종 snapshot에 대해 별도로 한다. 현재 생성된 manifest는 `approved_for_apply: false`다.

## 실제 dry-run 결과

2026-09-21 신규 DB `catalog-v2`를 대상으로 읽기 전용 dry-run을 완료했다.

| 대상 | 신규 행 후보 |
| --- | ---: |
| 계정별 수집 상태 | 125 |
| Discord route | 51 |
| 중복 병합 후 X 원문 | 4,454 |
| 성공 전송 이력 | 4,369 |
| 미완료 YouTube 작업 | 100 |

1단계 집계 뒤에도 기존 runtime이 계속 실행되어 성공 delivery는 4,365→4,369, 미완료 YouTube 작업은 99→100으로 변했다. 이 차이는 자동 적용하지 않았으며 현재 source snapshot hash에 반영했다. 전환 직전에 구 writer를 정지하고 dry-run을 다시 실행해야 한다. 원문 4,558개 선택 행은 account/external ID가 같은 104개 중복을 검증 후 병합해 신규 후보 4,454개가 됐다.

manifest는 Git 제외 경로 `db-migration/reports/single-db-readiness/runtime-migration-manifest.json`에 저장했다. DB URL, token, 원문, Discord ID는 manifest에 넣지 않았다.

## 테스트

로컬 PostgreSQL 18에서 합성 legacy 선택 집합을 신규 `catalog-v2`에 적용해 다음을 검증했다.

- 승인되지 않았거나 바뀐 manifest 거부
- 수집 상태→route→원문→sent delivery→worker job 참조 보존
- receipt와 legacy ID map의 같은 트랜잭션 기록
- 같은 manifest 재실행 시 중복 생성 0
- 기존 002 migration 회귀 테스트 유지

```powershell
.\.venv\Scripts\python.exe scripts/migrate_runtime_state.py
.\.venv\Scripts\python.exe -m pytest tests/test_runtime_state_migration.py -q -p no:cacheprovider
```

다음 단계는 external_accounts 기반 수집기와 최소 Discord sender를 신규 repository에 연결하는 4단계다.
