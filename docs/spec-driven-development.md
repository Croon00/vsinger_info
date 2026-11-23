# UtaMowa 스펙 기반 작업 안내

작성 2026-11-17 · 최종 확인 2026-11-23 · Specify CLI 1.4.1 · Codex skills · PowerShell

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
| docs 루트의 계약·구조 문서 | 현재 동작과 상세 계약 |
| docs/plans | 확정 계획과 설계 근거 |
| docs/records/backend, docs/records/data | 당시 백엔드 단계·운영 결과, 날짜별 데이터 변경·검증 |
| docs/backend-roadmap.md | 전체 미완료 작업과 기능 스펙 연결 |
| README.md | 실행법과 문서 진입점 |

기존 문서는 아래 지도에서 역할과 관련 스펙으로 연결한다. 향후 기능 변경 때 필요한 요구사항을 해당 스펙으로 추출하고 원본 계약·증거를 참조한다. 작성한 계획은 현재 코드·운영 상태를 대조한 후 실행 작업을 갱신한다.

## 기존 문서 지도

### 공통 구조와 계약

- [백엔드 구조](backend-architecture.md), [저장소 구조](repository-structure.md), [조회 API](read-api.md), [카탈로그 schema](catalog-schema.md), [공개 라이브 일정](live-site-monitor.md)은 plan 단계에서 현재 구조·계약 근거로 읽는다. 2026-09-21 [파일 정리 기록](records/backend/repository-cleanup-2026-09-21.md)은 당시 구조의 근거다.
- 기능별 계약 문서(곡 탐색·커버·세트리스트 후보·프로필 이미지·공유 채널 등)는 상단에 날짜별 변경·검증 기록(`records/backend/*-history.md` 등) 링크를 둔다. 과거 근거는 그 링크에서 찾는다.
- [후속 작업](backend-roadmap.md)은 specify 단계의 후보 목록이다. [DB 구조 계획](plans/db-renewal-plan.md), [곡 마스터 계획](plans/song-master-plan.md), [세트리스트 이전 계획](plans/setlist-migration-plan.md)은 해당 기능을 진행할 때 현 구현과 대조한다.
- [관리자 계획](records/backend/admin-web-plan.md)은 2026-11-23 삭제한 로컬 관리자 앱의 기록이며 후속 관리 도구 설계 때 참고한다. 현재 서비스 통합 범위는 constitution과 서비스 보완 계획을 따른다.

### 서비스 운영 전환

[001-service-readiness](../specs/001-service-readiness/spec.md)에서 요구사항·설계·남은 작업을 추적한다.

- 확정 요구와 설계 근거는 [통합 최종 계획](plans/backend-consolidation-plan.md), [서비스 보완 계획](plans/backend-service-readiness-plan.md)이다.
- 기존 단계 기록은 [조사](records/backend/backend-phase-1-baseline.md), [schema](records/backend/backend-phase-2-runtime-schema.md), [이전 도구](records/backend/backend-phase-3-runtime-migration.md), [runtime](records/backend/backend-phase-4-runtime.md), [전환 절차](records/backend/backend-phase-5-cutover.md)다.
- 로컬 보완 기록은 [X·Discord](records/backend/backend-service-step-1-runtime.md), [작업 실행기](records/backend/backend-service-step-2-jobs.md), [YouTube](records/backend/backend-service-step-3-youtube.md), [Spotify](records/backend/backend-service-step-4-spotify.md), [이전·설정](records/backend/backend-service-step-5-migration.md), [통합 검증](records/backend/backend-service-step-6-validation.md)이다.
- 실제 이전 근거는 [2026-09-23 전환 기록](records/backend/backend-cutover-2026-09-23.md), 조회 성능 근거는 [2026-10-11 측정](records/backend/backend-read-performance-2026-10-11.md)이다.

### 생방송 멀티뷰

