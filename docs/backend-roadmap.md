# 백엔드 후속 작업

갱신: 2026-09-23. 현재 계약은 [통합 조회 API](read-api-v2.md), 실행 구조는 [백엔드 구조](backend-architecture.md), 웹 검증은 [QA](../web/docs/qa.md)에 있다. 구조 변경의 기준은 [백엔드 통합 최종 계획](backend-consolidation-plan.md)이다. **운영 DB 선택 이전은 완료했으나 전체 서비스 활성화·검증은 미완료**이며 [운영 DB 이전 기록](backend-cutover-2026-09-23.md)에 현재 상태를 적었다. 최신 결함·누락 기능·개발 순서는 [서비스 검증과 보완 개발 계획](backend-service-readiness-plan.md)에 모은다.

통합 `/api`는 새 Neon의 아티스트·라이브·검색·통계·공연·앨범·가사를 조회한다. X poller와 최소 Discord sender의 신규 DB 코드는 구현됐고 선택 상태 이전도 수행했다. Discord 활성화와 실제 전송 검증은 남아 있다. 미지원 데이터는 실제 화면에서 목업으로 보충하지 않는다.

## 백엔드 통합 구현 순서

세부 범위·완료 조건·검증·복구는 [최종 계획](backend-consolidation-plan.md)에 모은다. 완료 항목과 남은 구현 순서를 함께 관리한다.

- [x] 1. [선택 이전 조사](backend-phase-1-baseline.md): X 매핑·활성 상태·잘못된 source 제외, `Hao_RKM` 병합 범위, YouTube 서브 채널 등록, 최소 행·필드 및 writer 후보 목록 확정. 미해결 매핑 충돌 0개.
- [x] 2. [운영 스키마·연결 기반](backend-phase-2-runtime-schema.md): 신규 DB에 `002` 계정 상태·원문·route·delivery·작업·이전 영수증 schema 적용, 공통 Settings·identity/revision guard와 legacy init 차단. 기존 DB 변경 없음.
- [x] 3. [선택 이전 도구·검증](backend-phase-3-runtime-migration.md): 실데이터 읽기 전용 dry-run, snapshot/manifest, 참조·제외 집합, 로컬 원자 적용·영수증·재실행 중복 0 검증. 실제 적용 결과는 [운영 DB 이전 기록](backend-cutover-2026-09-23.md)에 있다.
- [x] 4. 수집기·최소 Discord sender 로컬 전환: [X/Discord 보완 1단계](backend-service-step-1-runtime.md), [독립 작업 실행기](backend-service-step-2-jobs.md), [YouTube 신규 DB 수집](backend-service-step-3-youtube.md), [등록된 Spotify 계정 수집](backend-service-step-4-spotify.md)을 구현·검증했다. 실제 운영 검증은 전환 시 수행한다.
- [x] 5a. 정식 `/api` 계약과 신규 프론트 통합, legacy router 미마운트, `RUNTIME_CUTOVER_ENABLED` 배포 잠금.
- [ ] 5b. [서비스 보완 A~F](backend-service-readiness-plan.md) 완료 후 선택 이전까지 수행했다. 신규 DB runtime의 실제 수집·Discord 활성화와 장애 확인이 남았다. [이전 기록](backend-cutover-2026-09-23.md)과 [전환 순서](backend-phase-5-cutover.md)를 따른다.
- [ ] 6. `/api/v2`·임시 호환 경로·중복 설정 제거, Google 및 구 API/UI legacy 격리, 원격 봇 명령 정리·운영 검증.
- [ ] 별도 후속: admin-web에 수집 설정·route·작업/전송 상태 관리 추가. 현재 개발에서는 앱이 없는 것으로 취급하고 관리 API·연동도 제외.

admin-web은 이번 개발에서 없는 것으로 취급한다. YouTube·등록된 Spotify 계정의 수집·저장 service와 작업 실행기는 로컬 검증했다. [보완 5단계](backend-service-step-5-migration.md)에서 채널 processed/아카이브 pending 재개 선택과 단일 DB 설정을 보완했다. 노래방·가사·번역·독음은 후속 TODO로 제외한다.

## 새 카탈로그 연결 후 남은 작업

