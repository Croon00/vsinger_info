# schedule_music · 새 프론트

Vue + TypeScript + Vite, shadcn-vue Luma 기반 프론트입니다. 기본 실행은 새 Neon 카탈로그에 연결된 조회 전용 `/api/v2`를 사용합니다. 디자인 목업은 별도 모드로 유지합니다.

2026-09-19 디자인 초안 디렉터리에서 기본 `web` 디렉터리로 이동했습니다. 기존 관리 웹은 `../web.bak`에 보관합니다. 개발 서버 포트와 실제/mock 데이터 모드는 유지합니다.

성능 변경·측정 결과·필드/페이지 계약은 [조회 API v2](../docs/read-api-v2.md)에 있습니다. 백엔드 자동 reload가 반영되지 않아 새 경로가 404이면 API를 재시작합니다.

## 실제 API 연결

Node.js 22.12 이상 또는 24, npm을 사용합니다.

```powershell
npm install
if (-not (Test-Path .env.local)) { Copy-Item .env.example .env.local }
npm run dev
```

프론트: http://localhost:5174

`.env.local`의 `BACKEND_URL`을 실행 중인 FastAPI 주소로 설정합니다. 기본값은 `http://127.0.0.1:8000`입니다. Vite가 `/api/*`를 이 주소로 전달하므로 로컬 프론트의 CORS 설정 변경은 필요하지 않습니다. 백엔드 `API_KEY` 인증을 사용한다면 같은 값을 프론트의 **서버 전용** `BACKEND_API_KEY`로 설정합니다. `VITE_` 접두사로 키를 넣지 마세요. 프록시는 GET/HEAD만 전달합니다.

상위 프로젝트의 `.env.catalog`에 있는 `NEW_CATALOG_DATABASE_URL`이 사용자 조회 API의 DB 설정입니다. 기존 `.env`의 `DATABASE_URL`은 수집기·봇·기존 API용으로 유지합니다. 프론트에서 자동으로 읽거나 복사하지 않습니다. DB 주소는 HTTP API 주소로 사용할 수 없습니다.

백엔드가 실행되지 않았거나 인증에 실패하면 오류를 표시합니다. 목업으로 자동 대체하지 않습니다. 백엔드 서버·DB를 이 프론트 명령이 실행하지는 않습니다. 실제 데이터 검증 전 서버 실행 상태를 확인해야 합니다.

## 디자인 목업

```powershell
npm run dev:mock
```

목업: http://localhost:5175. MSW가 `/api/draft/*` 및 예시 가사에 응답합니다. 실제 모드의 저장 키는 `schedule-music-api:`, 목업은 `schedule-music-draft:`로 분리됩니다. 새 DB의 즐겨찾기는 `schedule-music-api:catalog-v1-favorites`를 사용하여 이전 DB의 ID와 분리합니다. 기존 테마·캘린더 설정은 유지합니다. 기존 목업 Service Worker가 남은 동일 출처에서 실제 모드로 바꾸면 해당 worker만 해제하고 한 번 새로고침합니다.

목업의 아티스트 이미지 출처는 [콘텐츠 출처](docs/content-sources.md)에 기록했습니다. 목업 공연·가격·가사는 예시 데이터이며 실제 모드에는 섞이지 않습니다. 실제 YouTube 영상은 두 모드 모두 외부 임베드로 재생합니다.

## 연결 범위

- 아티스트 목록·프로필·이미지·등록된 주요 링크, 데이터 기반 소속사 필터
- 아티스트별 라이브 6개씩 조회, 선택한 영상의 세트리스트·YouTube 재생과 시점 이동
- 서버에서 집계한 통계·월별 활동량을 통계 탭에서 별도 조회
- 곡명·원곡 아티스트 OR 검색과 50개씩 더 보기, 아티스트 별칭 검색
- 앨범 목록, 선택한 앨범 수록곡, 저장된 가사의 조회·출처·검토 상태
- 검토 완료된 오프라인/복합 공연의 캘린더와 상세

프로필·라이브·앨범·공연은 오류와 로딩을 분리했습니다. 새 DB에 저장된 한국어 이름과 생일을 표시합니다. 미등록 값을 임의 생성하지 않으며 앨범·가사도 외부 API 대신 새 DB에서 읽습니다. 상세 제한과 미구현 작업은 [백엔드 연결 TO-DO](../docs/backend-roadmap.md)에 정리했습니다.

## 검증

```powershell
npm test                  # API 변환 및 검색/날짜/통계 단위 테스트
npm run test:integration   # 실제 모드 + 현재 백엔드 계약을 재현한 HTTP 응답으로 PC/모바일 검증
npm run test:e2e           # 목업 모드의 PC/모바일 동작 검증
npm run build             # 실제 모드 TypeScript + 배포 빌드
npm run build:mock        # 디자인 목업 배포 빌드
```

브라우저 테스트는 설치된 Chrome을 사용합니다. 다른 위치는 `CHROME_PATH`로 지정합니다. `test:integration`은 5196번 테스트 프론트와 HTTP 응답 fixture를 사용하며 실제 DB를 호출하지 않습니다. 운영 API 호출 검증과 구분해야 합니다. 목업 테스트는 독립적인 5195번을 사용합니다.

실제 빌드의 `dist`는 정적 파일입니다. 운영 서버에서 `/api`를 실제 백엔드로 라우팅하고 SPA 경로를 `index.html`로 fallback해야 합니다. Vite의 서버 전용 API 키와 프록시는 정적 빌드에 포함되지 않습니다. `npm run preview`는 정적 배포 확인용이며 운영 API 프록시를 대신하지 않습니다. 배포는 수행하지 않았습니다.

화면별 현재 동작은 [화면 설계](docs/design-plan.md), 검증 범위·최근 결과는 [QA](docs/qa.md)를 따릅니다. 기존 `../web.bak`의 시각적 구현은 사용하지 않습니다.

## 폴더 구조

| 위치 | 역할 |
| --- | --- |
| src/api | 실제/mock API 선택, DTO 변환, 요청·캐시 |
| src/pages | 라우트별 화면 |
| src/components | 공통 화면 요소, ui 아래 생성된 shadcn 컴포넌트 |
| src/composables / src/lib | 리소스·환경설정 상태와 순수 함수 |
| src/mocks | MSW handler와 디자인 fixture |
| tests/unit / tests/e2e / tests/integration | 단위 / mock 화면 / 실제 계약 fixture |
| docs | 화면 설계, 검증, 목업 출처·측정 자료 |
| scripts | 점검·측정 보조 도구. 적용 환경은 QA 문서 확인 |
| public | 정적 자산과 mock worker |
| dist / test-results | 빌드·테스트 생성물. 소스가 아니며 Git 제외 |
| .agents/skills | 설치된 스킬. 프로젝트 문서 정리 대상에서 제외 |

백엔드의 구조·계약·후속 작업은 상위 docs에서 공통 관리합니다. 성능 원시 JSON과 당시 스크린샷은 검증 근거로 보존하되 최신 화면의 사양으로 사용하지 않습니다.
