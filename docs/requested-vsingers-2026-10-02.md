# 2026-10-02 아티스트 추가·우타와꾸 조사

상태(2026-10-04): **34/35개 YouTube 계정 등록과 수집 진행, 원문 근거가 있는 가창자 연결 33,271건 반영**.
미란 대상 확인, 보류·신규 가창 검수, 곡·한국어 제목의 미연결 부분, 작품·Spotify 반영은 남아 있다.

2026-10-03 사용자 정정으로 `사이다`는 `탄산수(炭酸水)`이며 공식 채널은
`https://www.youtube.com/@tansansuichan`임을 확인했다. 요청 목록은 총 35명이다. 입력 자료는
`data/seeds/requested_vsingers_2026_10_02.json`에 보존한다. 채널 ID는 실제 YouTube
Data API로 확인했다. 한국어 활동명은 요청 표기를 정리한 편집 표기이며 공식 한국어
이름으로 단정하지 않는다. `affiliation_status=verified`인 소속에는 공식 출처를
남겼다. 소속 미확인을 개인세로 자동 치환하지 않는다.

## 확인한 소속과 이름

- Re:AcT: 神凪アンナ, 杏夜くもり, 稀羽すう, 獅子神レオナ.
- UniVIRTUAL: 白玖ウタノ. 요청에서 그 아래에 나열된 다른 채널까지 같은 소속으로 묶지 않는다.
- ななしいんく: 龍ヶ崎リン. Rene는 로마자 표기로, 원어 활동명은 린이다.
- ミリプロ: 音ノ乃のの, 鹿乃まほろ. 제공된 카노 채널은 현재 鹿乃まほろ 이름을 사용한다.
- Mixstgirls: 渚沢シチ.
- スナックにり: 陽月るるふ, CYBILL.
- Varium: セレナーデ・オックスブラッド.
- ホロライブ: 角巻わため, AZKi, 星街すいせい.
- にじさんじ: 町田ちま, 戌亥とこ. 개별 프로필 출처의 검증 상태는 seed에 기록한다.
- Neo-Porte: 緋月ゆい. 요청의 하즈키 유이는 제공 채널 기준으로 히즈키 유이로 정리한다.
- StudioAbyss Inc.: 炭酸水. [2026-08-31 공식 공지](https://www.studioabyssinc.com/news/2026-tansansui-rurine-join/)에서 2026-07-01부터 마네지먼트 계약을 체결한 소속 아티스트임을 확인했다.
- NoiR는 음악 유닛 NoWorld 구성원이다. 유닛 관계와 소속사 관계를 구분한다.
- 茨むあん, 彷徨鈴은 본인 채널 설명에서 개인 활동을 확인했다. よしか⁂는 음반사 아티스트 소개에서 개인세를 확인했다.
- 그 밖의 확인 중인 소속, 레이블과 매니지먼트의 구분은 seed의 pending/candidate 상태를 유지한다.

제공된 `@MiRanOfficialChannel`은 채널 설명이 보컬·바이올린 연주자이며 공개 영상
4개에서 제목 규칙에 맞는 우타와꾸 후보는 0개였다. `天羽音みらん`과 같은 사람으로
추정하거나 채널을 교체하지 않았고 사용자 확인을 요청했다.

근거: [Re:AcT](https://www.v-react.com/), [미리프로](https://milpr.com/talents),
[스낵 니리](https://snacknili.com/), [Mixstgirls](https://mixstgirls.com/member/shichi-nagisawa),
[Varium](https://varium.jp/talent/serenade/), [Neo-Porte](https://neo-porte.jp/member/hizuki-yui).

## 수집 입력과 통계 파일

2026-10-02 실데이터 조사 결과: **34/34개 채널의 공개 uploads 목록 끝 페이지 확인,
30,389개 영상 목록, 제목 규칙 기반 노래방송 후보 9,999개**. 이 수는 실제 종료된
우타와꾸 방송·확보 세트리스트 수가 아니다. MiRan의 후보는 0개다.

2026-10-03 탄산수 추가 조사: 채널 ID `UCOZvymJrEDhlINeeTJ1SGjQ`, 공개 uploads
목록 488개, 제목 규칙 후보 387개. 당시 채널 통계는 구독자 8,770명·조회수
690,411회·공개 영상 수 552개다. API의 채널 영상 통계와 uploads 목록 수는
별도 값으로 보존한다. 전체 합계는 **35/35개 목록 끝 페이지 확인, 30,877개
영상 목록, 제목 규칙 후보 10,386개**로 갱신했다.

`scripts/prepare_requested_vsingers.py`는 DB·Discord·Calendar·LLM을 호출하지 않는다.
공식 YouTube API 읽기만 수행하며 30초 timeout, 호출 간격 최소 1초, 채널별 최대
400페이지/20,000개 상한을 둔다. 끝 페이지를 확인하지 못한 목록은
`listing_complete=false`이며 전체 수집 완료라고 기록하지 않는다. quota와 재시도
대상 오류에서는 다음 채널 호출을 중단하고 오류 사유만 기록한다.

```powershell
.\.venv\Scripts\python.exe scripts/prepare_requested_vsingers.py --max-pages 400
.\.venv\Scripts\python.exe scripts/prepare_requested_vsingers.py --report-only
```

출력은 Git에서 제외된 `db-migration/reports/requested-vsingers-2026-10-02/`에 둔다.

- 채널별 JSON: 공식 채널 이름·설명·ID·조회 시각·채널 통계·공개 업로드 목록.
- `channel-statistics.csv`: 한국어/원어 활동명, 소속 검증 상태, 구독자·조회수·공개 영상 수, 목록 수집 범위.
- `singing-candidates.csv`: 기존 수집기의 제목 규칙에 맞는 노래방송 후보 ID·제목·URL. Shorts나 일반 업로드도 섞일 수 있어 실제 종료된 라이브 여부는 추가 검증해야 한다.
- `summary.json`: 전체 목록 확보 여부와 DB 반영·세트리스트·한국어 제목의 미완료 상태.
- `existing-db.json`, `existing-statistics.json`: 신규 DB 읽기 전용 확인. 비밀 연결값이나 구 DB 자료는 포함하지 않는다.

채널 조회수·구독자 수는 가창 횟수 통계와 다르다. 후보 방송 목록이 확보되었다고
댓글 세트리스트·가창자·곡 연결이 확보된 것은 아니다. 비공개·삭제·회원 전용 영상은
공개 API로 전체 확보를 보장할 수 없다.

## 현재 DB 상태와 남은 작업

2026-10-02 조사 당시에는 체크아웃 지원 revision 005와 DB revision 007이 달라
DB 쓰기를 중단했다. **현재 HEAD `5f9eda6`은 `001`–`007`을 지원하며 실제 DB의
migration checksum도 일치하므로 이 차단은 해소됐다.** 로컬
`RUNTIME_CUTOVER_ENABLED`, `AGENT_ENABLED`가 false여도 다른 worker의 실행 상태를
뜻하지 않는다. 실제 DB에서 수집 작업 성공과 가창 행의 증가를 확인했다.

2026-10-04에는 요청 35개 중 34개 채널의 계정·단독 owner·수집 활성 상태가
등록돼 있다. MiRan은 미등록이다. 00:25 KST snapshot의 방송 2,831개·가창 후보
49,093행 중 32명·2,120방송·33,268가창에 `performance_artists` 33,271건을
반영했다. 원문·기존 곡 연결을 보존했으며 근거·검증·남은 범위는
[가창자 연결 기록](performance-artists-2026-10-04.md)에 있다.

피가로(artist 941/account 218), shin(942/219), 히비쿠(943/220)는 이미 있다.
2026-10-02 읽기 전용 확인 결과:

| 아티스트 | 저장 방송 | 가창 행 | song_id 연결 | 한국어 곡명 연결 | 해당 가창자 연결 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 피가로 | 5 | 91 | 0 | 0 | 0 |
| shin | 5 | 182 | 58 | 40 | 0 |
| 히비쿠 | 5 | 124 | 0 | 0 | 0 |

위 표는 2026-10-02의 과거 조사값이다. 2026-10-04 실제 DB와 현재 HEAD API에서
피가로 77회·shin 2,894회·안나 896회·탄산수 27회를 확인했다. 히비쿠 124행은
원문상 정보·잡담 타임스탬프이므로 가창자로 연결하지 않았다.

현재 조회 통계는 `performance_artists`에 해당 아티스트가 연결된 행만 집계한다.
2026-10-04 후속 사용자 요청으로 새 수집 가창에 단일 활성 채널 owner를 임시
가창자로 자동 연결하도록 구현했다. 그룹·공동 방송 여부는 판정하지 않는다.
owner가 없거나 여러 명이면 연결하지 않으며 기존 가창·수동 크레딧은 보존한다.
정책은 [YouTube 수집 계약](backend-service-step-3-youtube.md)에 있다. 로컬 검증은
완료했으나 배포된 worker의 새 코드 실행은 확인하지 않았다. 이전 보류·미연결 행의
추가 반영과 실제 곡별 가창자 교정은 별도 작업이다.

한국어 곡명은 현재 조회 API의 `songs.title_ko`를 통해 표시한다. 구 DB의
`youtube_archive_labels`/`translate_recent_youtube_setlists`는 정상 신규 경로가
아니므로 실행하지 않았다. 2026-10-03 읽기 전용 감사에서 요청 채널의
가창 45,685행 중 `song_id` 16,240행·한국어 곡명 12,316행은 이미 연결되어 있었다.
이는 당시 snapshot 값이며 전체 완료를 뜻하지 않는다. 미연결 곡 검수와 빈
`title_ko`의 근거 있는 표기 반영은 후속 작업이다.
원문·기존 한국어 제목은 보존하고 별개의 곡을 제목만으로 병합하지 않는다.

남은 작업은 미란 채널 대상 확인, 보류·신규 가창의 곡별 근거 검수, 잘못 파싱된
정보 행 교정, 미연결 곡·한국어 제목, 작품·Spotify 자료 반영과 실제 화면 검증이다.
탄산수 이름·채널 확인과 006/007 호환 코드 확보는 완료됐다.

## 작품 자료

최초 예고의 `タイトル未定` 대신 후속 공식 공지를 확인했다. 준비 seed에는
神凪アンナ의 [相対性インソムニア](https://www.v-react.com/archives/4425)
(2026-09-13), 杏夜くもり의 [くもりのあしあと](https://www.v-react.com/archives/4402)
(2026-08-30), 稀羽すう의 [Dive iN·seaglass](https://www.v-react.com/archives/4073)
정보와 출처가 있다. 아직 음반·녹음·곡 테이블에 반영하지 않았다.
獅子神レオナ는 [공식 작품 목록](https://www.v-react.com/archives/artist-name/shishigami-reona)의
개인 명의 앨범·싱글 10개를 조사 자료로 보존했다. 작품 목록의 날짜와 실제 발매일은
개별 작품 페이지 확인 전까지 구분하며 공동 명의 작품을 단독 작품으로 등록하지 않는다.

## 검증

2026-10-02 fixture 테스트: `tests/test_prepare_requested_vsingers.py` **3 passed**.
중복 영상 제거, 다른 채널 소유 영상 제외, 페이지 상한의 미완료 표시, quota 시
다음 채널 호출 중단과 잘못된 채널 ID 거부를 확인했다. 실제 API 조회와 신규 DB 읽기 전용 조사는 별도
실데이터 조사이며 fixture 테스트의 성공을 DB 적용·서비스 수집 성공으로 해석하지 않는다.
