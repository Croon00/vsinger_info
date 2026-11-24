# 후속 작업

최종 확인 2026-11-23. 남은 작업만 우선순위별로 둔다. 완료 기록과 2026-11-23 정리 전 날짜별 경과는 [정리 전 전문](records/backend/roadmap-2026-11-23.md)과 각 기록 문서에 있다. 기능별 세부 작업은 각 스펙의 tasks.md(T 번호)에서 추적하고, 끝난 항목은 이 문서에서 지우고 해당 tasks.md·기록 문서에 날짜와 근거를 남긴다.

현재 상태 요약: 2026-09-23 신규 DB로 필수 상태를 이전했다([전환 기록](records/backend/backend-cutover-2026-09-23.md)). 조회 `/api`와 프론트는 신규 DB를 사용한다. X·Discord·YouTube·Spotify·이미지·생방송 수집 코드는 로컬에서 검증했지만 **운영 활성화와 실제 관찰은 끝나지 않았다.** 범위 결정은 [통합 최종 계획](plans/backend-consolidation-plan.md)과 [서비스 보완 계획](plans/backend-service-readiness-plan.md)을 따른다.

## 1. 운영 전환과 배포

로컬 검증은 끝났으나 배포·실제 관찰이 남은 항목이다. 배포 전후에 `/ready`와 각 수집 결과를 확인한다.

- [ ] **오리지널 곡 조회 복구 배포**: 운영 분류 파일 누락으로 기본 오리지널 API가 500을 반환한다(2026-11-21 확인). 새 백엔드와 `app/resources/classification/original_music_tags.json`을 배포한 뒤 운영 목록·분류 필터를 확인한다. [원인·계약](original-music-tags.md), [014-original-song-availability](../specs/014-original-song-availability/tasks.md)
- [ ] runtime 운영 활성화: 신규 DB runtime의 실제 수집, Discord 활성화와 장애 확인. [전환 순서](records/backend/backend-phase-5-cutover.md). [001](../specs/001-service-readiness/tasks.md) T007~T010
- [ ] X provider `NoAccountError` 재현 여부·원인 조사와 수정. 001 T003
- [ ] Discord 실제 URL 전송·route·중복 방지 확인. 001 T009
- [ ] 생방송 멀티뷰 운영 반영: Railway에 `HOLODEX_API_KEY`, `HOLODEX_POLL_SECONDS=3600`, `HOLODEX_LIVE_CHECK_SECONDS=180`을 설정하고 API·monitor를 함께 배포한다. 이전 운영 API는 `live_checked_at`을 모르므로 조회 코드도 같이 배포해야 한다. 배포 웹에서 재생·채팅·자동재생 제한을 확인하고, YouTube 모드를 쓸 경우 채널 수에 따른 할당량을 점검한다. [002](../specs/002-live-multiview/tasks.md) T006~T009
- [ ] VESPERBELL MEMBERSHIP·KMNCLUB 멀티뷰 전용 등록과 운영 수집 확인. [등록 기록](records/data/multiview-membership-channels-2026-11-24.md) · [002](../specs/002-live-multiview/tasks.md) T012
- [ ] 프로필 이미지 worker의 서버 저장소 환경변수 갱신·재시작·실제 처리 확인. 배포 환경의 `AVATAR_BUCKET`과 기존 저장 URL 버킷 일치 여부도 확인한다(다르면 `avatar_variants`가 비어 대표 URL만 쓰임). [004](../specs/004-avatar-storage/tasks.md) T003
- [ ] 로컬 검증 후 배포하지 않은 코드의 배포와 확인:
  - 세트리스트 규칙 우선 추출·후보 비교(배포 후 실제 모델 품질 평가 포함), 작업 선점 반복 스캔 제거·보관 가창 재생성 방지. [008](../specs/008-setlist-quality/tasks.md) T005
  - 단일 채널 owner의 새 가창 자동 연결 worker. [005](../specs/005-catalog-registration/tasks.md) T005
  - 디스코그래피 YouTube 링크 조회·웹 버튼. [006](../specs/006-discography-links/tasks.md) T005
  - 라이브·통계 아티스트 범위 SQL 최적화. [009](../specs/009-song-exploration/tasks.md) T003
  - 오리지널 장르·분위기 필터. [010](../specs/010-original-music-tags/tasks.md) T004
  - 세트리스트 규칙 `setlist-rules-2`(모델 호출 없는 번호 타임스탬프 등). 장기 worker 적용 후 신규 수집 확인. [008](../specs/008-setlist-quality/tasks.md)
  - YouTube 오리지널 일일 수집: poll·collect worker 모두 새 코드 적용 후 일일 수집·실제 조회 검증. [012](../specs/012-youtube-original-daily/tasks.md), [계약](youtube-original-collection.md)
  - HONK THE HORN·NUROJUNK 멤버별 수집·일일 재대조 worker/API. [013](../specs/013-shared-member-catalog/tasks.md)
  - 홈 최근 곡·즐겨찾기 캐러셀(PC·모바일 화면 검수 포함). [011](../specs/011-home-recent-songs/tasks.md)
