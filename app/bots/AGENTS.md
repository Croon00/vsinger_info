# Discord Bot 영역 작업 지침

이 문서는 `app/bots/` 아래에서 작업할 때 루트 `AGENTS.md`에 추가로 적용된다. Discord 봇은 X 원문 URL 전송 전용이다.

## 허용 책임

- Discord client lifecycle
- 준비 상태 확인
- 기존 route의 channel 조회
- 전달받은 X `source_url` 한 줄 전송과 message ID 반환

slash command, interaction, command tree, 관리자 기능, route CRUD, 수동 테스트·재전송, 아티스트·YouTube·Spotify·노래방·가사·Google 기능을 추가하지 않는다. 설정 관리는 향후 admin-web에서 담당한다.

## 경계와 안전성

- 봇은 SQL을 실행하지 않는다. delivery claim·재시도·기록은 service/repository가 담당한다.
- 원문 본문이나 분류 label을 메시지에 덧붙이지 않는다.
- offline이면 service가 delivery를 claim하지 않으며 봇이 임의로 상태를 바꾸지 않는다.
- channel 누락과 Discord 오류는 예외로 반환해 durable sender가 재시도 여부를 결정하게 한다.
- 테스트에서 실제 Discord에 연결하거나 전송하지 않는다.
