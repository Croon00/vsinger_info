# YouTube 오리지널 일일 수집 계약

2026-11-22 로컬 구현. [012 요구·설계·작업](../specs/012-youtube-original-daily/spec.md)을 따른다. DB fixture와 운영 worker 적용은 미완료다.

같은 날 후속 요청으로 과거 누락곡을 명시적으로 조사·반영했다. [실제 보완 기록](records/data/youtube-original-backfill-2026-11-22.md): 신규 40곡·기존 공식 영상 연결 14건. 아래 최초 구현 검증과 실제 반영을 구분한다. 일일 worker 운영 배포는 아직 하지 않았다.

## 주기와 대상

기존 YouTube 수집의 YOUTUBE_POLL_INTERVAL_SECONDS 기본 86400초를 공유한다. 활성 external_accounts의 고정 채널 ID·owner 관계를 사용하며 uploads 최대 4페이지/200개를 확인한다. 최초 youtube_baseline_at 이전 영상은 자동 과거 수집하지 않는다. 조회 API는 수집하지 않는다.

기존 커버·노래 방송 분류를 우선하고 남은 일반 업로드를 purpose=original 검증 작업으로 넘긴다. 후보가 곧 오리지널은 아니다. 예약/진행·비공개/공개 미확인·미래/미확인 게시일·커버·티저/노래 방송/Shorts 표기·버전 차이는 자동 등록하지 않는다.

## 판정과 저장

제목에 original·official이 없어도 등록 owner의 기존 발매 음원과 채널·완전한 곡명 필드·버전·길이가 유일하게 일치하면 녹음에 영상을 연결한다. Spotify 외부 ID를 요구하지 않으므로 공식 YouTube 자료로 등록했던 녹음도 대상이다. 여러 음원 후보·다른 기존 공식 영상·제목 일부 일치만으로는 연결하지 않는다. 기존 오리지널 탭에 미확정 발매가 포함되는 계약은 유지하며 영상 연결 자체가 모든 발매의 오리지널 여부를 인증하지는 않는다.

기존 녹음과 연결되지 않는 새 곡은 제목의 명시적 original/오리지널 표기 또는 설명 첫 20줄에서 현재 곡명을 인용한 오리지널 안내가 있어야 한다. 설명의 Vocal/歌唱/歌/Artist 등 가창 크레딧이 등록 owner의 정확한 이름·별칭과 일치해야 한다. official/MV만으로 새 음원을 만들지 않으며 미등록 협업자는 추측하지 않는다. 제목을 유일한 인용 제목으로 분리할 수 없으면 영상 제목을 보존한다. 앨범·발매일·song_id를 추측해 만들지 않는다.

최종 정책 `youtube-original-evidence-3`은 설명의 정확한 곡 태그(originalsong/originalmusic/オリジナル曲)와 `Vocal & Movie` 복합 필드도 읽는다. `Original MV/オリジナルMV`만으로는 창작곡 근거가 되지 않는다. 알려진 그룹 이름 뒤 괄호 멤버 표기는 그룹 명의로만 연결하고 개별 명의를 만들지 않는다. 90초 미만/길이 미상·short.ver·1Chorus·홍보/티저 표기는 자동 등록하지 않는다.

purpose=original typed 작업은 기존 archive/cover payload와 key를 바꾸지 않는다. 공유 연결 풀·작업별 Session·계정/영상·lease·영상별 잠금·snapshot을 사용하고 저장 직전에 owner/명의·대상 녹음을 다시 확인한다. 같은 영상의 기존 녹음·cover/archive·보관 행·수동 링크는 보존한다. 원문 설명·영상/채널 ID·판정은 source_documents에, 녹음/가창 생성이나 영상 연결의 전후 값·출처는 catalog_imports/catalog_changes에 저장한다.

미확정은 review_candidate로 보존하며 일반 poll이 완료된 동일 후보를 무한 재처리하지 않는다. 재검토는 명시적 요청이 필요하다. 새 앨범 없이도 녹음·명의·영상으로 기존 오리지널 목록/홈에서 조회한다. OpenAI·댓글·Spotify·Discord·Calendar·가사/번역 호출은 추가하지 않는다.

## 운영 적용과 검증

새 purpose가 생기므로 poll·collect worker 모두 업데이트한 뒤 실행해야 한다. API만 켜거나 구버전 worker를 유지한 상태는 적용 완료가 아니다. 이번 작업에서 runtime guard·서버 환경변수·DB schema·배포 프로세스는 바꾸지 않았다.

2026-11-22 관련 fixture/회귀 122 passed, PostgreSQL 의존 106 skipped. 실제 DB의 scope SELECT만 읽기 전용 확인했으며 실제 신규 곡 수집·DB 반영·모델 호출·운영 배포는 하지 않았다. [남은 작업](../specs/012-youtube-original-daily/tasks.md).

최종 세트리스트 규칙·댓글 형식 포함 회귀는 241 passed, 106 skipped이며 git diff --check를 통과했다. DB fixture·운영 적용은 여전히 미완료다.
