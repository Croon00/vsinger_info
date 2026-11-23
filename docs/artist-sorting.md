# 아티스트 탐색 정렬

최종 확인 2026-11-23. 날짜별 실데이터 갱신·검증 결과는 [변경·검증 기록](records/backend/artist-sorting-history.md)에 있다.

## 화면

소속사 선택 오른쪽에 같은 Select 형태로 정렬 기준을 제공한다. 기본은 가나다 순이며 즐겨찾기가 정렬 순서를 바꾸지 않는다. 선택은 URL의 `sort=channel-created|channel-recent|subscribers|subscribers-low|name`에 보존된다. 소속사 필터와 이름 검색 결과에 같은 정렬을 적용한다.

- 채널 생성 오래된 순 / 최근 순: `youtube_channel_created_at`을 시간대로 보정한 시각으로 비교한다. 미확인은 양방향 모두 마지막이다. 실제 데뷔일 필드는 변경하지 않는다.
- 구독자 높은 순 / 낮은 순: 공식 소유 채널의 공개 구독자 수로 비교한다. 0명은 정상 수치이며 비공개·미확인은 양방향 모두 마지막이다. 동률은 이름 순서다.
- 가나다 순: 한국어 표시 이름(`display_name`)을 우선하고 없으면 원어 이름으로 한국어 locale 정렬한다. 숫자는 자연수 순서로 비교하고 동률은 아티스트 ID 순서다.

아티스트 카드 이름 오른쪽에 구독자 수를 `12.1만`처럼 표시한다. 만 명 미만은 `9,999`, 1억 이상은 `1.2억`으로 표시하며 반올림해 수치를 올리지 않는다. 비공개·미확인은 `—`다. 접근성 레이블과 툴팁은 API에 저장된 전체 숫자를 제공한다. 모바일에서는 이름과 구독자 수 공간을 확보하도록 즐겨찾기 버튼을 한국어 이름 줄 오른쪽에 둔다.

## 저장 및 조회

- `/api/artists`, `/api/artists/{id}`는 nullable `debut_date`, `youtube_subscriber_count`, `youtube_channel_created_at`, `youtube_statistics_updated_at`을 반환한다. 신규 DB의 `artists.debut_date`와 `collection_states.provider_state.youtube_channel_statistics`를 읽으며 조회 시 provider를 호출하지 않는다.
- 대표 채널은 현재 owner 관계 중 `position`, 관계 ID가 빠른 YouTube 계정이다. 여러 채널의 구독자 수를 합산하지 않는다.
- VESPERBELL의 ヨミ·カスカ와 KMNZ의 LITA·TINA·NERO는 [공유 채널 규칙](shared-youtube-channels.md)에 따라 그룹 채널 통계와 링크를 사용한다. `youtube_statistics_source`와 구독자 툴팁에 그룹 출처를 표시하며 소유권을 바꾸지 않는다. 개별 채널이 없는 다른 그룹 멤버에게 그룹 구독자 수를 개인 수치로 복사하지 않는다.
- 채널 통계 namespace는 `channel_id`, `created_at`, `subscriber_count`, `subscribers_hidden`, `captured_at`을 저장한다. 구독자 수는 YouTube가 공개하는 반올림 값이며 실시간 수치나 과거 증가 추이는 제공하지 않는다. 개설일과 데뷔일은 독립 필드이며 값이 없으면 임의로 채우지 않는다.

## 갱신

```powershell
.venv\Scripts\python.exe scripts/refresh_youtube_channel_statistics.py
.venv\Scripts\python.exe scripts/refresh_youtube_channel_statistics.py --all-registered
.venv\Scripts\python.exe scripts/refresh_youtube_channel_statistics.py --account-id <ID>
```

- 기본은 표시 중인 아티스트가 소유하고 수집이 활성화된 공식 YouTube 계정만 조회한다.
- `--all-registered`는 표시 중인 아티스트의 모든 등록된 공식 소유 채널을 대상으로 한다. 비활성 수집 계정도 채널 메타데이터만 조회하며 `collection_enabled`를 바꾸거나 영상 수집을 활성화하지 않는다.
- `--account-id`는 지정한 계정만 갱신한다(반복 가능).
- 채널 ID를 중복 제거해 최대 50개씩 `channels.list(part=snippet,statistics)`로 요청하며 2초 간격을 둔다. 응답은 Pydantic으로 검증하고 비공개 구독자는 null로 저장한다.
- 기존 collection state·lease·poll cursor·데뷔일을 덮어쓰지 않으며 영상 수집이나 외부 전송을 시작하지 않는다. 키·DB URL을 출력하지 않는다.

정상 `youtube_poll`도 기존 `channels.list` 요청의 part에 snippet·statistics를 포함해 같은 namespace를 갱신한다. 채널 요청을 추가하지 않으며 별도 주기 실행은 없다. 운영 worker에 코드가 반영되어 실행될 때 기존 poll 주기로 갱신된다.

## 테스트

provider fixture로 묶음 조회·비공개·미확인·정상 poll의 추가 요청 없는 통계 확보를 검증한다. 프론트는 정렬·축약 수치 단위 테스트와 PC·모바일 HTTP fixture 브라우저 테스트로 메뉴 위치·정렬·URL 복원·소속사·검색 조합·가로 넘침을 확인한다. YouTube 카탈로그 수집의 DB fixture 테스트는 로컬 PostgreSQL 바이너리가 있어야 실행된다.
