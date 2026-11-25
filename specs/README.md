# UtaMowa 기능 스펙

2026-11-17 기존 문서를 바탕으로 도입했다. 번호는 문서 식별자이며 실행 우선순위는 사용자 요청과 roadmap을 따른다.

| 스펙 | 범위 | 현재 판정 |
| --- | --- | --- |
| [001-service-readiness](001-service-readiness/spec.md) | 신규 DB 수집·알림 서비스 운영 전환 | 과거 로컬 검증 기록 있음, 운영 확인 작업 남음 |
| [002-live-multiview](002-live-multiview/spec.md) | 생방송 검색·상태 확인·멀티뷰 운영 연결 | 기존 구현 있음, 배포·운영 확인 작업 남음 |

## 신규 기능 스펙 (2026-11-21~)

| 스펙 | 범위 | 현재 판정 |
| --- | --- | --- |
| [011-home-recent-songs](011-home-recent-songs/spec.md) | 홈 최근 오리지널·커버 곡 | 로컬 구현·실데이터 조회 확인, 화면 검수·PostgreSQL fixture 남음 |
| [012-youtube-original-daily](012-youtube-original-daily/spec.md) | YouTube 오리지널 일일 수집 | 로컬 구현, DB fixture·운영 적용 남음 |
| [013-shared-member-catalog](013-shared-member-catalog/spec.md) | HONK THE HORN·NUROJUNK 멤버별 라이브·커버 | 실데이터 보완, 운영 후속 남음 |
| [014-original-song-availability](014-original-song-availability/spec.md) | 분류 파일 누락 시 오리지널 목록 복구 | 로컬 수정·회귀 검증 완료, 배포·운영 확인 남음 |
| [015-artist-spotify-genres](015-artist-spotify-genres/spec.md) | 아티스트 상세의 Spotify 아티스트 장르 | 로컬 구현·실데이터 저장 완료, 배포·화면 검수 남음 |
| [016-original-lyrics-review](016-original-lyrics-review/spec.md) | 오리지널 곡 가사 후보 수집과 검토 후 등록 | 후보·직접 입력 파일 생성, 검토·등록 대기 |
| [017-released-cover-exclusion](017-released-cover-exclusion/spec.md) | 오리지널 곡 목록에서 발매 커버 음원 제외 | 로컬 구현·실데이터 읽기 확인, 배포 남음 |

014는 2026-11-21 `003-original-song-availability`로 만들었으나 기존 `003-artist-catalog`와 번호가 겹쳐 2026-11-23 014로 바꿨다. 새 스펙은 기존 최대 번호 다음 번호를 쓴다.

각 디렉터리의 spec.md → plan.md → tasks.md 순서로 읽는다. 기존 검증의 건수는 기록 시점 값이다. 이번 도입의 검증 범위는 [스펙 작업 안내](../docs/spec-driven-development.md)에 기록한다.

다른 기능과 과거 기록의 연결은 [문서 지도](../docs/spec-driven-development.md), 전체 미완료 항목은 [roadmap](../docs/backend-roadmap.md)을 따른다. 새 기능은 별도 번호의 스펙을 만든다.

## 기존 작업 범위별 스펙 (2026-11-18)

기존 작업을 003~010으로 묶었다. 번호는 정리 순서이며 실행 우선순위·과거 작업 시점을 나타내지 않는다. 완료 기록은 원본 날짜의 근거이며 이번 정리에서 실데이터·배포를 재검증하지 않았다. 각 디렉터리의 spec.md → plan.md → tasks.md 순서로 읽는다.

| 스펙 | 범위 | 상태 |
| --- | --- | --- |
| [003-artist-catalog](003-artist-catalog/spec.md) | 아티스트 명의·공유 채널·탐색 정렬 | 과거 근거 이관, 후속 확인은 tasks.md |
| [004-avatar-storage](004-avatar-storage/spec.md) | 프로필 이미지 저장·초기 이미지 작업 | 과거 근거 이관, 후속 확인은 tasks.md |
| [005-catalog-registration](005-catalog-registration/spec.md) | 아티스트·공식 채널 등록과 자료 보완 | 과거 근거 이관, 후속 확인은 tasks.md |
| [006-discography-links](006-discography-links/spec.md) | Spotify 계정 탐색과 발매곡 YouTube 연결 | 과거 근거 이관, 후속 확인은 tasks.md |
| [007-youtube-covers](007-youtube-covers/spec.md) | YouTube 커버 분류·과거 수집·조회 | 과거 근거 이관, 후속 확인은 tasks.md |
| [008-setlist-quality](008-setlist-quality/spec.md) | 세트리스트 이전·후보 선택·가창 정정과 복구 | 과거 근거 이관, 후속 확인은 tasks.md |
| [009-song-exploration](009-song-exploration/spec.md) | 곡 탐색·세트리스트 검색과 조회 최적화 | 과거 근거 이관, 후속 확인은 tasks.md |
| [010-original-music-tags](010-original-music-tags/spec.md) | 오리지널 음원의 근거 기반 장르·분위기 필터 | 과거 근거 이관, 후속 확인은 tasks.md |
