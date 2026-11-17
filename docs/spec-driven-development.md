# UtaMowa 스펙 기반 작업 안내

작성 2026-11-17 · Specify CLI 1.4.1 · Codex skills · PowerShell

## 시작하기

스펙·설계·작업 목록·점검·분석 결과는 한국어로 작성한다. 인수 시나리오는 전제·동작·기대 결과로 읽는다. 파일명·명령어·API 경로·코드 식별자와 추적 ID는 도구에서 사용하는 표기를 따른다.

프로젝트 공통 원칙은 .specify/memory/constitution.md, 기능 목록은 specs/README.md에서 읽는다. Codex를 이 저장소에서 새로 열면 .agents/skills의 설치된 스킬을 사용할 수 있다. 기능별 문서는 spec.md → plan.md → tasks.md 순서로 진행한다.

| 명령 | 입력과 작업 | 주요 문서 |
| --- | --- | --- |
| `$speckit-constitution` | AGENTS.md와 확정 결정을 공통 원칙에 반영 | .specify/memory/constitution.md |
| `$speckit-specify` | 사용자 요구와 기존 계약에서 시나리오·범위·완료 조건 작성 | specs/<번호-기능>/spec.md |
| `$speckit-clarify` | 해당 스펙의 불명확한 요구사항 확인 | spec.md |
| `$speckit-plan` | 구현 경로·기술·데이터·계약·검증 설계 | plan.md와 필요한 설계 문서 |
| `$speckit-checklist` | 요구사항 품질 점검 항목 작성 | checklists/ |
| `$speckit-tasks` | 요구사항·설계에서 실행 작업 추출 | tasks.md |
| `$speckit-analyze` | 원칙·요구사항·설계·작업의 누락·충돌 점검 | 분석 결과 |
| `$speckit-implement` | 현재 기능의 작업 목록 실행·검증 | 코드와 tasks.md |
| `$speckit-converge` | 스펙 대비 구현을 대조하고 남은 작업 추가 | tasks.md |

예를 들어 새 요구는 `$speckit-specify 저장된 곡 통계에 서버 페이지와 정렬을 제공한다`로 시작한다. 이후 clarify, plan, tasks, analyze, implement를 실행한다. 기존 기능을 계속할 때는 대상 스펙 경로를 명시한다.

## 기존 스펙 선택

현재 CLI는 기능 디렉터리를 .specify/feature.json에 기억한다. PowerShell에서는 환경변수로 기존 스펙을 지정할 수 있다.

```powershell
$env:SPECIFY_FEATURE_DIRECTORY = 'specs/002-live-multiview'
.\.specify\scripts\powershell\check-prerequisites.ps1 -Json -RequireSpec -RequireTasks -IncludeTasks
```

이후 Codex에 `specs/002-live-multiview를 대상으로 $speckit-analyze를 실행해줘`처럼 요청한다. 새 세션에서도 대상 경로를 명시하면 작업 범위를 확인하기 쉽다. 다른 기능을 작업할 때 환경변수를 해당 경로로 바꾼다.

## 문서의 관리 위치

| 위치 | 관리 내용 |
| --- | --- |
| AGENTS.md 및 영역별 AGENTS.md | 에이전트 작업 지침 |
| .specify/memory/constitution.md | 공통 개발 원칙과 확정 서비스 경계 |
| specs/<번호-기능>/spec.md | 사용자 요구·범위·완료 조건 |
| specs/<번호-기능>/plan.md | 변경 설계·영향 코드·검증 방법 |
| specs/<번호-기능>/tasks.md | 요구사항별 실행 작업과 상태 |
| docs의 계약·구조 문서 | 현재 동작과 상세 계약 |
| docs의 날짜별 기록 | 당시 데이터 변경·검증·운영 결과 |
| docs/backend-roadmap.md | 전체 미완료 작업과 기능 스펙 연결 |
| README.md | 실행법과 문서 진입점 |

기존 문서는 아래 지도에서 역할과 관련 스펙으로 연결한다. 향후 기능 변경 때 필요한 요구사항을 해당 스펙으로 추출하고 원본 계약·증거를 참조한다. 작성한 계획은 현재 코드·운영 상태를 대조한 후 실행 작업을 갱신한다.

## 기존 문서 지도

### 공통 구조와 계약

- [백엔드 구조](backend-architecture.md), [저장소 구조](repository-structure.md), [조회 API](read-api-v2.md), [카탈로그 schema](catalog-schema.md)는 plan 단계에서 현재 구조·계약 근거로 읽는다.
- [후속 작업](backend-roadmap.md)은 specify 단계의 후보 목록이다. [DB 구조 계획](db-renewal-plan.md), [곡 마스터 계획](song-master-plan.md), [세트리스트 이전 계획](setlist-migration-plan.md)은 해당 기능을 진행할 때 현 구현과 대조한다.
- [관리자 계획](admin-web-plan.md)은 후속 관리 기능의 자료다. 현재 서비스 통합 범위는 constitution과 서비스 보완 계획을 따른다.

### 서비스 운영 전환

