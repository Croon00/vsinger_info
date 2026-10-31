# 猫 The Sappiness 등록 — 2026-11-01

사용자가 지정한 YouTube 고정 ID `UCQm--lgPz5Sq_b5hW9UXXQQ`는 기존 external_accounts에 없었다. 공식 channels.list 및 [공식 사이트](https://nekothe.com/)를 확인해 `猫 The Sappiness` / `Neko The Sappiness`로 신규 등록했다. 검증된 한국어 표기와 소속사 분류는 없어 비워 두었다. 등록 기준은 [seed](../data/seeds/nekothe_2026_11_01.json)에 둔다. 실제 신규 DB artist_id=1022, YouTube account_id=332, slug=`neko-the-sappiness`다. 기존 아티스트와 이름만으로 병합하지 않았다.

공식 API 구독자 144,000명, 채널 생성일 2024-03-21을 저장했다. 공식 사이트 생일의 월일 4월 20일을 사용했다. 초기 아바타 worker는 S3 `NoSuchBucket`으로 업로드 재시도 상태이므로 공식 YouTube 공개 thumbnail URL을 프로필에 저장하고 변경 출처를 감사 이력에 기록했다. 저장소 오류를 해결한 것으로 간주하지 않는다.

## 수집 결과

공식 업로드 목록을 14페이지, 공개 API로 조회 가능한 영상 672개까지 끝까지 확인했다. 비공개·삭제 등으로 videos.list에서 반환되지 않는 항목은 만들지 않았다. 호출 간격 2초로 확인했고 기존 source ID·URL을 보존했다.

- 커버 후보 245개 저장, 조회수 245개 갱신. Shorts 214개 제외, 일반 커버 31개 표시. 길이 180초 이하 후보를 대상으로 제목 표식 31개와 공개 URL 형식 186개를 확인했다. 180초 초과 일반 후보 28개와 짧은 일반 영상 3개가 표시된다.
- 우타와꾸 후보 15개를 기존 typed youtube_collect 작업으로 등록했다. 최초 작업 15개 처리 후 라이브 13개, 가창 50개가 저장됐다. 이 중 1개 라이브는 추출 재시도 대기다. 추가 2개 영상도 공개/완료 상태 대기 후 재시도하며, 총 pending 3개다. 이 수치를 전체 추출 완료로 해석하지 않는다. 원곡 아티스트가 없는 원문은 기존 곡 탐색 규칙에 따라 제외되어 곡 탐색의 우타와꾸 검색 결과는 33묶음이다.
- [공식 Discography](https://nekothe.com/discography/)에 명시된 싱글/참여곡 7개와 1st EP 3곡을 합해 오리지널 10곡·발매 8개를 수동 근거 manifest로 저장했다. 공식 MV 8개에 영상 ID·등록일·길이·조회수를 연결했다. EP의 BORN·My Baby는 확인된 MV가 없어 영상 미연결 상태로 유지한다. Spotify 토큰 발급이 실패해 Spotify에서 수집한 데이터라고 기록하거나 외부 ID를 추정하지 않았다. 원곡 작품 song_id는 미확정으로 두며 recordings/발매/가창 명의만 저장했다.

신규 아티스트/계정과 발매·녹음·영상·이미지 변경은 catalog_imports/catalog_changes에 근거와 함께 기록했다. 오리지널 반영 receipt=7493. X·Discord route·일정은 생성하지 않았다. 조회 API에서 수집을 시작하지 않는다.

## 실행 상태와 검증

YouTube 계정은 collection_enabled=true로 등록했다. 현재 로컬 기본 환경은 RUNTIME_CUTOVER_ENABLED/AGENT_ENABLED가 false여서 전역 정기 worker가 활성화된 것으로 간주하지 않는다. 사용자 요청의 초기 수집은 별도 프로세스에서만 두 플래그를 활성화해 실행했다. 남은 작업은 요청 라벨 `nekothe-2026-11-01`만 처리하는 숨김 worker가 재시도 시각을 기다린다. 전역 설정은 변경하지 않았다. 로그는 Git 제외 `.tmp/nekothe-worker.stdout.log`, `.tmp/nekothe-worker.stderr.log`다. 초기 실행본과 API는 각각 독립적이며 PC/프로세스 종료 후 지속 실행을 보장하는 서비스 등록은 이번 작업에 포함하지 않았다.

실제 신규 DB와 로컬 HTTP에서 아티스트 200·이미지·구독자·채널 생성일, 개인 커버 31개, 전역 커버 검색 31개, 오리지널 검색 10개, 영상 ID 중복 없음과 우타와꾸 50가창 저장을 확인했다. `/api/artists/1022`, `/api/artists/1022/covers`, `/api/explore/songs?kind=original&q=Neko%20The%20Sappiness`가 200으로 응답했다. 이는 fixture 테스트가 아닌 실제 읽기 검증이다. 코드/스키마 변경은 없다.