2026-09-20 아티스트 원어/한국어/별칭·독립 이미지·생일, 영구 ID 기반 라이브·가창 연결, 공연 도시·시간대, DB 앨범·가사 조회를 새 사용자 웹에 연결했다. 검수된 자료를 DB에 반영하면 조회할 수 있으며 미등록 데이터는 빈 상태로 표시한다.

- [ ] 남은 음악 데이터 검수·반영과 임시 가창자 연결 보완. 2026-09-21 세트리스트·임시 가창자 등의 반영 범위는 [이관 결과](setlist-migration-report.md)에 기록되어 있다. 전체 초기 데이터가 미반영 상태인 것은 아니며 공연/앨범/가사 수집·반영은 조회 API가 자동으로 수행하지 않는다.
- [ ] 그룹 프로필에서 구성원 생일을 함께 표시하는 관계 DTO·UI.
- [ ] 캘린더의 실제 아티스트 상징색 적용, 프로필 이미지 크롭 설정.
- [ ] 여러 공연 티켓 차수 표시, 공식 커버·노래방 번호·곡 상세 화면.
- [ ] 대규모 통계의 서버 페이지·검색·정렬. 현재 집계 전체를 받고 프론트에서 10개씩 표시한다.
- [ ] 공개 읽기 인증과 관리 권한 분리, 운영 동일 출처 /api 프록시. 현재 선택적 X-API-Key는 완성된 사용자 권한 체계가 아니다.
- [ ] 로그인 기반 즐겨찾기 동기화. 현재 브라우저 로컬 저장이며 새 DB용 즐겨찾기 키를 분리했다.
- [ ] 실제 콘텐츠의 영상 재생 가능 여부 및 이미지 품질 검수. fixture 성공은 외부 플랫폼 실재생 보증이 아니다.

## 데이터 품질과 운영 경로

- [ ] [최종 통합 계획](backend-consolidation-plan.md)에 따라 신규 DB 하나로 운영한다. 필수 상태는 이전했고 기존 DB는 보존한다. YouTube·등록된 Spotify 계정 수집은 로컬 검증했으며 X provider 오류와 Discord 실제 전송 검증이 남아 있다. 이미 반영된 음악 자료는 유지한다.
- [x] 2026-09-20 [로컬 카탈로그 관리자](admin-web-plan.md) 1차 구현: JSON/수동 초안, 원본 비교, 승인·미리보기·원자적 반영, 수동 수정·보관·백업. 초기 데이터는 사용자 검수 전이며 전문 세트리스트 편집기·중복 병합은 후속 작업이다. 새 조회 API 전환은 완료했다.
- [ ] 오염된 곡·중복 영상·미확정 가창자 연결을 실제로 검수한다. 덤프 집계와 조회 최적화가 데이터를 정제한 것은 아니다. 재수집/로컬 LLM 실행은 별도 작업이며 원문·외부 ID·출처·생성 버전을 보존한다.
- [x] X 실행 경로의 분류·공연 추출·Calendar·YouTube 자동 등록을 제거했다. X는 신규 DB 원문 저장과 Discord 원문 URL 전송으로 끝나며 독립 YouTube setlist/음악 integration은 별도 모듈로 유지한다. Google 데이터는 구 DB에 보존하고 정상 실행 경로의 코드는 legacy 설정으로 격리했다.
- [ ] 기존 서비스 사용 종료가 확인되면 중복 API·호환 경로·레거시 읽기 부작용을 단계적으로 제거한다.

## 구 API 모듈에 남은 기능과 전환 대상

아래 구 경로는 현재 정상 앱에 마운트되지 않는다. 코드가 남아 있다는 이유로 호출 가능한 서비스로 간주하지 않는다. 같은 의미의 조회 기능은 현재 `/api` 계약에서 확인하고, 보존할 수집/변경 기능은 신규 service·보호된 관리 작업 계약으로 전환한다. Google 연동은 legacy 격리 대상이다.

