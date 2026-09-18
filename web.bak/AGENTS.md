# Vue Frontend 영역 작업 지침

이 문서는 `web.bak/` 아래에서 작업할 때 루트 `AGENTS.md`에 추가로 적용된다.
프론트는 Vue 3 기반 관리자 웹이며 FastAPI를 유일한 데이터·권한 기준으로 사용한다.

## 기본 스택

- Vue 3 Composition API와 `<script setup>`
- TypeScript strict mode
- Vite
- Vue Router
- Pinia
- 서버 데이터 캐시는 TanStack Query for Vue 사용을 우선 고려
- Nuxt UI의 Vue 3 + Vite 플러그인
- Inspira UI는 제한적인 장식 요소에만 사용

## 디자인 시스템

- 기본 컴포넌트와 디자인 토큰은 Nuxt UI를 사용한다.
- Nuxt 프레임워크는 도입하지 않고 Vue 3 + Vite용 Nuxt UI 플러그인을 사용한다.
- 테이블, 폼, 모달, 드롭다운, 사이드바, 탐색 UI를 직접 재구현하지 않는다.
- 프로젝트 고유 UI만 `components/`에 구현한다.
- Inspira UI는 로그인, 빈 상태, 대시보드 헤더 등 장식 영역에만 사용한다.
- 데이터 테이블과 설정 화면에는 지속적이거나 시선을 방해하는 애니메이션을 사용하지 않는다.
- Inspira UI 컴포넌트는 Nuxt UI의 색상·간격·radius 토큰에 맞춘다.
- PrimeVue, Vuetify, shadcn-vue 같은 추가 범용 디자인 시스템을 함께 사용하지 않는다.

## 디렉터리 책임

```text
web.bak/src/
├─ api/          FastAPI client, DTO, query functions
├─ components/   여러 화면에서 재사용하는 UI
├─ pages/        route 단위 화면
├─ router/       route 정의와 접근 제어
└─ stores/       세션 및 전역 UI 상태
```

화면 전용 컴포넌트는 해당 page 근처에 두고, 실제로 재사용될 때만 `components/`로 이동한다.

## API와 상태

- 브라우저에서 PostgreSQL, Discord, X, OpenAI API에 직접 접근하지 않는다.
- 모든 업무 데이터는 FastAPI를 통해 읽고 변경한다.
- API base URL은 환경 변수로 관리하며 secret을 `VITE_` 환경 변수에 넣지 않는다.
- API 응답 타입을 `any`로 두지 않는다.
- 로딩, 빈 목록, 오류, 권한 없음 상태를 각 화면에서 명시적으로 표시한다.
- 서버 데이터를 Pinia에 복제해 두지 않는다. 서버 캐시와 UI 상태를 분리한다.

## Pinia 상태 관리

- Pinia는 여러 route와 component가 공유하는 클라이언트 상태에 사용한다.
- store는 Composition API 형태의 setup store와 명시적인 반환 타입을 사용한다.
- state 변경은 store action을 통해 수행하고 컴포넌트에서 임의로 복잡한 상태 전이를 만들지 않는다.
- getter에는 파생 상태만 두고 네트워크 호출이나 다른 부작용을 넣지 않는다.
- store 사이의 순환 의존성을 만들지 않는다.

Pinia에 저장할 상태:

- 로그인한 Discord 사용자 기본 정보
- 현재 선택된 guild ID
- 사이드바 열림·접힘 상태
- theme와 locale 같은 사용자 UI 설정
- 화면 사이에서 유지해야 하는 필터·정렬 선택

Pinia에 저장하지 않을 상태:

- bearer token, OAuth token, client secret
- `HttpOnly` session cookie의 내용
- API에서 받은 전체 artist, source item, route, event 목록
- 컴포넌트 하나에서만 사용하는 modal·input 임시 상태
- TanStack Query가 이미 관리하는 loading, error, cache 데이터

- 새로고침 후 유지할 값은 allowlist 기반 persistence만 사용한다.
- guild가 변경되면 guild 종속 Pinia 상태와 TanStack Query cache를 함께 초기화한다.
- logout 시 모든 사용자·guild 종속 store를 `$reset()`한다.

## 인증과 보안

- Discord 로그인 세션은 서버가 설정한 HttpOnly 쿠키를 사용한다.
- 프론트 route guard는 UX 보조 수단일 뿐이며 실제 권한 판정은 FastAPI가 수행한다.
- HTML로 받은 원문이나 LLM 출력을 `v-html`로 바로 렌더링하지 않는다.
- guild를 바꾸면 이전 guild의 query cache와 선택 상태가 섞이지 않게 한다.
- 삭제, 대량 재전송, 수동 수집은 확인 UI와 진행 상태를 제공한다.

## UX 원칙

- 모바일보다 데스크톱 관리자 화면을 우선하되 태블릿 폭까지 대응한다.
- 주요 화면은 대시보드, 아티스트·소스, Discord 라우트, 수집 글, 일정 순서로 구성한다.
- ID만 표시하지 말고 artist, guild, channel의 사람이 읽을 수 있는 이름을 함께 표시한다.
- 날짜는 API의 timezone 정보를 보존하고 사용자 timezone으로 명확히 표시한다.
- 자동 분류 결과와 사람이 수정한 결과를 구분한다.
- 성공 toast만 보여주지 말고 재전송 건수와 실패 사유를 화면 기록으로 남긴다.

## 품질 기준

- 새 컴포넌트는 props와 emits 타입을 명시한다.
- API client unit test, 핵심 store test, 주요 흐름 E2E test를 구분한다.
- formatter, linter, TypeScript typecheck가 통과해야 한다.
- 접근 가능한 label, keyboard focus, 충분한 색 대비를 유지한다.

## 빌드와 배포

- 개발 서버는 `npm run dev`로 실행한다.
- typecheck와 테스트를 통과한 뒤 `npm run build`로 production bundle을 만든다.
- Vite의 기본 출력 디렉터리인 `web.bak/dist/`를 정적 호스팅에 배포한다.
- `npm run preview`는 production build의 로컬 확인에만 사용하고 실제 production server로 사용하지 않는다.
- 배포 환경은 build 시점에 `VITE_API_BASE_URL`을 주입한다.
- `VITE_` 환경 변수는 브라우저 bundle에 포함되므로 공개 가능한 값만 저장한다.
- Vue Router history mode를 사용할 경우 모든 비정적 경로를 `/index.html`로 보내는 SPA fallback을 설정한다.
- CI 기본 순서는 `npm ci`, `npm run typecheck`, `npm run test`, `npm run build`로 한다.
