# 아티스트 탐색 정렬

소속사 선택 오른쪽에 동일한 Select 형태로 정렬 기준을 제공한다. 기본은 가나다 순이며 즐겨찾기가 정렬 순서를 바꾸지 않는다. 선택은 URL의 `sort=channel-created|channel-recent|subscribers|subscribers-low|name`에 보존된다. 소속사 필터와 이름 검색 결과에 같은 정렬을 적용한다.

- 채널 생성 오래 된 순 / 채널 생성 최근 순: `youtube_channel_created_at`을 시간대로 보정한 시각으로 비교한다. 미확인은 양방향 모두 마지막이다. 실제 데뷔일 필드는 변경하지 않는다.
- 구독자 높은 순 / 구독자 낮은 순: 공식 소유 채널의 공개 구독자 수를 내림차순/오름차순으로 비교한다. 0명은 정상 수치이며 비공개·미확인은 양방향 모두 마지막이다. 동률은 이름 순서다.
- 가나다 순: 한국어 표시 이름(`display_name`)을 우선하고 없으면 원어 이름으로 한국어 locale 정렬한다. 숫자는 자연수 순서로 비교하고 동률은 아티스트 ID 순서다.

아티스트 카드 이름 오른쪽에는 구독자 수를 `12.1만`처럼 표시한다. 만 명 미만은 `9,999`, 1억 이상은 `1.2억`으로 표시하며 반올림해 수치를 올리지 않는다. 비공개·미확인은 `—`로 표시한다. 접근성 레이블과 툴팁은 API에 저장된 전체 숫자를 제공한다. 모바일에서는 이름과 구독자 수에 공간을 확보하도록 즐겨찾기 버튼을 한국어 이름 줄 오른쪽에 배치한다.

## 저장 및 조회

정상 조회 `/api/artists`, `/api/artists/{id}`에 nullable 필드 `debut_date`, `youtube_subscriber_count`, `youtube_channel_created_at`, `youtube_statistics_updated_at`을 추가했다. 신규 DB의 기존 `artists.debut_date`와 `collection_states.provider_state.youtube_channel_statistics`를 읽으며 조회 시 provider를 호출하지 않는다. 대표 채널은 현재 owner 관계 중 `position`, 관계 ID가 빠른 YouTube 계정이다. 여러 채널의 구독자 수를 합산하지 않는다.

채널 통계 namespace는 `channel_id`, `created_at`, `subscriber_count`, `subscribers_hidden`, `captured_at`을 저장한다. 공개 API의 구독자 수는 YouTube가 공개하는 반올림 값이며 정확한 실시간 수치나 과거 증가 추이는 제공하지 않는다. 개설일과 데뷔일은 독립적인 필드다.

## 갱신

```powershell
.venv\Scripts\python.exe scripts/refresh_youtube_channel_statistics.py
.venv\Scripts\python.exe scripts/refresh_youtube_channel_statistics.py --all-registered
```

신규 DB에서 표시 중인 아티스트가 소유하고 수집이 활성화된 공식 YouTube 계정만 조회한다. 채널 ID를 중복 제거해 최대 50개씩 `channels.list(part=snippet,statistics)`로 요청하며 2초 간격을 둔다. 통계 응답은 Pydantic으로 검증하고 비공개 구독자는 null로 저장한다. 기존 collection state·lease·poll cursor·데뷔일을 덮어쓰지 않으며 영상 수집이나 외부 전송을 시작하지 않는다. 키·DB URL을 출력하지 않는다.

명시적인 `--all-registered` 옵션은 표시 중인 아티스트의 모든 등록된 공식 소유 채널을 대상으로 한다. 비활성 수집 계정도 채널 메타데이터만 조회하며 `collection_enabled`를 변경하거나 영상 수집을 활성화하지 않는다.

정상 `youtube_poll`도 기존 `channels.list` 요청의 part에 snippet·statistics를 포함해 응답을 검증하고 동일 namespace를 갱신한다. 채널 요청을 추가하지 않으며 별도의 주기 실행은 만들지 않는다. 운영 worker에 코드가 반영되어 실행될 때 기존 poll 주기로 갱신된다.

## 검증 — 2026-11-01

실데이터에서 95개 채널을 요청해 95개 응답을 저장했다. 실제 조회 API의 표시 중인 103명 중 구독자·개설일이 연결된 아티스트는 각각 89명, 데뷔일 등록은 58명이다. 나머지를 임의로 채우지 않는다.

같은 날짜의 추가 요청으로 `--all-registered`를 실행해 공식 채널 100개를 모두 갱신했다. 현재 조회 API에서 103명 중 구독자·생성일이 연결된 아티스트는 각각 94명이다. 나머지 9명(LITA·TINA·NERO·ヨミ·カスカ·MOCO·BAMBI·SAKUYA·KAGURA)은 개별 채널 등록이 없는 그룹 멤버이며 그룹 구독자 수를 개인 수치로 복사하지 않았다. 기본 가나다 순, 양방향 정렬, 시간대 비교 및 축약 수치 표시를 포함한 프론트 단위 테스트 56개와 PC·모바일 브라우저 테스트 2개를 통과했다.

프론트 빌드 통과, 정렬 단위 테스트 4개를 포함한 프론트 단위 테스트 52개 통과. PC·모바일 HTTP fixture 브라우저 테스트 2개에서 메뉴 위치·높이, 세 정렬, URL 복원, 소속사·검색 조합 및 가로 넘침을 검증했다. provider fixture로 묶음 조회·비공개·미확인·정상 poll의 추가 요청 없는 통계 확보를 검증한다. 폐기 가능한 로컬 PostgreSQL 바이너리가 없어 기존 YouTube 카탈로그 수집의 DB fixture 테스트 38개는 건너뛰었다. 실데이터 수집·조회 확인과 fixture 검증은 별개다.