| API 또는 기능                                             | 미사용 이유 / 활용 위치                                                 |
| --------------------------------------------------------- | ----------------------------------------------------------------------- |
| `GET /api/youtube-performance-stats`                      | 전체 상위 200개 집계이며 현재 아티스트별 통계와 기준이 다름.            |
| `GET /api/youtube-covers`                                 | 커버 업로드 화면을 추가할 때 활용. artist_id/collaborator_id 필터 있음. |
| `GET /api/youtube-performance-filters`                    | 다중 조건 검색 UI의 후보 목록. 현재는 자유어 검색.                      |
| `GET /api/artist-agencies`                                | 현재는 조회된 아티스트의 소속사만 필터에 사용.                          |
| 아티스트·소속사·소스 POST/PATCH/DELETE                    | 관리자 등록/수정 UI.                                                    |
| `POST /api/event-candidates`                              | 관리자 공연 후보 등록.                                                  |
| `POST /api/youtube-lives`, `/api/youtube-lives/backfills` | 영상 등록·과거 수집. backfill은 202 응답, 작업 진행 조회 계약 없음.     |
| `PATCH /api/youtube-performances/{id}`                    | 세트리스트 메타데이터 교정. 타임스탬프 수정은 현재 요청 모델 미지원.    |
| Spotify 아티스트 목록·후보·프로필 조회                    | 등록·매칭 관리.                                                         |
| Spotify sync·youtube-auto-link·enable·exclude             | 관리자 데이터 준비·노출 설정. 페이지 방문으로 실행하지 않음.            |
| `GET /api/spotify/relationships`                          | 공동 발매 관계 화면.                                                    |
| songs/from-youtube·spotify-track-youtube·credits 변경     | 가사 생성·곡 연결·크레딧 관리.                                          |
| Google auth/start·callback                                | Google Calendar 계정 연동. 웹 사용자 로그인 기능과 다름.                |

Discord 라우팅·수집 worker·Google Calendar 동기화는 새 프론트 네 메뉴의 직접 HTTP 소비 범위 밖이다. 내부 기능이 존재하는 것을 웹용 HTTP API 제공으로 간주하지 않았다.


## 향후 버전: 곡을 기준으로 탐색·통계 (사용자 요청)

현재 버전의 화면 구현 범위에는 포함하지 않는다. 새 구조의 상세 기준은 [DB 구조 계획](db-renewal-plan.md)에 모으고 아래에는 남은 화면·조회 작업을 둔다.

- 목표: 곡 목록 및 상세, 해당 곡을 많이 부른 아티스트, 월별 가창 추이, 곡 정보.
- 기존 songs는 YouTube/Spotify/가사 중심이며, youtube_song_performances에는 이를 참조하는 song_id가 없다. 제목 문자열만으로 동일 곡을 집계하지 않는다.
- 확정된 통합 명부와 계획된 곡/녹음 분리 구조를 구현한다. 원곡자는 세부 역할 없이 복수 명의로, 합동 가창은 실제 가창자 관계로 연결하며 탐색 노출 여부와 독립적으로 등록한다.
- 미매칭 가창의 nullable song_id와 원문 보존은 DB 계획에 따른다. 운영 호환에 필요한 구 DB→Catalog ID 대응은 최종 통합 계획에 따라 검증해 보존하되 이전 즐겨찾기 자동 승계는 이번 범위에서 제외한다. 원어/한국어/영문 필드로 곡을 검색하고 곡 별칭은 후속 확장으로 남긴다.
- 구 DB의 곡·가사는 이번 이전 대상에서 제외하고 기존 DB에 보존한다. 이 후속 화면에서는 신규 DB에 반영된 자료를 사용한다. 추가 음악 데이터 이관은 현재 계획에 포함하지 않는다.
- 집계 기준: 한 번의 가창을 기본 단위로 정의하고, 메들리·반복·부분 가창·합동 가창·재업로드 처리 및 버전 합산 기준을 명시한다.
- 월별 추이는 가창 횟수와 별개로 전체 수집 가창 대비 비율을 제공할지 검토한다. 수집량 증가를 곡 인기 상승으로 오인하지 않도록 기준을 설명한다.
- 현재 단계에서는 관계와 이전 경로만 준비한다. 곡 상세 UI·완성된 통계 API·별도 검색 시스템은 이후 범위다.
- 곡 마스터 구축·`performances.song_id` 연결 순서와 표기 규칙은 [곡 마스터 구축 계획](song-master-plan.md)을 따른다.
