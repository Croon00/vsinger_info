# 전체 디자인 점검 · 2026-09-16

기존 Luma / Neutral 프리셋을 유지하면서 홈, 탐색, 아티스트의 네 탭, 검색, 캘린더, 설정, 라이브 뷰어, 가사·공연 팝업을 점검했다.

## 수정

| 영역 | 확인한 문제 | 반영 |
| --- | --- | --- |
| 컴포넌트 | 세트리스트와 캘린더 일부 액션이 기본 HTML 버튼으로 구현됨 | 기존 shadcn Button의 ghost 변형으로 통일하고 포커스 피드백 적용 |
| 글자 계층 | 즐겨찾기 한국어 이름이 모바일 8px, PC 9px로 지나치게 작음 | 각각 10px / 11px로 조정. 검색 메타데이터·라이브 날짜·가사 안내도 가독성 보정 |
| 간격 | 섹션 간격 45px, 제목 아래 23px 등 화면별 편차 | 검색 섹션 PC 40px / 모바일 32px, 모바일 섹션 제목 아래 20px, 상세 프로필 간격 32px로 정리 |
| 설정 | 좁은 화면의 테마 버튼에서 아이콘과 글자가 밀집 | 480px 이하에서 아이콘 위·이름 아래로 배치 |
| 로딩 | 모든 화면에서 큰 정사각형 6개가 나타나 실제 콘텐츠와 불일치 | 홈·탐색은 실제 그리드 규칙 공유, 나머지는 작은 행 형태의 Skeleton 적용 |
| 라이브 카드 | 재생 표시가 마우스 호버에만 반응하고 내부 링크에 외부 링크 화살표 사용 | 키보드 포커스에서도 재생 표시. 잘못된 화살표 제거, 이미지 확대는 정밀 포인터에 한정 |
| 팝업 | 배경과 본문 애니메이션 속도가 다름 | Dialog 열기 250ms / 닫기 150ms, Drawer 400ms / 350ms로 배경과 본문 동기화. 드래그 동작은 유지 |
| 팝업 정보 | 추상적인 설명과 영문 닫기 레이블 | 가사는 아티스트명, 공연은 정보 종류를 표시하고 닫기 레이블을 한국어로 통일 |

홈의 중앙 정렬된 그리드와 모바일 마지막 행의 좌측 배치, 통계의 컴팩트한 행과 페이지 높이 유지 방식, 아이콘 전용 모바일 독은 유지했다. 사용하지 않는 topbar CSS는 제거했다.

## 검증

- 단위 테스트 13개, PC·모바일 E2E 28개 통과.
- 마지막 캘린더 버튼 변경 후 관련 E2E 2개 추가 확인.
- TypeScript 검사 및 프로덕션 빌드 통과.
- 320 / 390 / 900 / 1440px, 라이트·다크를 포함한 5개 환경 × 12개 화면에서 가로 넘침과 런타임 오류 점검.
- 키보드로 곡 선택, 라이브 카드 재생 표시, 팝업 포커스 복귀, 테마 전환, reduced-motion 동작 확인.

화면 재점검은 개발 서버 실행 후 `node scripts/design-audit.mjs`로 수행한다. 결과는 `test-results/design-audit/`에 저장한다. 모바일 앨범 선택의 의도된 가로 스크롤은 화면 넘침 판정에서 제외한다. 라이브 뷰어 캡처와 자동화 테스트는 YouTube 테스트 더블을 사용하며 이번 점검은 실제 외부 영상 재생의 재검증을 포함하지 않는다.

## 기준 문서

- [shadcn-vue Button](https://shadcn-vue.com/docs/components/button), [Dialog](https://shadcn-vue.com/docs/components/dialog), [Drawer](https://shadcn-vue.com/docs/components/drawer), [Skeleton](https://shadcn-vue.com/docs/components/skeleton)
- 프로젝트 `.agents/skills/shadcn-vue/SKILL.md`, `.agents/skills/transitions-dev/SKILL.md` — 겹치는 지침은 shadcn-vue 우선.
