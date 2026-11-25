# YouTube 커버 영상

최종 확인 2026-11-23. 날짜별 오분류 수정·복구·검증 결과는 [변경·검증 기록](records/backend/youtube-covers-history.md)에 있다.

아티스트 화면은 라이브 → 커버 → 통계 → 발매곡 → 공연 정보 순서다. 커버 탭을 선택할 때만 첫 12개를 조회하며 더보기로 다음 페이지를 읽는다. 썸네일·원문 제목·게시일·영상 길이를 표시하고 영상 선택은 YouTube 새 창으로 연결한다. 조회 요청에서 외부 수집을 시작하지 않는다.

## 조회 계약

`GET /api/artists/{artist_id}/covers?offset=0&limit=12&order=latest`는 `Page[CoverRead]`를 반환한다. `order`는 `latest`(기본)·`oldest`·`views`이고 항목에 저장된 YouTube 조회수 `view_count`(없으면 null)를 포함한다. 조회 중 YouTube를 호출하지 않는다.

- `offset`은 0~100000, `limit`은 1~100이다. `API_KEY`가 설정된 환경에서만 API 키를 요구한다. 존재하지 않거나 카탈로그에 표시하지 않는 아티스트는 404다. 임시 `/api/v2` 별칭에서도 같다.
- `items`는 `id`, `youtube_video_id`, `youtube_url`, `title`, `published_at`, `duration_seconds`, `view_count`, `views_updated_at`이다. 조회수는 채널 수집이 저장한 통계이며 0은 실제 값, null은 미확인이다.
- 기본 정렬(`latest`)은 게시일 내림차순, `oldest`는 게시일 오름차순이며 둘 다 날짜가 없는 항목은 마지막이다. `views`는 조회수 내림차순, 미확인은 마지막, 동률은 최신 게시일이다. 모든 정렬의 마지막 기준은 커버 ID다.
- 저장된 `covers`와 `videos` 중 보관 처리되지 않고 공개·일부 공개·공개 상태 미확인인 항목만 읽는다.
- 범위는 현재 공식 채널 소유 관계(`artist_external_accounts.relationship=owner`)와 영상의 `source_account_id`로 정한다. 채널 소유자를 가창 참여자로 자동 확정하지 않는다.
- VESPERBELL·KMNZ 멤버의 커버는 [공유 채널 규칙](shared-youtube-channels.md)에 따라 제목에 명시된 멤버만, 명시가 없으면 대상 멤버 전원에게 표시한다. 전체 목록에서 영상은 중복 생성하지 않는다.
- 원본 수집에는 Shorts도 남을 수 있으나 사용자 조회에서는 [곡 탐색의 Shorts 제외 규칙](song-exploration.md#shorts-제외)에 따라 제외하고, 짧은 미확인 영상은 형식 확인 후 표시한다.

## 커버 판정 기준 (`cover-title-v3`)

수집 worker, 과거 수집, 곡 탐색과 아티스트 커버 조회가 같은 제목 기준을 사용한다.

- 제목의 독립된 `cover`/`covered`/`covers`, `歌ってみた`, `カバー`, `커버`만 커버 근거로 사용한다. 설명의 홍보 링크·해시태그나 `歌唱` 가창 크레딧은 근거로 쓰지 않으며 명시적 셀프 커버는 제외한다.
- 진행 중·예정 영상은 제외한다. 완료된 영상에 방송 시작·종료 정보가 있어도 프리미어 공개에서 생긴 정보일 수 있으므로 명시적 커버 제목을 다시 확인해 인정한다. YouTube Data API의 공식 premiere 플래그를 사용하는 판정은 아니다.
- 가창 방송 제목은 기존 archive 분류를 유지하고 라이브 방송·잡담·장시간 방송 등의 제목은 일반 커버로 넣지 않는다.
- 과거 설명만으로 저장된 후보는 원문·소유권을 유지하고 조회에서 제외한다. 그런 후보 때문에 연결된 발매 음원이 오리지널 탭에서 빠지지 않는다.
- 비공개·삭제 영상과 제목에 커버 표기가 없는 영상은 수집을 보장하지 않는다.

## 과거 영상 수집

```powershell
.venv\Scripts\python.exe scripts/backfill_catalog_youtube_covers.py --until-complete
```

- 대상은 신규 DB의 표시 중인 아티스트가 소유하고 수집이 활성화된 YouTube `external_accounts`다. 구 DB 및 `youtube_channel_monitors`를 읽거나 변경하지 않는다.
- 채널의 업로드 재생목록을 `playlistItems.list` 50개, `videos.list` 최대 50개 단위로 순차 처리한다. 검색 API·LLM·댓글·Discord·Calendar는 호출하지 않는다.
- 페이지 단위로 신규 영상·커버·원문 설명과 provider 메타데이터를 한 트랜잭션에 저장한다. 영상 ID 잠금과 고유 키로 중복을 막고, 다른 채널 소유권·기존 보관 처리·라이브 분류를 덮어쓰지 않는다. 페이지 저장 후에만 다음 페이지 토큰을 기록하므로 중간 종료 후 같은 페이지를 다시 읽어도 중복 생성하지 않는다.
- 공유 채널 업로드 목록에 나타나는 별도 게시 채널은 승인된 출처 ID를 external account로 등록한 경우에만 수집한다. 출처가 비어 있던 기존 완료 프리미어는 빈 출처만 채우고 기존 라이브 행을 보존한다. 임의의 다른 채널은 수집하지 않으며 기존 출처를 덮어쓰지 않는다.

| 옵션 | 기본값 | 동작 |
| --- | --- | --- |
| `--until-complete` | 꺼짐 | 예산이 회복되면 자동 재개하고 일시적인 provider 실패를 최대 5회 연속 재시도 |
| `--budget` | 1500 | 이 도구의 최근 24시간 요청 수 상한(실패 요청 포함). 프로젝트 전체 사용량 계측은 아니므로 남은 할당량에 맞춰 낮출 수 있다 |
| `--interval` | 2 | 요청 간 최소 초 |
| `--max-pages` | 2000 | 채널별 실행당 페이지 상한 |
| `--checkpoint` | `.tmp/youtube-cover-backfill.json` | 진행 위치와 요청 시각 |
| `--account-id ID` | 없음 | 지정한 계정만 처리(반복 가능) |
| `--rescan-completed` | 꺼짐 | 완료 채널 재검사. `--account-id` 또는 `--rescan-all`이 필요 |
| `--rescan-all` | 꺼짐 | 대상 채널 전체를 명시적으로 재검사 |
| `--rescan-run LABEL` | 자동 생성 | 재검사 감사 라벨(영문·숫자·`._-` 1~80자). 같은 라벨로 재개하면 완료한 페이지를 다시 초기화하지 않는다 |
| `--include-disabled` | 꺼짐 | 비활성 계정의 커버 전용 검사. 정기 수집 설정은 바꾸지 않는다 |

- 재검사는 같은 체크포인트의 요청 예산과 기존 pages/covers_saved 누적값을 유지하고 rescan_history에 이전 상태를 남긴다.
- 체크포인트는 DB 인스턴스 ID를 대조하며 DB advisory lock으로 이 도구의 동시 실행을 막는다. 같은 체크포인트를 써야 완료 채널과 최근 요청 사용량을 이어받는다.
- API 일일 할당량 오류는 provider 대기 시간을 따른다. 영구 오류나 DB 오류는 종료하며 원인을 해결한 뒤 같은 명령으로 재개한다. PC나 프로세스가 종료되면 자동 실행되지 않는다.
- 신규 영상의 정기 수집은 기존 `youtube_poll`/`youtube_collect` worker를 따른다. 전체 채널 재검사는 [전체 커버 재검사 기록](records/data/youtube-cover-audit-2026-11-01.md)과 `scripts/audit_youtube_covers.py`를 참고한다.

## 테스트

```powershell
.venv\Scripts\python.exe -m pytest tests/test_youtube_covers.py tests/test_new_catalog_read.py -q --basetemp=.tmp/pytest-covers -p no:cacheprovider
cd web
npm test
npx playwright test --config playwright.real.config.ts artist-covers.spec.ts
npm run build
```

DB fixture 테스트는 로컬 PostgreSQL 바이너리가 있어야 실행되며 없으면 건너뛴다. 브라우저 테스트는 HTTP fixture를 사용하므로 실데이터 검증과 구분한다.
