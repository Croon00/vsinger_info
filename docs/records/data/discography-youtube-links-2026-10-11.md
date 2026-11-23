# 디스코그래피 YouTube 연결 적용 (2026-10-11)

현재 도구와 기준은 [디스코그래피 YouTube 연결](../../discography-youtube-links.md)을 따른다. 2026-11-23 현재 문서에서 날짜별 기록을 옮겼다. 수치와 상태는 기록 시점의 값이다.

사용자 요청으로 발매곡별 검증된 YouTube 링크를 연결했다.

```powershell
python scripts/link_discography_youtube.py --output outputs/discography-youtube-2026-10-11
python scripts/link_discography_youtube.py --apply --output outputs/discography-youtube-2026-10-11
```

## fixture 검증

2026-10-11: 매칭 fixture 테스트 25개 통과, 조회 DB fixture 13개는 로컬 PostgreSQL 부재로 skipped. 프론트 URL 매핑/디스코그래피 단위 테스트 22개 통과, vue-tsc 및 실제 모드 Vite 빌드 통과. HTTP fixture Playwright PC·모바일 2개 통과: 안전한 직접 영상 URL, 새 탭 속성, 미연결 Instrumental 버튼 없음, 화면 폭 내 배치, 검은 배경·흰 글씨·빨간 hover를 검증하고 화면을 캡처했다. 이는 fixture UI 검증이며 실데이터 적용 결과는 아래에 별도로 기록한다.

## 실데이터 적용

공식 owner 채널 76개, 업로드 목록 43,865개를 조회했다. 큰 채널은 이번 실행에서 `--max-pages 100`으로 상한을 늘려 전체 페이지를 확인했다. 총 3,242개 녹음 중 678개를 연결했다(receipt 6466: 화면의 イニミニまいご 1개, 6467: 466개, 6468: 211개). catalog_changes의 녹음 ID 678개와 실제 저장 링크 678개를 대조하고 최신 곡명·버전·길이·채널·공개 상태 조건으로 각각 재검증했으며 불일치 0개였다.

최종 미연결은 2,564개다. CSV와 가창 명의별 목록은 `outputs/discography-youtube-2026-10-11/unresolved.csv`·`unresolved.md`, 大神ミオ 대상 목록 37개는 `unresolved-mio.md`다. 공식 owner 채널과 검증 조건 기준의 미확정 목록이므로 플랫폼 전체에서 영상이 없다는 의미는 아니다. 사용자 URL을 받으면 녹음 ID와 버전을 기준으로 후속 검토한다.

실제 조회 로직의 앨범 2067은 イニミニまいご에 `https://www.youtube.com/watch?v=vG60szMQ1cE`를 반환하고 Instrumental에는 null을 반환했다. 링크 데이터는 운영 DB에 적용했으며 `youtube_url` 계약과 웹 버튼의 코드 배포는 (기록 당시) 아직 수행하지 않았다.
