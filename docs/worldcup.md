# 곡 월드컵(오리지널·커버) 결과·통계

최종 확인 2026-11-26. 요구사항은 [018-original-worldcup](../specs/018-original-worldcup/spec.md), 복수 소속사 검증 결과는 [작업 기록](records/backend/worldcup-agencies-2026-11-26.md)에 있다.

월드컵 결과 저장 경로는 완료된 한 판의 경기 결과를 받는다. 설정과 랭킹 조회는 읽기 전용이다.

## 저장 (migration 008)

- `worldcup_runs`: 제출 ID(중복 방지), 익명 브라우저 ID(UUID, localStorage `utamowa-client-id`), 곡 종류(`original`·`cover`), 범위 종류·이름, 규모, 소요 시간, 우승 영상 ID, `is_local`.
- `worldcup_matches`: 판별 경기 순서·라운드·승자·패자 영상 ID.
- IP·계정·이름은 저장하지 않는다. 곡은 영상 ID로 식별한다(오리지널은 공식 MV, 커버는 커버 영상).

## 계약

`POST /api/worldcup/results` → 201 `{run_id, duplicate, winner}` (같은 `submission_id` 재전송은 200, `duplicate: true`)

- 본문: `submission_id`, `client_id`, `song_kind`(original 기본·cover), `scope_kind`(agency·artists·random), `scope_label`, `size`(16·32·64·128), `duration_seconds`, `matches[{round, winner, loser}]`(경기 순서).
- 거부(422 `invalid_bracket:<code>`): 경기 수가 규모−1이 아님(`match_count`), 라운드 순서(`round_order`), 1라운드 중복 곡(`duplicate_song`), 이전 라운드 승자끼리의 대결이 아님(`pairing`), 경기당 1초 미만(`too_fast`), 곡 종류에 맞지 않는 영상(`unknown_song`: 오리지널은 활성 녹음의 공식 MV, 커버는 저장된 커버).
- 429: 같은 브라우저 ID 1시간 20판 초과, 또는 같은 전달 주소 1시간 60판 초과(프로세스 메모리, 주소는 저장하지 않음).
- 503: 테이블이 아직 없음(migration 008 적용 전) 또는 DB 연결 불가.

`GET /api/worldcup/stats` → `{items, total, offset, limit, total_runs}`

- 파라미터: `song_kind`(original 기본·cover, 서로 섞지 않음), `agency`(오리지널은 녹음 명의, 커버는 채널 소유 아티스트의 소속사), `video_ids`(반복, 최대 128), `order`(`championships` 기본·`championship_rate`·`match_win_rate`), `min_appearances`(기본 1), `offset`, `limit`(최대 100).
- 항목: `video_id`, `title`, `title_ko`, `artist_name`, `appearances`(출전한 판), `championships`, `championship_rate`(우승÷출전), `match_wins`, `match_losses`, `match_win_rate`(승÷대결). 캐시하지 않는다.
- 화면은 비율 정렬에서 `min_appearances=3`을 쓴다.

`GET /api/worldcup/pool-summary?song_kind=` → `{song_kind,total,agencies[{name,count}],artists[{id,count}]}`

- 설정 화면용. `/api/explore/songs?kind=…&published_only=true`와 같은 탐색 쿼리 결과를 명의별·소속사별로 센다(협업 곡은 각 명의에 1회). 오리지널은 승인된 그룹 명의, 커버는 멤버 명의다. 종류별로 프로세스 메모리에 10분 캐시한다(2026-11-26 실측 첫 계산 오리지널 0.7초·747곡, 커버 2.1초·4,571곡).
- 소속사 모드에서 영상이 있는 소속사를 여러 곳 고를 수 있다. `GET /api/explore/songs`에 `agency_names`를 반복해 보내고, 선택 중 하나에 속하는 영상의 합집합으로 대진을 만든다. 여러 소속사가 참여한 영상은 한 번만 포함하고, 최소 16곡이 있어야 시작할 수 있다.
- 화면은 2,000곡을 넘는 후보(무작위 커버 등)를 100곡 단위 페이지 20개를 무작위로 골라 표본으로 쓰고 "전체 N곡 중 무작위 표본"이라고 표시한다.

## 로컬 판 구분

로컬 Vite 프록시는 모든 `/api` 요청에 `X-UtaMowa-Client: local-dev`를 붙인다. 이 헤더로 저장된 판은 `is_local=true`이며 공개 통계에서 빠지고, 같은 헤더가 있는 통계 요청(로컬 화면)에서만 포함된다. 로컬 백엔드도 운영 DB를 쓰므로 이 구분이 필요하다.

## 프록시

로컬 Vite와 운영 `web/server.mjs`는 `/api/worldcup/results`의 POST를 전달한다. 운영 프록시는 본문 64KB 초과를 413으로 막고 `X-Forwarded-For`를 붙이며, 그 밖의 POST는 405다.

## 배포 순서

앱은 DB의 마이그레이션 목록이 아는 조합이어야 동작한다. **008을 지원하는 백엔드를 먼저 배포한 뒤** `scripts/migrate_catalog.py --apply`로 008을 적용하고 `--verify`로 확인한다. 반대 순서면 배포된 구 백엔드의 조회가 모두 실패한다. 프론트(`server.mjs`)는 백엔드와 함께 배포한다.
