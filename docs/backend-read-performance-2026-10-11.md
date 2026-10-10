# 조회 지연 조사 — 2026-10-11

## 범위와 결론

사용자의 브라우저 캡처에서 라이브 목록 요청은 TTFB 5.68초, Server-Timing db 5.49초, queries 2로 표시됐다. 현재 로컬 `.env`의 신규 DATABASE_URL을 사용해 실제 데이터의 읽기 전용 조회를 검증했다. 기존 DB 접근, 데이터·schema·인덱스·provider 설정 변경, 수집·전송·LLM 호출은 수행하지 않았다. 운영 Railway의 환경·DB 대상 일치나 동시 부하·요금제는 직접 확인하지 못했다.

같은 연결에서 반복해도 느린 SQL이 재현됐다. 무료 요금제·절전만을 원인으로 단정할 수 없으며, 아티스트별 archive 범위를 구하는 SQL 실행 계획이 명확한 개선 대상이다. 애플리케이션 변경·배포는 이번 조사에 포함하지 않았다.

## 실제 데이터 측정

초기 연결 약 1,126ms. 연결 이후 SELECT 1 왕복 3회는 71.4 / 71.3 / 71.4ms였다. 최초 연결 시간에 DNS·TLS·인증 등이 포함되므로 절전 해제 시간으로 해석하지 않는다.

아티스트 확인을 포함한 repository query_ms 3회 중앙값:

| 아티스트 | 라이브 첫 6개 | 통계 |
|---|---:|---:|
| HACHI (12) | 7,445ms | 2,139ms |
| 羽緒 (26) | 1,262ms | 2,037ms |
| AZKi (995) | 1,194ms | 1,339ms |

query_ms는 연결된 DB와의 결과 수신까지 포함하며 브라우저 전체 로딩 시간이 아니다. 실제 API의 Server-Timing은 CatalogReadRepository.rows 내부 측정만 포함하고 session 초기화·identity 검증은 포함하지 않는다.

## 실행 계획과 비교 SQL

LIVE scope의 OR + correlated EXISTS가 영상 약 18,625개를 기준으로 archive·performance 관계를 반복 확인했다. HACHI 라이브 계획에서 archive 조회는 18,625회, performance 가창자 인덱스 조회는 232,339회 실행됐다. 통계의 월별 집계도 같은 scope를 사용한다. 인덱스는 사용되고 있으나 특정 아티스트의 후보를 먼저 좁히지 못하는 실행 계획이다.

진단용 SQL에서 scope만 다음 집합으로 대체했다: 대표 아티스트의 archive ID UNION 출연자의 archive ID UNION 활성 performance의 가창자 archive ID. 운영 코드에는 반영하지 않았다. 원본과 비교 SQL을 실제 데이터에서 모두 실행해 전체 반환 행·순서·집계가 같은지 검증한 뒤 EXPLAIN ANALYZE를 수행했다.

| 아티스트 | SQL | 원본 서버 실행 | 비교 SQL 서버 실행 |
|---|---|---:|---:|
| HACHI | 라이브 | 7,424ms | 159ms |
| HACHI | 통계 곡 | 361ms | 250ms |
| HACHI | 통계 월별 | 1,590ms | 110ms |
| 羽緒 | 라이브 | 1,555ms | 49ms |
| 羽緒 | 통계 곡 | 432ms | 240ms |
| 羽緒 | 통계 월별 | 1,231ms | 107ms |
| AZKi | 라이브 | 1,429ms | 16ms |
| AZKi | 통계 곡 | 133ms | 156ms |
| AZKi | 통계 월별 | 848ms | 22ms |

실행 계획 비교는 각 1회다. 원본 실행 계획과 비교 계획은 같은 시점의 교대 반복 측정이 아니며 캐시·부하 차이가 포함될 수 있다. 따라서 개선 비율을 보장하지 않는다. 곡 통계는 모든 경우 빨라지지 않았지만 라이브·월별 scope의 반복 검사 감소는 후속 최적화 근거다. 전체 아티스트·빈 데이터·보관/비공개·공동 출연·페이지 경계는 구현 시 fixture 회귀 검증이 추가로 필요하다.

## 산출물과 후속 작업

Git 제외 outputs/catalog-read-profile-2026-10-11/profile.json과 scope-comparison.json에 실제 데이터 측정·SQL·실행 계획을 보존했다. 진단 스크립트는 .tmp/profile_catalog_reads.py와 .tmp/compare_catalog_scope.py다.

후속: archive 후보 집합을 먼저 제한하는 SQL을 repository에 적용하고 기존 접근 범위·집계·pagination 계약을 유지하는 테스트를 수행한다. 실데이터 비교와 운영 배포 후 Server-Timing을 따로 검증한다. 이 조사만으로 유료 전환의 필요성을 판단하지 않는다.
