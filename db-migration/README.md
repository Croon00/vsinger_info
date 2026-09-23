# 로컬 입력·검수 작업 공간

애플리케이션에서 사용하는 로컬 자료를 보관한다. `input/`, `workspace/`, `reports/`, `archive/`는 Git에서 제외한다.

| 경로 | 용도 |
| --- | --- |
| `input/` | 관리자에서 명시적으로 가져올 원본 JSON |
| `workspace/` | 검수 SQLite, 원본 스냅샷, 이미지 이전 작업 자료 |
| `reports/` | 로컬 실행 결과·분석 보고서 |
| `archive/` | 이전 원본·일회성 작업 백업. 실행 코드가 아님 |

공유 문서는 [관리자 안내](../docs/admin-web-plan.md), [DB 설계](../docs/db-renewal-plan.md), [테이블·필드 명세](../docs/catalog-schema.md)에 둔다. 실행 SQL·스키마 계약·적용 보고서는 [migrations/catalog](../migrations/catalog/README.md)에 둔다.

2026-09-20 파일 정리 시 `archive/file-cleanup-2026-09-20/`에 기존 `DB.dump`, `exports.zip`, 미참조 `hachi_dusk.json`을 보존했다. 루트의 일회성 검수 Python 91개와 텍스트 13개는 `root-audit-files.zip`에 통합했다. `root-audit-files.manifest.json`에 원래 파일명·크기·SHA-256이 있으며 압축 후 내용 일치를 확인했다. 이 로컬 백업은 Git clone에 포함되지 않는다. 검수 스크립트는 외부 `DB_DATA`의 고정 경로를 사용하므로 복원하더라도 내용을 확인한 뒤 실행한다.