- [ ] 로컬 PostgreSQL이 없어 건너뛴 DB fixture 테스트를 CI 또는 PostgreSQL이 있는 환경에서 실행한다. 여러 스펙의 검증에서 반복해서 남은 항목이다(011·012·013 포함).
- [ ] 운영 동일 출처 `/api` 프록시 구성.
- [ ] Neon 사용량 확인: 빈 큐 확인을 15분 경계로 바꾼 뒤(`WORKER_IDLE_SECONDS=900`) worker 활성 설정·중복 runtime·`/ready` 감시 주기와 Neon Active 시간·CU-hours를 비교한다. 실제 절감량은 미검증이다.

## 2. 데이터 검수와 보완

자동 수집이 만든 후보를 사람이 확인하거나 근거를 찾아 연결하는 작업이다. 원문·외부 ID·출처·수동 교정을 보존하고 이름만으로 병합하지 않는다.

- [ ] 세트리스트 잔여(2026-11-21 규칙 복구 후): 추가 형식/충돌 검토 1,613개·저장 댓글 없음 466개·보관 가창 보호 62개, 총 2,141개. 오토노세 라코 133개는 미해결이다. [복구 기록](records/data/setlist-rules-recovery-2026-11-21.md), [008](../specs/008-setlist-quality/tasks.md)
- [ ] 세트리스트: 2026-10-31 모델 재처리의 원문 검증 실패 108개·판단 불확실 1개 수동 검토, 댓글 없는 261개는 새 근거가 생기면 재검토(보관 가창 33개는 자동 재생성하지 않음). 10월 초 보류·복구 3단계 범위(빈 아카이브 44개+정정 1개)와 중복 없이 대조해 현재 잔여를 확정한다. `transient_error` 원인 조사와 재시도 소진 작업 복구 포함. [008](../specs/008-setlist-quality/tasks.md) T003~T004
- [ ] 요청 아티스트(2026-10-02) 후속: 미란 대상 확인, 기존 보류 15,825행과 미연결 행의 반영·오파싱 교정, 미연결 곡·한국어 제목·작품·Spotify 자료. [005](../specs/005-catalog-registration/tasks.md) T003~T005
- [ ] Spotify 미연결 32명(검토 19·이름 미일치 13)의 공식 계정 근거 확인과 개별 연결. [006](../specs/006-discography-links/tasks.md) T003
- [ ] 미연결 녹음 2,564개(Topic/레이블·미등록 가창 명의·Instrumental·라이브 버전 등)의 공식 근거 확인과 연결. 006 T004
- [ ] 오염된 곡·중복 영상·미확정 가창자 연결 검수와 남은 음악 데이터 반영. 덤프 집계와 조회 최적화가 데이터를 정제한 것은 아니다. [이관 결과](records/backend/setlist-migration-report.md)
- [ ] 발매 음원의 오리지널/커버 여부 검수 확대, source 계정이 없는 발매 영상의 업로더 근거·소유권 검수. [009](../specs/009-song-exploration/tasks.md) T004
- [ ] 오리지널 음악 분류: 미분류 음원 조사, 공식 영상 연결 보완, 분위기 근거 확대. [010](../specs/010-original-music-tags/tasks.md) T003, T005
- [ ] YouTube 오리지널: 미확정 후보·별도 유통 채널 검수(2026-11-22 공식 채널 138개 조사, 신규 녹음 40곡·영상 연결 14건 반영 후 잔여). [누락곡 보완 기록](records/data/youtube-original-backfill-2026-11-22.md), [012](../specs/012-youtube-original-daily/tasks.md)
- [ ] HONK THE HORN·NUROJUNK 진행자 미확정 방송 3개 검토. [013](../specs/013-shared-member-catalog/tasks.md)
- [ ] YouTube 커버 과거 수집의 전체 채널 순회 완료 여부 확인. [007](../specs/007-youtube-covers/tasks.md) T003
- [ ] 실제 콘텐츠의 영상 재생 가능 여부와 이미지 품질 검수. fixture 성공은 외부 플랫폼 실재생 보증이 아니다.

## 3. 기능 후속

범위가 정해지면 새 스펙으로 구체화한다.

