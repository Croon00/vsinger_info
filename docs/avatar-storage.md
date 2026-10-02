# 프로필 이미지 저장과 교체

2026-09-20 최초 적용. 아티스트 이미지 파일은 Neon Object Storage, 대표 URL은 `artists.avatar_url`에 저장한다. 2026-10-02 자동 초기 이미지 코드와 migration 007을 추가했다. 이 revision의 운영 DB 적용·실제 업로드는 아직 검증하지 않았다.

## 신규 등록 시 자동 이미지

revision 007의 `avatar_jobs`와 DB trigger가 아티스트에 YouTube·X `owner` 관계를 저장할 때 같은 transaction으로 이미지 작업을 예약한다. 아티스트 생성 후 계정을 나중에 연결하거나 URL·대표 계정·소유 관계를 바꿔도 적용된다. 등록에는 외부 API나 업로드를 실행하지 않는다. 조회 `/api`도 이미지 작업을 예약·실행하지 않는다. 등록 스크립트와 향후 신규 DB용 등록 경로에 공통으로 적용되며 admin-web 연동은 이번 범위에 없다.

- 기존 `avatar_url`이 있으면 예약·교체를 생략한다. 직접 지정한 이미지를 우선 보존한다.
- YouTube → X 순서이며 같은 플랫폼에서는 `is_primary` → `position` → 계정 ID 순서다. `member` 관계와 보관된 계정은 제외한다. `collection_enabled`와 탐색 노출 여부는 이미지 처리 조건이 아니다.
- YouTube는 고정 채널 ID를 우선 사용하고, 없으면 `/channel/UC…`, `/@handle`, `/user/…`를 해석한다. `channels.list(part=snippet)`의 `high` → `medium` → `default` URL을 사용한다. `/c/…`와 식별되지 않는 주소는 이름 검색하지 않고 `channel_id_required`로 기록한다.
- X는 등록된 프로필 주소의 핸들과 기존 설정의 twscrape/X API를 사용한다. 이미지가 없거나 다운로드·이미지 검증이 실패하면 다음 후보로 넘어간다.
- 일시 오류는 계정별 최대 3회 시도한 뒤 다음 후보로 넘어간다. 전체 작업은 최대 5회다. `Retry-After`/YouTube quota 대기 시각을 저장하고 같은 플랫폼 후보를 가진 다른 이미지 작업도 그 시각까지 대기한다. 음악 수집 큐는 변경하지 않는다.
- 다운로드·128/256/512 WebP 변환·업로드·공개 응답과 캐시 검증 뒤 대표 URL을 저장한다. 원본 이미지 URL·출처 플랫폼/계정·콘텐츠 해시 경로는 작업 결과와 `catalog_changes`에 남긴다. `artists.avatar_url`은 저장소 URL이다.
- 업로드 실패는 선택한 원본 URL로 재시도한다. 같은 콘텐츠는 같은 경로를 사용한다. 만료 lease는 복구하고 아티스트별 동시 실행을 막는다. 반영 직전에 현재 소유 관계·계정 정보를 다시 확인하며, 실행 중 수동 지정된 이미지는 보존한다.
- 주소가 모두 없으면 예약하지 않는다. 후보를 모두 사용할 수 없으면 `no_source`, 기존 이미지가 생기면 `skipped_existing`, 소유 관계 변경/아티스트 보관은 `conflict`다. 저장 오류·최종 lease 소진은 `failed`로 기록한다. 아티스트 등록은 유지한다.

`python -m app.runtime`에서 `RUNTIME_CUTOVER_ENABLED=true`, `AGENT_ENABLED=true`, `AVATAR_WORKER_ENABLED=true`(기본값)가 모두 충족되면 독립 이미지 loop가 실행된다. 007 미적용 DB에서는 `migration_required`로 대기한다. API만 실행하면 이미지 worker는 실행되지 않는다. `/ready`는 기존 음악 worker 검사이며 이미지 큐의 상태를 포함하지 않는다.

