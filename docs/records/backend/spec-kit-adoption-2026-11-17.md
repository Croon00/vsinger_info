# 스펙 기반 작업 도입·이관·문서 재배치 기록

현재 작업 안내는 [스펙 기반 작업 안내](../../spec-driven-development.md)를 따른다. 2026-11-23 안내 문서 끝의 검증 절을 원문 그대로 옮겼다. 수치와 상태는 각 기록 시점의 값이다.

## 도입 검증 (2026-11-17)

2026-11-17 검증 결과는 다음과 같다.

- Specify CLI 1.4.1의 Codex 스킬 9개와 PowerShell 스크립트·템플릿·workflow 설치를 확인했다.
- 두 기능에 check-prerequisites.ps1 -RequireSpec -RequireTasks -IncludeTasks를 실행해 spec.md·plan.md·tasks.md 인식과 종료 코드 0을 확인했다.
- docs/의 모든 Markdown 문서가 위 지도에서 연결됨을 확인했다. README·AGENTS·constitution·신규 안내·specs의 상대 링크와 UTF-8 문자를 검사했다.
- roadmap의 병합 충돌 표시를 제거하고 양쪽 기록을 2026-10-03 이력과 2026-10-04 후속 기록으로 연결했다. git diff --check를 실행했다.

이번 검증 범위는 문서·설치 구조다. 애플리케이션 테스트·실제 provider·운영 배포 확인은 각 기능의 미완료 작업으로 추적한다.

## 기존 작업 이관 검증 (2026-11-18)

003~010의 8개 기능에 spec.md·plan.md·tasks.md 24개를 작성하고 기능 목록·문서 지도·roadmap에 연결했다. 분류 단위는 기존 계약과 날짜별 작업의 관련 범위로 정했다. 과거 완료 기록은 원본 날짜를 유지했으며, fixture·실데이터·배포 상태를 구분했다.

- Windows PowerShell 환경에서 8개 디렉터리 각각에 check-prerequisites.ps1 -Json -RequireSpec -RequireTasks -IncludeTasks를 실행해 종료 코드 0을 확인했다.
- 신규 문서 24개와 연결 문서 3개의 UTF-8 문자·상대 링크 대상, 신규 문서의 명시적 코드 경로와 US/FR/SC 식별자를 검사해 오류 0건을 확인했다. git diff --check를 통과했다.
- 애플리케이션 테스트·DB 조회 및 변경·실제 provider 호출·배포 확인은 이번 문서 이관에서 실행하지 않았다. Git 제외 보고서의 존재·내용은 재검증하지 않았다.
- requested-vsingers-2026-10-02.md에 남은 병합 충돌 표시와 상태 불일치는 005의 T003에서 추적한다. 세트리스트의 10월 초 상태는 10월 말 복구 기록과 대조할 후속 작업으로 008에 연결했다.

## 문서 재배치 (2026-11-23)

- docs 문서 36개를 `docs/plans/`(5), `docs/records/backend/`(17), `docs/records/data/`(14)로 옮기고 저장소 전체 Markdown 상대 링크를 갱신했다. 파일명은 유지했다.
- 기존 `repository-structure.md`는 `records/backend/repository-cleanup-2026-09-21.md`로 보존하고 현재 구조 문서를 새로 작성했다. README의 공개 라이브 일정 설명을 `live-site-monitor.md`로 분리했다.
- 운영 경로와 연결되지 않은 `web.bak/`, `admin-web/`, `app/admin/`, 관리자 전용 스크립트·테스트, `schemas/import/v1/`을 삭제했다.
- 2차: `read-api-v2.md`를 `read-api.md`로 바꾸고, 조회 API·곡 탐색·프로필 이미지·세트리스트 후보 비교·공유 채널 문서의 날짜별 검증·결정 문단을 `docs/records/backend/*-history.md`(HONK THE HORN·NUROJUNK MV 등록은 `records/data/duo-original-mv-2026-11-01.md`)로 옮겨 현재 계약만 남겼다. `catalog-schema.md`에서 삭제된 로컬 검수 구조를 `records/backend/catalog-local-review-2026-09-20.md`로 분리했다. specs 003~010은 요약·링크 구조라 유지했다.
- 검증 범위는 Markdown 상대 링크 검사, 삭제 대상 참조 검색, Python 테스트(설치되지 않은 의존성 모듈 제외)다. 실데이터·배포 확인은 하지 않았다.
