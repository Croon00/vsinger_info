# YouTube 커버 영상

아티스트 화면은 라이브 → 커버 → 통계 → 발매곡 → 공연 정보 순서다. 커버 탭을 선택할 때만 첫 12개를 조회하며 더보기로 다음 페이지를 읽는다. 썸네일·원문 제목·게시일·영상 길이를 표시하고 영상 선택은 YouTube 새 창으로 연결한다. 조회 요청에서 외부 수집을 시작하지 않는다.

## 조회 계약

`GET /api/artists/{artist_id}/covers?offset=0&limit=12`는 `Page[CoverRead]`를 반환한다. `offset`은 0~100000, `limit`은 1~100이다. 기존 조회 API와 동일하게 `API_KEY`가 설정된 환경에서 API 키 인증을 적용하며, 미설정 환경에서는 인증을 강제하지 않는다. 존재하지 않거나 카탈로그에 표시하지 않는 아티스트는 404다. 임시 `/api/v2` 별칭에서도 동일하게 제공한다.

`items`는 `id`, `youtube_video_id`, `youtube_url`, `title`, `published_at`, `duration_seconds`를 제공한다. 게시일 내림차순, 같은 날짜는 커버 ID 내림차순이며 날짜가 없는 항목은 마지막이다. 저장된 `covers`와 `videos` 중 보관 처리되지 않고 공개·일부 공개·공개 상태 미확인인 항목만 읽는다. 현재 공식 채널 소유 관계(`artist_external_accounts.relationship=owner`)와 영상의 `source_account_id`로 범위를 정하며, 채널 소유자를 가창 참여자로 자동 확정하지 않는다.

## 과거 영상 수집

```powershell
.venv\Scripts\python.exe scripts/backfill_catalog_youtube_covers.py --until-complete
```

수집 대상은 신규 DB의 표시 중인 아티스트가 소유하고 수집이 활성화된 YouTube `external_accounts`다. 구 DB 및 `youtube_channel_monitors`를 읽거나 변경하지 않는다. API로 채널의 업로드 재생목록을 확인하고 `playlistItems.list` 50개, `videos.list` 최대 50개 단위로 순차 처리한다. 검색 API·LLM·댓글·Discord·Calendar는 호출하지 않는다.

기존 커버 판별 함수에 따라 제목 또는 설명의 `cover`, `歌ってみた`, `歌唱`, `カバー`, `covered by`를 후보로 삼는다. 방송 시작·종료 정보 또는 방송 예정 상태가 있는 영상은 제외한다. Shorts를 별도로 판별하지 않으므로 키워드가 있는 짧은 커버도 포함될 수 있다. 비공개·삭제 영상과 키워드가 없는 커버는 전체 수집을 보장하지 않는다.

페이지 단위로 신규 영상·커버·원문 설명과 provider 메타데이터를 한 트랜잭션에 저장한다. 영상 ID 잠금과 고유 키로 중복을 방지하고, 다른 채널 소유권·기존 보관 처리·라이브 분류를 덮어쓰지 않는다. 페이지 저장을 마친 뒤에만 다음 페이지 토큰을 기록하므로 중간 종료 후 같은 페이지를 다시 읽어도 중복 생성하지 않는다.

기본 API 요청 간격은 2초이며 이 도구의 최근 24시간 시도 요청을 1,500회로 제한한다. 실패한 요청도 계산한다. 이는 다른 worker를 포함하는 프로젝트 전체 사용량 계측은 아니므로 실제 남은 할당량에 맞춰 `--budget`을 더 낮출 수 있다. `--interval`, `--max-pages`도 조정 가능하다. 페이지 제한은 채널별 실행당 2,000페이지다.

진행 위치와 요청 시각은 `.tmp/youtube-cover-backfill.json`에 저장한다. DB 인스턴스 ID를 대조하고 DB advisory lock으로 이 도구의 동시 실행을 막는다. 같은 체크포인트를 유지해야 완료한 채널과 최근 요청 사용량을 이어받는다. `--until-complete`는 예산이 회복되면 자동 재개하고 일시적인 provider 실패를 최대 5회 연속 재시도한다. API 일일 할당량 오류는 provider 대기 시간을 따른다. 영구 오류나 DB 오류는 종료하며 원인을 해결한 뒤 같은 명령으로 재개한다. PC나 프로세스가 종료되면 자동 실행되지 않으며 동일 명령을 다시 실행해야 한다. 신규 영상의 정기 수집은 기존 `youtube_poll`/`youtube_collect` worker를 따른다.

## 검증 — 2026-10-31

- 프론트엔드 실제 모드 빌드 통과, 기존 단위 테스트 48개 통과.
- HTTP fixture를 사용하는 PC·모바일 브라우저 테스트 4개 통과: 탭 지연 조회, 더보기, 원문 URL, 새로고침 후 선택 유지, 오류 재시도, 빈 목록, 가로 넘침 검사.
- provider/DB mock을 사용하는 요청 예산·체크포인트 재개 테스트 2개 통과. 로컬 PostgreSQL 바이너리가 없어 폐기 가능한 DB를 사용하는 신규 API·저장 테스트 2개와 기존 카탈로그 읽기 테스트 13개는 건너뛰었다.
- 별도의 실데이터 검증에서 신규 DB identity, 수집 활성 채널 95개, 기존 커버 380개를 확인한 뒤 요청된 추가 수집을 실행했다. 실제 페이지 저장을 확인하고 신규 DB를 읽는 FastAPI TestClient에서 아티스트별 조회 200, API 키 설정 시 미인증 401, 없는 아티스트 404, 잘못된 페이지 크기 422 및 페이지 간 ID 중복 없음을 확인했다. 전체 채널 수집 완료 여부는 체크포인트의 `done`과 실행 로그로 확인해야 하며 테스트 통과와 구분한다.

회귀 검증 명령:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_youtube_covers.py tests/test_new_catalog_read.py -q --basetemp=.tmp/pytest-covers -p no:cacheprovider
cd web
npm test
npx playwright test --config playwright.real.config.ts artist-covers.spec.ts
npm run build
```
