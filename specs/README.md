# UtaMowa 기능 스펙

2026-11-17 기존 문서를 바탕으로 도입했다. 번호는 문서 식별자이며 실행 우선순위는 사용자 요청과 roadmap을 따른다.

| 스펙 | 범위 | 현재 판정 |
| --- | --- | --- |
| [001-service-readiness](001-service-readiness/spec.md) | 신규 DB 수집·알림 서비스 운영 전환 | 과거 로컬 검증 기록 있음, 운영 확인 작업 남음 |
| [002-live-multiview](002-live-multiview/spec.md) | 생방송 검색·상태 확인·멀티뷰 운영 연결 | 기존 구현 있음, 배포·운영 확인 작업 남음 |
| [003-original-song-availability](003-original-song-availability/spec.md) | 분류 파일 누락 시 오리지널 목록 복구 | 로컬 수정·회귀 검증 완료, 배포·운영 확인 남음 |

각 디렉터리의 spec.md → plan.md → tasks.md 순서로 읽는다. 기존 검증의 건수는 기록 시점 값이다. 이번 도입의 검증 범위는 [스펙 작업 안내](../docs/spec-driven-development.md)에 기록한다.

다른 기능과 과거 기록의 연결은 [문서 지도](../docs/spec-driven-development.md), 전체 미완료 항목은 [roadmap](../docs/backend-roadmap.md)을 따른다. 새 기능은 별도 번호의 스펙을 만든다.
