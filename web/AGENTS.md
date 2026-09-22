# Web 작업 지침

새 사용자 조회 프론트다. 실행·폴더 안내는 [README](README.md), 현재 화면 기준은 [화면 설계](docs/design-plan.md)를 따른다.

## 범위

- 프론트 파일·의존성은 이 디렉터리에 둔다. 기존 ../web.bak의 화면·스타일·컴포넌트·레이아웃을 디자인 참고로 읽거나 재사용하지 않는다.
- 사용자 승인에 따라 실제 백엔드 연결과 조회 성능 개선을 적용했다. 기본 실행은 통합 `/api`, 디자인 목업은 명시적 mock 모드다.
- 실제 모드에서 미지원 데이터나 API 오류를 목업으로 대체하지 않는다. 미지원 기능은 [백엔드 후속 작업](../docs/backend-roadmap.md)에 기록한다.
- 백엔드 변경·실데이터 검증은 해당 요청 범위에서 수행한다. 조회 검증을 위해 DB 초기화·수집·번역·외부 전송을 시작하지 않는다.
- API 계약은 [조회 API](../docs/read-api-v2.md), 검증 범위는 [QA](docs/qa.md)에 유지한다.

## 스킬과 디자인

- .agents/skills/shadcn-vue/SKILL.md
- .agents/skills/transitions-dev/SKILL.md

겹치는 지침은 shadcn-vue 우선이다. 컴포넌트 구조·접근성·색상·폰트·반경·아이콘은 shadcn-vue, 호환되는 모션은 transitions-dev를 따른다. 별도 모달/탭 시스템이나 디자인 테마로 대체하지 않는다.

CLI의 --preset a2vfHFI로 생성한 components.json과 전역 CSS가 기준이다. 재초기화가 필요하면 프리셋을 CLI에 전달하고 수동 유사 CSS로 대신하지 않는다.

화면별 수치와 동작은 디자인 문서 한 곳에서 관리한다. 실제 한국어 표기가 없는 아티스트에게 이름을 임의 생성하지 않는다. 목업 출처와 합성 자료는 docs/content-sources.md에 구분해 보존하며 실제 데이터에 섞지 않는다. 티켓은 외부 링크만 지원하고 구매·응모를 자동화하지 않는다.