| 영역 | 작업 |
| --- | --- |
| 관리 | 수집 설정·route·작업/전송 상태를 관리할 도구를 새로 설계한다(기존 `admin-web`·`web.bak`은 2026-11-23 삭제). 세트리스트 후보 검토·정정 UI/API 포함 |
| 인증 | 공개 읽기 인증과 관리 권한 분리. 현재 선택적 `X-API-Key`는 완성된 사용자 권한 체계가 아니다 |
| 사용자 | 로그인 기반 즐겨찾기 동기화(현재 브라우저 로컬 저장) |
| 아티스트 | 그룹 프로필의 구성원 생일 DTO·UI([003](../specs/003-artist-catalog/tasks.md) T005), 캘린더 상징색 적용, 프로필 이미지 크롭 |
| 공연 | 여러 티켓 차수 표시 |
| 곡 | 공식 커버·노래방 번호·곡 상세 화면, 대규모 통계의 서버 페이지·검색·정렬([009](../specs/009-song-exploration/tasks.md) T005) |
| 수집 | YouTube 조회수 정기 갱신 주기·예산 확정(현재 명시적 CLI), 최근 10개 업로드 밖의 미발견 예약 방송 discovery, Holodex 미등록 채널 보완 |
| 이미지 | 이미지 큐의 `/ready` 통합, 수동 이미지를 보존하는 선택적 주기 갱신([004](../specs/004-avatar-storage/tasks.md) T004~T005) |
| 성능 | 인증 범위를 지키는 조회 응답 캐시. 곡 별칭 수·검색 부하가 늘면 부분 검색 인덱스를 실측 후 검토. 외부 작업 발견 지연(최대 약 15분)이 문제가 되면 DB 외부 깨우기 검토 |

## 4. 레거시 정리

- [ ] `/api/v2` 숨김 별칭·임시 호환 경로·중복 설정 제거.
- [ ] Google 연동과 마운트하지 않은 구 라우터의 legacy 격리 또는 삭제, 원격 봇 명령 정리. 기존 서비스 사용 종료를 확인한 뒤 단계적으로 진행한다.

구 라우터에만 있는 기능은 다음과 같다. 코드가 남아 있어도 호출 가능한 서비스로 간주하지 않으며, 필요하면 신규 service와 보호된 관리 작업 계약으로 다시 만든다.

| 구 기능 | 쓰였던 용도 |
| --- | --- |
| `GET /api/youtube-performance-stats` | 전체 상위 200개 집계. 현재 아티스트별 통계와 기준이 다름 |
| `GET /api/youtube-covers` | artist_id/collaborator_id 필터 커버 목록 |
| `GET /api/youtube-performance-filters` | 다중 조건 검색 UI의 후보 목록 |
| `GET /api/artist-agencies` | 소속사 필터 |
| 아티스트·소속사·소스 POST/PATCH/DELETE | 관리자 등록·수정 |
| `POST /api/event-candidates` | 공연 후보 등록 |
| `POST /api/youtube-lives`, `/api/youtube-lives/backfills` | 영상 등록·과거 수집(진행 조회 계약 없음) |
| `PATCH /api/youtube-performances/{id}` | 세트리스트 메타데이터 교정(타임스탬프 수정 미지원) |
| Spotify 아티스트 목록·후보·프로필, sync·youtube-auto-link·enable·exclude, relationships | Spotify 등록·매칭·노출 설정, 공동 발매 관계 |
| songs/from-youtube·spotify-track-youtube·credits 변경 | 가사 생성·곡 연결·크레딧 관리 |
| Google auth/start·callback | Google Calendar 계정 연동 |

## 5. 향후 버전: 곡 기준 탐색·통계

사용자 요청으로 남긴 다음 버전 범위다. 현재 화면 구현 범위에는 포함하지 않으며 구조는 [DB 구조 계획](plans/db-renewal-plan.md), 곡 마스터 구축과 `performances.song_id` 연결 순서는 [곡 마스터 구축 계획](plans/song-master-plan.md)을 따른다.

- 목표: 곡 목록·상세, 해당 곡을 많이 부른 아티스트, 월별 가창 추이, 곡 정보.
- 제목 문자열만으로 같은 곡을 집계하지 않는다. 원곡자는 세부 역할 없이 복수 명의로, 합동 가창은 실제 가창자 관계로 연결한다. 미매칭 가창은 nullable song_id와 원문을 보존한다.
- 집계 단위는 한 번의 가창이며 메들리·반복·부분 가창·합동 가창·재업로드·버전 합산 기준을 먼저 정한다.
- 월별 추이는 수집량 증가를 인기 상승으로 오인하지 않도록 전체 수집 가창 대비 비율 제공 여부를 검토한다.
- 구 DB의 곡·가사는 이전 대상이 아니며 기존 DB에 보존한다. 이전 즐겨찾기는 자동 승계하지 않는다.
- 노래방(song_id 구축 후)과 가사·번역·독음은 이 버전 이후의 TODO다.
