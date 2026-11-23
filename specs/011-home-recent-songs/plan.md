# 홈 최근 곡 구현 설계

## 구현 경로

FR-001·003~005는 HomePage와 공통 `RecentSongs.vue`에서 구현한다. 기존 Button·ResourceState·SongVideoDialog 및 색상 토큰을 재사용한다. 가로 overflow·scroll-snap과 ResizeObserver로 수동 이동·버튼 상태를 구현한다. 화면 수치는 [화면 설계](../../web/docs/design-plan.md)에서 관리한다.

FR-002·006은 기존 `/api/explore/songs`의 `order=latest`, `limit=10`과 선택 `published_only=true`를 사용한다. FastAPI bool 입력 검증 후 repository에서 영상 ID 형식 및 `published_at <= CURRENT_TIMESTAMP`를 페이지 계산 전에 적용한다. 기본값 false는 기존 영상 미연결 음원 표시를 보존한다. utawaku와 함께 사용하면 422다. 기존 인증·분류·중복 제거를 유지하며 DB 변경은 없다.

## 검증

HTTP fixture로 옵션 전달·limit·잘못된 bool·utawaku 오용을 확인한다. 로컬 PostgreSQL fixture로 미확인·미래 게시 제외 후 최신 10개를 검증하고 원격 DB로 대체하지 않는다. TypeScript·Vite 빌드와 기존 unit 회귀를 실행한다. 실데이터는 API·프록시에서 읽기 전용으로 개수·중복·순서를 확인한다. PC·모바일 화면·수동 이동·전체 보기의 실행 여부는 tasks와 QA에 기록한다.
