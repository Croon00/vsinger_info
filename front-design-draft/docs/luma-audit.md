# Luma 컴포넌트 검수

2026-09-15 · 프리셋 `a2vfHFI` · `reka-luma` · Neutral · Inter · Lucide

## 검수 방법

공식 shadcn-vue CLI `view`로 18종의 Luma 레지스트리를 읽어 로컬 UI 파일 135개와 대조했다. import 경로와 공백을 정규화해 비교했으며, 컴포넌트 내부와 앱 CSS의 덮어쓰기를 함께 확인했다. CLI가 `--dry-run`과 `--diff`를 아직 지원하지 않아 읽기 전용 `view`로 대체했다. 레지스트리 원본은 `luma-registry-audit.json`에 보관한다.

대상: Avatar, Button, Toggle, ToggleGroup, Card, Tabs, Calendar, Dialog, Drawer, InputGroup, Sidebar, Badge, Empty, Field, Select, Skeleton, Alert, Separator.

## 수정한 항목

| 항목 | 발견 사항 | 반영 |
| --- | --- | --- |
| 아티스트 이미지 | 화면마다 Avatar 또는 일반 img로 표시 | 공통 `ArtistAvatar`로 통일. 사용자 요청에 따라 1:1 비율과 `--radius-xl`(현재 14px) 사용. 이미지·fallback·테두리 모두 동일 반경 |
| 필터 ToggleGroup | 기본 orientation이 없어서 양끝 라운딩·경계 CSS 조건이 적용되지 않음 | 기본 horizontal 지정. Luma의 24px 끝 라운딩 복구 |
| 앨범 선택 | 직접 만든 button과 검은 outline으로 선택 표시 | ToggleGroup/ToggleGroupItem outline 사용. PC 세로, 모바일 가로 방향과 키보드 선택 지원 |
| 공연 항목 | 별도 테두리·배경·반경 정의 | Button outline으로 구성하고 내부 정보 배치만 조정 |
| 세트리스트 패널 | 별도 패널 스타일 | Card의 Header/Title/Description/Content/Footer 조합 사용 |
| 캘린더 | Heading·HeadCell·날짜 글자 크기를 앱 CSS로 덮어씀 | 해당 덮어쓰기 제거. 일정 셀 높이와 표식 배치는 유지 |
| 모바일 독 | 기본 버튼 글자를 9px로 축소 | 버튼의 기본 글자 크기로 복귀 |
| 현재 재생 곡 | `.setlist-songmis-playing` 오타로 선택 배경 누락 | `.setlist-song.is-playing`으로 수정 |

홈, 탐색, 상세, 통합검색의 아티스트 결과와 세트리스트 결과, 캘린더 날짜 목록, 공연 팝업에서 공통 이미지를 사용한다. 원본 이미지 파일과 기존 object-position은 변경하지 않았다.

## 유지한 차이와 적용 범위

- Luma의 기본 버튼·카드·입력·탭·모달 모양은 유지한다. 아티스트 이미지의 둥근 사각형은 이번 사용자 요청에 따른 명시적 예외이며, 일반 Avatar 원본을 바꾸지 않았다.
- 카드 내용의 날짜·곡명·아티스트명 등 정보 위계와 화면별 그리드·간격은 앱 레이아웃으로 유지한다. 콘텐츠 전체를 공식 데모 화면과 동일하게 만드는 검수는 아니다.
- 기존 `Calendar.vue`, `SidebarMenuSkeleton.vue`, `SidebarProvider.vue`의 템플릿 문자열 구문 보정은 유지한다. CLI view 결과와 차이는 있으나 스타일 변경은 아니다.
- `SelectContent`의 `cn-menu-target` 차이는 초기 CLI 변환 결과이며 현재 preset의 default/subtle 메뉴 설정을 유지한다.
- 이전 수정의 CalendarCellTrigger 선택 색상 우선순위 보정은 유지한다. Luma ghost 버튼의 다크 hover가 선택 대비를 덮어쓰는 문제를 해결하기 위한 것으로, 색상은 기존 primary 토큰이다.
- 새로운 컴포넌트 테마 적용이나 전체 UI 덮어쓰기를 수행하지 않았다.

## 확인

- Vue TypeScript 검사 및 Vite 빌드 성공.
- PC·모바일 E2E 14개 시나리오의 성공 출력을 확인했다. 앨범 선택 시 곡 목록과 선택 상태가 일치하는 검증을 추가했다.
- 재실행에서 첫 방문의 Service Worker 등록 전후 문서를 오갈 때 Chrome 뒤로가기가 문서 재로드로 처리되어 포커스/날짜 검증 2개가 실패한 실행이 있었다. 네트워크 trace에서 document 재요청을 확인했다. E2E는 Worker 활성화 후 새 문서에서 시나리오를 시작하도록 준비 단계를 명시했다. 최초 Worker 등록 중의 브라우저 히스토리 동작까지 보장하는 테스트는 아니다.
- PC 라이트·모바일 다크에서 탐색, 이미지 실패, 공연 목록·팝업, 검색을 확인했다. 이미지와 fallback의 실측 비율은 1:1, 반경은 14px이다.
- 필터의 실제 orientation은 horizontal이고 첫 항목의 왼쪽 위 반경은 Luma의 24px로 확인했다.
- 320·390·1440px에서 앨범 선택·캘린더·라이브 뷰어의 가로 넘침이 없었다. `luma-*-viewer.png`는 플레이어 테스트 더블로 세트리스트 패널만 검토한 캡처이므로 영상 영역은 비어 있다.
- YouTube 실제 영상 재생은 이번 검수 범위에 포함하지 않았다.

공식 기준: [Avatar](https://shadcn-vue.com/docs/components/avatar), [ToggleGroup](https://shadcn-vue.com/docs/components/toggle-group), [Card](https://shadcn-vue.com/docs/components/card), [Tabs](https://shadcn-vue.com/docs/components/tabs), [InputGroup](https://shadcn-vue.com/docs/components/input-group).
