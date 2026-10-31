# 아티스트 탐색 정렬

소속사 선택 오른쪽에 동일한 Select 형태로 정렬 기준을 제공한다. 기본 미선택 상태는 기존 즐겨찾기 우선·영문 이름 순서를 유지한다. 정렬을 선택하면 즐겨찾기보다 해당 기준을 우선하며, 선택은 URL의 `sort=channel-created|subscribers|name`에 보존된다. 소속사 필터와 이름 검색 결과에 같은 정렬을 적용한다.

- 채널 생성일: `youtube_channel_created_at`이 빠른 순서이며 미확인은 마지막이다. 사용자 요청에 따라 데뷔 순서를 대체하며, 실제 데뷔일 필드는 변경하지 않는다.
- 구독자 순서: 공식 소유 채널의 공개 구독자 수가 많은 순서. 0명은 정상 수치이며 비공개·미확인은 마지막이다. 동률은 이름 순서다.
- 가나다 순: 한국어 표시 이름(`display_name`)을 우선하고 없으면 원어 이름으로 한국어 locale 정렬한다. 숫자는 자연수 순서로 비교하고 동률은 아티스트 ID 순서다.

## 저장 및 조회

정상 조회 `/api/artists`, `/api/artists/{id}`에 nullable 필드 `debut_date`, `youtube_subscriber_count`, `youtube_channel_created_at`, `youtube_statistics_updated_at`을 추가했다. 신규 DB의 기존 `artists.debut_date`와 `collection_states.provider_state.youtube_channel_statistics`를 읽으며 조회 시 provider를 호출하지 않는다. 대표 채널은 현재 owner 관계 중 `position`, 관계 ID가 빠른 YouTube 계정이다. 여러 채널의 구독자 수를 합산하지 않는다.

채널 통계 namespace는 `channel_id`, `created_at`, `subscriber_count`, `subscribers_hidden`, `captured_at`을 저장한다. 공개 API의 구독자 수는 YouTube가 공개하는 반올림 값이며 정확한 실시간 수치나 과거 증가 추이는 제공하지 않는다. 개설일과 데뷔일은 독립적인 필드다.

## 갱신

```powershell
.venv\Scripts\python.exe scripts/refresh_youtube_channel_statistics.py
```

신규 DB에서 표시 중인 아티스트가 소유하고 수집이 활성화된 공식 YouTube 계정만 조회한다. 채널 ID를 중복 제거해 최대 50개씩 `channels.list(part=snippet,statistics)`로 요청하며 2초 간격을 둔다. 통계 응답은 Pydantic으로 검증하고 비공개 구독자는 null로 저장한다. 기존 collection state·lease·poll cursor·데뷔일을 덮어쓰지 않으며 영상 수집이나 외부 전송을 시작하지 않는다. 키·DB URL을 출력하지 않는다.

정상 `youtube_poll`도 기존 `channels.list` 요청의 part에 snippet·statistics를 포함해 응답을 검증하고 동일 namespace를 갱신한다. 채널 요청을 추가하지 않으며 별도의 주기 실행은 만들지 않는다. 운영 worker에 코드가 반영되어 실행될 때 기존 poll 주기로 갱신된다.

## 검증 — 2026-11-01

실데이터에서 95개 채널을 요청해 95개 응답을 저장했다. 실제 조회 API의 표시 중인 103명 중 구독자·개설일이 연결된 아티스트는 각각 89명, 데뷔일 등록은 58명이다. 나머지를 임의로 채우지 않는다.

프론트 빌드 통과, 정렬 단위 테스트 4개를 포함한 프론트 단위 테스트 52개 통과. PC·모바일 HTTP fixture 브라우저 테스트 2개에서 메뉴 위치·높이, 세 정렬, URL 복원, 소속사·검색 조합 및 가로 넘침을 검증했다. provider fixture로 묶음 조회·비공개·미확인·정상 poll의 추가 요청 없는 통계 확보를 검증한다. 폐기 가능한 로컬 PostgreSQL 바이너리가 없어 기존 YouTube 카탈로그 수집의 DB fixture 테스트 38개는 건너뛰었다. 실데이터 수집·조회 확인과 fixture 검증은 별개다.