[002-live-multiview](../specs/002-live-multiview/spec.md)에서 조회·주기·상태 전환·운영 연결을 추적한다. 상세 계약은 [조회 API](read-api.md#생방송-멀티뷰), 주기 변경 경위는 [조회 API 기록](records/backend/read-api-history.md)에서 확인한다.

### 음악·아티스트 기능 계약

2026-11-18 기존 작업을 다음 spec.md·plan.md·tasks.md로 정리했다. 과거 완료 기록은 원본 문서에 보존하고 날짜별 근거와 후속 확인을 연결한다.

- [아티스트 명의·공유 채널·탐색 정렬](../specs/003-artist-catalog/spec.md). 원본 자료는 해당 spec.md의 입력과 근거에서 확인한다.
- [프로필 이미지 저장·초기 이미지 작업](../specs/004-avatar-storage/spec.md). 원본 자료는 해당 spec.md의 입력과 근거에서 확인한다.
- [아티스트·공식 채널 등록과 자료 보완](../specs/005-catalog-registration/spec.md). 원본 자료는 해당 spec.md의 입력과 근거에서 확인한다.
- [Spotify 계정 탐색과 발매곡 YouTube 연결](../specs/006-discography-links/spec.md). 원본 자료는 해당 spec.md의 입력과 근거에서 확인한다.
- [YouTube 커버 분류·과거 수집·조회](../specs/007-youtube-covers/spec.md). 원본 자료는 해당 spec.md의 입력과 근거에서 확인한다.
- [세트리스트 이전·후보 선택·가창 정정과 복구](../specs/008-setlist-quality/spec.md). 원본 자료는 해당 spec.md의 입력과 근거에서 확인한다.
- [곡 탐색·세트리스트 검색과 조회 최적화](../specs/009-song-exploration/spec.md). 원본 자료는 해당 spec.md의 입력과 근거에서 확인한다.
- [오리지널 음원의 근거 기반 장르·분위기 필터](../specs/010-original-music-tags/spec.md). 원본 자료는 해당 spec.md의 입력과 근거에서 확인한다.

2026-11-21 이후 새 기능은 다음 스펙에서 시작했다.

- [홈 최근 오리지널·커버 곡](../specs/011-home-recent-songs/spec.md): 계약은 [곡 탐색](song-exploration.md)의 `published_only`.
- [YouTube 오리지널 일일 수집](../specs/012-youtube-original-daily/spec.md): 계약은 [오리지널 일일 수집](youtube-original-collection.md).
- [공유 채널 멤버별 라이브·커버](../specs/013-shared-member-catalog/spec.md): 계약은 [공유 YouTube 채널](shared-youtube-channels.md).
- [분류 파일 누락 시 오리지널 목록 복구](../specs/014-original-song-availability/spec.md): 계약은 [음악 분류](original-music-tags.md).

### 날짜별 조사·적용·검증 근거

다음 기록은 관련 작업의 research·검증 근거로 참조한다. 데이터 수치와 성공 여부는 해당 기록 시점에 적용한다.

- [요청 아티스트 2026-10-02](records/data/requested-vsingers-2026-10-02.md), [가창자 반영 2026-10-04](records/data/performance-artists-2026-10-04.md), [요청 채널 2026-11-14](records/data/requested-channels-2026-11-14.md)
- [누락 YouTube 채널 2026-09-18](records/data/youtube-channel-coverage-2026-09-18.md), [Mair](records/data/mair-2026-10-07.md), [Nakamachi Arale](records/data/nakamachi-arale-2026-10-07.md), [Nekothe](records/data/nekothe-registration-2026-11-01.md), [Kurokumo](records/data/kurokumo-2026-11-07.md), [ReAcT 자료](records/data/react-collection-2026-11-07.md), [ReAcT 멤버](records/data/react-members-2026-11-07.md)
- [라이브 5850 정정](records/data/live-5850-correction-2026-10-07.md), [세트리스트 정리](records/data/setlist-cleanup-2026-10-10.md), [규칙 갱신](records/data/setlist-refresh-2026-10-30.md), [모델 복구](records/data/setlist-model-recovery-2026-10-31.md)
- [요청 채널 2026-11-17](records/data/requested-channels-2026-11-17.md), [규칙만으로 세트리스트 복구 2026-11-21](records/data/setlist-rules-recovery-2026-11-21.md), [공유 멤버 보완 2026-11-22](records/data/shared-members-2026-11-22.md), [오리지널 누락곡 보완 2026-11-22](records/data/youtube-original-backfill-2026-11-22.md)
- [전환 시기 복구](records/backend/youtube-cutover-recovery-2026-10-09.md), [수집 runtime 조사](records/backend/youtube-runtime-audit-2026-10-11.md), [커버 조사](records/data/youtube-cover-audit-2026-11-01.md)

web/docs와 scripts/README.md 등 영역 문서는 해당 영역 AGENTS.md와 함께 읽는다. 실행 도구의 실제 DB 변경·외부 호출 범위를 확인한 뒤 사용한다.

## 도입·검증 기록

2026-11-17 도입, 2026-11-18 기존 작업 이관, 2026-11-23 문서 재배치의 검증 결과는 [스펙 기반 작업 기록](records/backend/spec-kit-adoption-2026-11-17.md)에 있다.
