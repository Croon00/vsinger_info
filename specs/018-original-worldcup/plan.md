# 오리지널 곡 월드컵 설계

- 로직: `web/src/lib/worldcup.ts` 순수 함수(`toCandidates`, `drawSongs`, `seed`, `start`, `choose`, `undo`, `progress`, `ranking`, `save`/`load`). 상태는 직렬화 가능한 객체이며 되돌리기 기록은 300개로 제한한다.
- 화면: `web/src/pages/WorldcupPage.vue`(설정 → 대결 → 결과). 아티스트 선택지는 곡 탐색과 같이 승인된 그룹 멤버를 그룹 하나로 묶는다. 소속사 목록은 아티스트 목록에서 만든다.
- 메뉴: `/worldcup` 라우트와 주 메뉴 "월드컵"(트로피 아이콘, 마우스 올림 시 금색·기울기·반짝임). 메뉴 선택 표시 규칙에 `/worldcup`을 추가했다.
- 2단계 후보(미구현): 전체 우승률 통계(투표 저장 API 필요), 결과 공유, 커버·아티스트 월드컵.