[001-service-readiness](../specs/001-service-readiness/spec.md)에서 요구사항·설계·남은 작업을 추적한다.

- 확정 요구와 설계 근거는 [통합 최종 계획](backend-consolidation-plan.md), [서비스 보완 계획](backend-service-readiness-plan.md)이다.
- 기존 단계 기록은 [조사](backend-phase-1-baseline.md), [schema](backend-phase-2-runtime-schema.md), [이전 도구](backend-phase-3-runtime-migration.md), [runtime](backend-phase-4-runtime.md), [전환 절차](backend-phase-5-cutover.md)다.
- 로컬 보완 기록은 [X·Discord](backend-service-step-1-runtime.md), [작업 실행기](backend-service-step-2-jobs.md), [YouTube](backend-service-step-3-youtube.md), [Spotify](backend-service-step-4-spotify.md), [이전·설정](backend-service-step-5-migration.md), [통합 검증](backend-service-step-6-validation.md)이다.
- 실제 이전 근거는 [2026-09-23 전환 기록](backend-cutover-2026-09-23.md), 조회 성능 근거는 [2026-10-11 측정](backend-read-performance-2026-10-11.md)이다.

### 생방송 멀티뷰

[002-live-multiview](../specs/002-live-multiview/spec.md)에서 조회·주기·상태 전환·운영 연결을 추적한다. 상세 계약은 [조회 API](read-api-v2.md), 과거 실행 기록은 [roadmap](backend-roadmap.md)에서 확인한다. Holodex의 최신 기준은 전체 검색 1시간·생방송 및 예정 시각 도달 방송 확인 3분이다. 과거 1분·30분 기록은 당시 이력이다.

### 음악·아티스트 기능 계약

다음 자료는 해당 기능의 specify·plan 입력으로 사용한다. 전체 미완료 목록에서 요청된 기능을 선택해 새 스펙으로 구체화한다.

- [아티스트 이름](artist-names.md), [아티스트 정렬](artist-sorting.md), [이미지 저장](avatar-storage.md), [공유 YouTube 채널](shared-youtube-channels.md)
- [곡 탐색](song-exploration.md), [오리지널 음악 분류](original-music-tags.md), [디스코그래피 YouTube 연결](discography-youtube-links.md)
- [Spotify 이름 일치 조사](spotify-exact-name-discovery.md), [YouTube 커버 수집](youtube-covers.md), [세트리스트 후보 선택](youtube-setlist-selection.md)
- [채널 수집 범위](youtube-channel-coverage.md), [세트리스트 이전 결과](setlist-migration-report.md)

### 날짜별 조사·적용·검증 근거

다음 기록은 관련 작업의 research·검증 근거로 참조한다. 데이터 수치와 성공 여부는 해당 기록 시점에 적용한다.

- [요청 아티스트 2026-10-02](requested-vsingers-2026-10-02.md), [가창자 반영 2026-10-04](performance-artists-2026-10-04.md), [요청 채널 2026-11-14](requested-channels-2026-11-14.md)
- [Mair](mair-2026-10-07.md), [Nakamachi Arale](nakamachi-arale-2026-10-07.md), [Nekothe](nekothe-registration-2026-11-01.md), [Kurokumo](kurokumo-2026-11-07.md), [ReAcT 자료](react-collection-2026-11-07.md), [ReAcT 멤버](react-members-2026-11-07.md)
- [라이브 5850 정정](live-5850-correction-2026-10-07.md), [세트리스트 정리](setlist-cleanup-2026-10-10.md), [규칙 갱신](setlist-refresh-2026-10-30.md), [모델 복구](setlist-model-recovery-2026-10-31.md)
- [전환 시기 복구](youtube-cutover-recovery-2026-10-09.md), [수집 runtime 조사](youtube-runtime-audit-2026-10-11.md), [커버 조사](youtube-cover-audit-2026-11-01.md)

web/docs와 scripts/README.md 등 영역 문서는 해당 영역 AGENTS.md와 함께 읽는다. 실행 도구의 실제 DB 변경·외부 호출 범위를 확인한 뒤 사용한다.

## 도입 검증

2026-11-17 검증 결과는 다음과 같다.

- Specify CLI 1.4.1의 Codex 스킬 9개와 PowerShell 스크립트·템플릿·workflow 설치를 확인했다.
- 두 기능에 check-prerequisites.ps1 -RequireSpec -RequireTasks -IncludeTasks를 실행해 spec.md·plan.md·tasks.md 인식과 종료 코드 0을 확인했다.
- docs/의 모든 Markdown 문서가 위 지도에서 연결됨을 확인했다. README·AGENTS·constitution·신규 안내·specs의 상대 링크와 UTF-8 문자를 검사했다.
- roadmap의 병합 충돌 표시를 제거하고 양쪽 기록을 2026-10-03 이력과 2026-10-04 후속 기록으로 연결했다. git diff --check를 실행했다.

이번 검증 범위는 문서·설치 구조다. 애플리케이션 테스트·실제 provider·운영 배포 확인은 각 기능의 미완료 작업으로 추적한다.