```powershell
# 명시적 schema 적용. 기존 이미지는 일괄 재수집하지 않는다.
.\.venv\Scripts\python.exe scripts/migrate_catalog.py --apply
# 기존 개인세 세 명의 빈 이미지 작업: 기본은 DB 읽기만 하는 미리보기
.\.venv\Scripts\python.exe scripts/avatar_jobs.py enqueue --artist-id 941 --artist-id 942 --artist-id 943
.\.venv\Scripts\python.exe scripts/avatar_jobs.py enqueue --artist-id 941 --artist-id 942 --artist-id 943 --apply
# 이미지 조회·저장소 업로드·DB 갱신. 음악 수집은 실행하지 않는다.
.\.venv\Scripts\python.exe scripts/avatar_jobs.py run-once
.\.venv\Scripts\python.exe scripts/avatar_jobs.py worker
.\.venv\Scripts\python.exe scripts/avatar_jobs.py status 1
```

007 적용 자체는 이미 등록된 아티스트의 작업을 만들지 않는다. 같은 아티스트·계정 snapshot·`request_run`은 같은 작업을 반환한다. 끝난 작업의 명시적 재시도는 `enqueue --request-run retry-2026-10-02 --apply`처럼 새 라벨을 지정한다. 현재 이미지는 여전히 덮어쓰지 않는다. 주기적인 이미지 교체는 후속 작업이다.

## 연결 설정

루트의 Git 제외 파일 `.env` 또는 서버 환경변수에 다음 값을 설정한다. 비밀값은 프론트 환경변수에 넣지 않는다.

