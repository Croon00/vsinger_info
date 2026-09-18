# 기존 관리 웹

Vue 3 + TypeScript + Vite 기반의 기존 관리 프론트다. Pinia, TanStack Query for Vue, Nuxt UI를 사용한다. 새 사용자 조회 화면은 [front-design-draft](../front-design-draft/README.md)에서 별도로 개발한다. 기존 웹은 폐기되지 않았으며 관리·수집 API와의 호환성을 유지한다.

## 실행

루트에서 백엔드를 실행한 뒤 이 디렉터리에서 실행한다.

```powershell
npm install
npm run dev
```

개발 서버는 5173번이며 `vite.config.ts`가 `/api-proxy` 요청을 `http://127.0.0.1:8000`으로 전달한다. 브라우저가 PostgreSQL·외부 서비스 인증정보에 직접 접근하지 않는다.

## 검증과 빌드

```powershell
npm run typecheck
npm test
npm run test:e2e
npm run build
npm run preview
```

실제 스크립트는 `package.json`을 따른다. 빌드 결과 `dist/`는 생성물이며 소스와 분리한다. preview는 로컬 빌드 확인용이다. 작업 규칙은 [AGENTS.md](AGENTS.md), API 구조는 [백엔드 문서](../docs/backend-architecture.md)를 따른다.

이 README 정리는 실행 설정과 의존성만 확인했으며 기존 화면의 시각 구현을 새 프론트 설계에 사용하지 않았다.
