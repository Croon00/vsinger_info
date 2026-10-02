# 2026-10-02 아티스트 추가·우타와꾸 조사

상태: **조사 자료 준비, DB 반영·세트리스트 수집·번역 반영 미완료**.

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

## DB 호환성 차단과 남은 작업

연결된 신규 DB는 `catalog-v2`, revision `001`–`007`이다. 이 체크아웃은
`catalog-v2`를 사용하지만 migration 파일과 runtime의 `SUPPORTED_REVISIONS`는
`005`까지다. `catalog_runtime_session()`이 `CatalogIdentityError`로 중단했다.
단순히 지원 revision 목록을 늘리거나 기존 보호 장치를 우회하지 않았다.
`RUNTIME_CUTOVER_ENABLED`, `AGENT_ENABLED`도 현재 false다. DB 쓰기는 수행하지 않았다.

피가로(artist 941/account 218), shin(942/219), 히비쿠(943/220)는 이미 있다.
2026-10-02 읽기 전용 확인 결과:

| 아티스트 | 저장 방송 | 가창 행 | song_id 연결 | 한국어 곡명 연결 | 해당 가창자 연결 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 피가로 | 5 | 91 | 0 | 0 | 0 |
| shin | 5 | 182 | 58 | 40 | 0 |
| 히비쿠 | 5 | 124 | 0 | 0 | 0 |

현재 조회 통계는 `performance_artists`에 해당 아티스트가 연결된 행만 집계한다.
새 수집기는 채널 소유자를 방송 진행자로 연결하지만 곡별 가창자로 자동 복사하지
않는다. 따라서 방송을 추가하는 것만으로 요청한 가창 통계가 완성되지 않는다.
댓글·방송 설명의 가창 근거를 확인하고 공동 방송의 가창자를 구분해야 한다.

한국어 곡명은 현재 조회 API의 `songs.title_ko`를 통해 표시한다. 구 DB의
`youtube_archive_labels`/`translate_recent_youtube_setlists`는 정상 신규 경로가
아니므로 실행하지 않았다. 호환 코드가 확보된 뒤 대상 채널에 한해 기존 확정
`song_match_keys` 연결, 미연결 곡 검수, 빈 `title_ko` 번역·검증을 수행해야 한다.
원문·기존 한국어 제목은 보존하고 별개의 곡을 제목만으로 병합하지 않는다.

진행에 필요한 정보는 006/007을 포함한 호환 코드의 브랜치/작업 경로와 미란 채널의
대상 확인이다. 탄산수의 이름·채널 확인은 완료됐다. 그 뒤 소속·owner 충돌을 확인한 등록, 공개 후보 영상 실제 라이브
검증, 200 ID 이하의 명시적 작업 등록, 세트리스트 수집, 가창 근거 확인, 곡 연결·번역,
조회 API/화면의 통계 검증 순서로 이어간다.

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
