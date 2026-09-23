# 카탈로그 관리자 웹

새 Neon 음악 카탈로그를 위한 로컬 검수·관리 도구다. Vue 3 + TypeScript + Vite와 shadcn-vue Luma preset `a2vfHFI`를 사용한다.

실행·사용법·API·검증·후속 작업은 [관리자 안내](../docs/admin-web-plan.md)를 기준으로 한다.

```powershell
npm ci
npm run build
cd ..
.\.venv\Scripts\python.exe scripts/run_admin.py
```

주소: http://127.0.0.1:8010

- `npm run dev`: 개발 화면 5176. 관리자 API 8010을 별도로 실행한다.
- `npm run build`: 타입 검사와 정적 빌드.
- `npm run test:e2e`: 임시 로컬 검수 DB로 Edge 브라우저 검증. 먼저 build를 실행하고 8010 포트를 비운다.
- `src/components/ui/`: CLI로 생성한 Luma 컴포넌트.
- `src/components/ResourceForm.vue`: 필드별 폼.
- `src/components/RelationPicker.vue`: 초안/기존 자료 연결 검색.
- `src/lib/api.ts`: 로컬 API 클라이언트와 표시 이름.

DB 비밀번호를 VITE 환경변수에 넣지 않는다. 초기 데이터는 검수함에서 승인·미리보기 후 명시적으로 반영해야 한다.