- `DATABASE_URL`: 새 통합 DB
- `AWS_ENDPOINT_URL_S3`: 해당 Neon 브랜치의 S3 endpoint
- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`: 이미지 worker·명시적 업로드 도구 전용. 일반 조회 API의 이미지 URL 생성에는 불필요
- `AWS_REGION`: 저장소 리전
- `AVATAR_BUCKET`: 이미지 버킷. 이번 적용값은 `avator-image`

버킷은 Neon 콘솔에서 `public_read`로 설정해야 한다. 공개 읽기만 허용하며 쓰기는 자격 증명이 필요하다. 현재 코드는 별도 CDN을 구성하지 않고 저장소에서 직접 제공한다. 캐시는 HTTP 브라우저 캐시다.

## 크기 선택

현재 CSS 기준 즐겨찾기는 88/100/116px, 아티스트 상세는 80/140/168px, 공연 팝업은 최대 108px, 일정 목록은 48~64px이다. 탐색·검색 그리드는 컨테이너에 따라 가변이다.

| 파일 | 주된 용도 |
| --- | --- |
| 128.webp | 일정 목록·작은 프로필 |
| 256.webp | 즐겨찾기·모바일 그리드, 작은 프로필의 고밀도 화면 |
| 512.webp | 탐색 그리드·상세 프로필의 고밀도 화면 |
| original | 재가공용 원본, 일반 프론트에 제공하지 않음 |

픽셀 크기는 긴 변의 상한이다. 비율을 유지하고 원본보다 확대하지 않는다. EXIF 방향을 반영한 뒤 화면용 파일의 메타데이터를 제거하고 WebP quality 85로 저장한다. 애니메이션 이미지라면 첫 프레임을 정적 이미지로 사용한다.

`ArtistAvatar`가 실제 렌더링 크기와 devicePixelRatio에 맞는 파일 하나를 선택한다. 화면 200px 근처에 오기 전에는 src를 비워 Reka의 내부 사전 로딩도 지연한다. 실패 시 기존 AvatarFallback을 유지한다.

## 최초 이전 / 신규 URL 반영

프로젝트 루트에서 실행한다. report 경로는 실행마다 새 이름을 쓴다. 기존 보고서는 복구 이력이므로 prepare가 덮어쓰지 않는다.

```powershell
.\.venv\Scripts\python.exe scripts/migrate_avatars.py prepare --report db-migration/workspace/avatars/import-next.json
.\.venv\Scripts\python.exe scripts/migrate_avatars.py apply --report db-migration/workspace/avatars/import-next.json
```

prepare는 DB를 조회하고 외부 이미지를 로컬에 다운로드·가공한다. 이미 관리 중인 URL은 건너뛴다. apply는 원본과 변형 파일을 업로드하고 **모든 변형의 익명 GET, 내용, Cache-Control을 확인한 다음** DB를 갱신한다. 새 주소를 만든 동안 관리자가 avatar_url을 수정했다면 conflict로 건너뛴다. 다운로드/업로드 실패 항목의 DB URL은 유지한다. apply는 중단 후 같은 report로 재실행할 수 있다.

관리자에서 신규 외부 URL을 저장한 뒤 위 과정을 실행하거나, 한 아티스트만 교체할 수 있다.

```powershell
.\.venv\Scripts\python.exe scripts/migrate_avatars.py prepare --artist-id 1 --source-url "https://example.com/new-profile.jpg" --report db-migration/workspace/avatars/artist-1-next.json
.\.venv\Scripts\python.exe scripts/migrate_avatars.py apply --report db-migration/workspace/avatars/artist-1-next.json
```

직접 지정한 URL의 저장소 이전·기존 이미지 교체는 이 명시적 CLI 작업을 사용한다. 빈 이미지의 최초 채움은 위 `avatar_jobs`가 담당한다. 공통 다운로드·변환·업로드 구현은 `app/services/avatar_storage.py`다.

## 캐시와 교체

경로는 `avatars/v1/{artist_id}/{콘텐츠 해시}/{128|256|512}.webp`다. 해시는 원본과 가공 결과에서 만들어 이미지나 가공 설정이 달라지면 새 경로가 된다.

- 이미지 헤더: `Cache-Control: public, max-age=31536000, immutable`
- DB 대표 URL: 512.webp
- API `avatar_variants`: 128/256/512 주소. 현재 설정의 관리 URL만 파생하고 외부 URL에는 빈 객체를 반환한다.
- API 응답은 기존 no-store, 프론트 데이터 캐시는 기존 30초다. 이미 열린 화면은 자동 push 갱신하지 않으며 새로고침하면 새 URL을 받는다.
- 이전 파일은 삭제하지 않는다. 브라우저 캐시나 복구 이력과 충돌하지 않는다.
- CDN/이미지 변환 서비스는 별도로 추가하지 않았다.

원본, 이전 주소, 새 주소와 결과는 Git 제외 경로 `db-migration/workspace/avatars/`에 보존한다. 복구 시 report의 source(교체 작업이면 previous_url)를 해당 ID에 복원하되, 현재 URL이 report의 new_url과 일치하는지 확인해야 한다. 이후의 별도 수정을 덮어쓰지 않는다.

## 검증 기록

2026-10-02: disposable 로컬 PostgreSQL과 provider/S3/HTTP mock 검증 203개 통과. 범위는 신규 자동 이미지·등록 dry-run/재실행·동시 claim·lease 복구·provider 대기·수동 수정/소유 변경 보호·공개 업로드 검증, migration 001/002/004/006 업그레이드, 기존 이미지 CLI·runtime·음악 작업·YouTube/Spotify 수집·조회 API·X 클라이언트 회귀다. 운영 DB schema 변경·실제 YouTube/X 조회·업로드는 실행하지 않았다.

2026-09-20: 81개 이미지 다운로드·WebP 생성·업로드·DB 반영 성공, 실패 0개. 각 3개 변형의 공개 응답과 캐시 헤더를 DB 반영 전에 확인했다. 원본 합계 13,153,829 bytes, 256px 합계 1,174,592 bytes(약 91% 감소). 전송 파일 크기 비교이며 페이지 전체 로딩 시간 측정값은 아니다.

로컬 fixture: 이미지 변환/URL 검사 및 기존 조회 API 테스트 12개, 프론트 단위 테스트 26개, PC·모바일 이미지 크기 선택/지연 로딩/주소 교체 브라우저 테스트 2개 통과. 프론트 타입 검사·프로덕션 빌드 통과.
