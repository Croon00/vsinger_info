# 디스코그래피 YouTube 연결 — 2026-10-11

사용자 요청으로 발매곡별 검증된 YouTube 링크를 연결한다. 기존 `recordings.official_video_id`와 `videos`를 사용하므로 schema 변경은 없다. `/api/albums/{id}`의 트랙은 `youtube_url`을 추가로 반환하며 보관/비공개/삭제/공개 여부 미확인 영상은 반환하지 않는다. 조회 API는 검색·수집을 실행하지 않는다.

웹은 링크가 있는 곡만 `YouTube로 보기` 버튼을 표시한다. 기존 shadcn Button의 youtube variant를 사용하며 검은 배경·흰 글씨·흰 테두리·알약 모양이다. hover와 focus-visible은 빨간색으로 채워지고 reduced-motion에서는 즉시 전환한다. 새 탭 링크는 noopener noreferrer를 사용한다. compact hero 미리보기는 기존 구성을 유지하고 앨범 상세에서 곡별 버튼을 제공한다.

## 명시적 조사 도구

```powershell
python scripts/link_discography_youtube.py --output outputs/discography-youtube-2026-10-11
python scripts/link_discography_youtube.py --apply --output outputs/discography-youtube-2026-10-11
```

기본 실행은 통합 DB 읽기와 외부 YouTube API 읽기, 로컬 보고서 작성만 수행한다. 로컬 proxy 문제가 있는 경우에만 `--direct-connect`를 사용한다. `--max-pages`는 채널당 업로드 목록 상한이며 기본 60, 허용 1–100이다. 같은 출력 디렉터리는 같은 조사 재개용 캐시다. 새 조사는 새 디렉터리를 사용한다.

등록된 가창자의 owner 채널을 API로 조회하고 곡명·버전·공개 상태·재생 길이를 확인한다. 제목은 완전한 필드/인용 제목 기준으로 비교하며 짧은 부분 문자열만으로 연결하지 않는다. 피처링 표기를 분리하는 경우 영상 제목에 같은 피처링 명의가 있어야 하며 뒤에 붙은 버전 표기는 유지한다. Instrumental, acoustic/piano, remix, short, live 버전 차이는 보류하고 방송·리액션·티저·XFD는 제외한다. 종료된 공식 MV/Original 최초 공개는 완료된 영상으로 인정하지만 진행 중/예약 영상과 일반 노래 방송은 제외한다. 여러 후보 중 유일한 full MV를 우선하고, 동일 우선순위 후보가 여러 개면 보류한다. 자동 배포 음원은 공식 owner 채널에 있는 경우만 인정한다. 별도 Topic/레이블 채널이나 명의 미등록 가창자는 이름만으로 소유권을 추정하지 않는다.

`--apply`는 catalog identity와 기존 recording version 및 owner 관계를 다시 확인한다. 기존 링크를 덮어쓰지 않으며 catalog_imports/catalog_changes에 영상 생성/공개 상태 갱신/녹음 연결의 전후 데이터를 보존한다. 자동 판정 근거는 채널 ID와 영상 ID로 기록한다. 중복 operation은 already_applied를 반환한다. 알림·LLM·Calendar·가사·새 방송 세트리스트 추출은 실행하지 않는다.

`unresolved.csv`는 recording_id, 실제 가창 명의, 곡명, 수록 발매, 보류 사유, 빈 youtube_url 열을 포함한다. `unresolved.md`는 가창 명의별 목록이다. 영상 부재를 증명하는 목록이 아니라 자동 연결을 확정하지 못한 목록이며 사용자 제공 URL의 후속 검토 입력으로 사용한다.

API 계약: [YouTube uploads playlist 목록](https://developers.google.com/youtube/v3/docs/playlistItems/list). 페이지당 최대 50개의 업로드 제목을 확인한 뒤 제목 후보만 videos API로 상세 확인한다.

## 검증

실데이터 적용: 공식 owner 채널 76개, 업로드 목록 43,865개를 조회했다. 큰 채널은 이번 실행에서 `--max-pages 100`으로 상한을 늘려 전체 페이지를 확인했다. 총 3,242개 녹음 중 678개를 연결했다(receipt 6466: 화면의 イニミニまいご 1개, 6467: 466개, 6468: 211개). catalog_changes의 녹음 ID 678개와 실제 저장 링크 678개를 대조하고 최신 곡명·버전·길이·채널·공개 상태 조건으로 각각 재검증했으며 불일치 0개였다.

최종 미연결은 2,564개다. CSV와 가창 명의별 목록은 `outputs/discography-youtube-2026-10-11/unresolved.csv`·`unresolved.md`, 大神ミオ 대상 목록 37개는 `unresolved-mio.md`다. 공식 owner 채널과 검증 조건 기준의 미확정 목록이므로 플랫폼 전체에서 영상이 없다는 의미는 아니다. 사용자 URL을 받으면 녹음 ID와 버전을 기준으로 후속 검토한다.

실제 조회 로직의 앨범 2067은 イニミニまいご에 `https://www.youtube.com/watch?v=vG60szMQ1cE`를 반환하고 Instrumental에는 null을 반환했다. 링크 데이터는 운영 DB에 적용했으며 `youtube_url` 계약과 웹 버튼의 코드 배포는 아직 수행하지 않았다.

2026-10-11: 매칭 fixture 테스트 25개 통과, 조회 DB fixture 13개는 로컬 PostgreSQL 부재로 skipped. 프론트 URL 매핑/디스코그래피 단위 테스트 22개 통과, vue-tsc 및 실제 모드 Vite 빌드 통과. HTTP fixture Playwright PC·모바일 2개 통과: 안전한 직접 영상 URL, 새 탭 속성, 미연결 Instrumental 버튼 없음, 화면 폭 내 배치, 검은 배경·흰 글씨·빨간 hover를 검증하고 화면을 캡처했다. 이는 fixture UI 검증이며 실데이터 적용 결과는 아래에 별도로 기록한다.
