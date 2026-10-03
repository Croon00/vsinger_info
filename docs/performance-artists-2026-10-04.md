# 2026-10-04 요청 아티스트 가창자 연결

사용자 요청에 따라 신규 DB의 `performance_artists`를 반영했다. 기준 HEAD는
`5f9eda666a396d4670b16e5b3073c9d00a132fcc`이며, DB revision `001`–`007`과
체크아웃 migration checksum의 일치를 확인했다. 구 DB는 사용하지 않았다.

## 반영 결과

2026-10-04 00:25 KST snapshot의 요청 채널 34개, 방송 2,831개, 가창 후보 행
49,093개 중 **32명·2,120방송·33,268가창에 가창자 관계 33,271건**을 추가했다.
34개 배치의 영수증(import 1133–1166)과 행별 `catalog_changes` 33,271건에
출처 문서 ID·해시·원문 행·판정 근거를 남겼다. dry-run과 실제 반영 모두 충돌·생략 0건이다.

단독 방송 33,259가창은 공개된 노래방송 제목, 가창자 이름·노래방송 시리즈 태그·
동일 영상 설명의 자기소개, 종료된 라이브 기록, 곡 목록 원문을 함께 확인한
**문맥 기반 연결(`contextual`)**이다. 채널 owner만으로 연결하지 않았으며 모든 곡의
음성을 직접 확인했다는 의미는 아니다. 정보·잡담 타임스탬프와 곡임을 확인하기
어려운 행은 제외했다.

Nornis 방송 `aqqBywjBUZg`(archive 5881)은 영상 설명의 `@MachitaChima`와 댓글의
`(町)`, `(戌)`, `(2人)`을 대조했다. 치마 단독 3곡, 토코 단독 3곡, 합창 3곡에
총 12건을 `source_row_verified`로 연결했다. `(2人+)`는 추가 가창자가 불명확해
보류했다. 합창의 `lead`/`guest`와 순번은 대표 진행자·참여자 저장 순서이며 보컬 비중 판정이 아니다.

## 실제 DB 및 조회 검증

2026-10-04 00:48 KST 읽기 전용 검사에서 계획 대비 누락·추가 관계 0건,
원문·시각·곡 연결·출처 문서 해시 변경 0건, 보류 행의 가창자 연결 0건을 확인했다.
현재 HEAD FastAPI TestClient와 실제 신규 DB에서 통계 GET 및 연결 방송 상세 GET을
검사했다. 배포된 브라우저 화면과 실제 영상 재생은 이 검증에 포함하지 않는다.

| 아티스트 | API 가창 횟수 | 세트리스트 연결 방송 |
| --- | ---: | ---: |
| 神凪アンナ | 896 | 59 |
| Figaro | 77 | 5 |
| shin | 2,894 | 79 |
| 炭酸水 | 27 | 3 |
| 町田ちま | 36 | 4 |
| 戌亥とこ | 21 | 3 |
| 音魂ヒビク | 0 | 0 |

위 7명의 통계 응답은 모두 200이고 DB의 연결 수와 일치했다. 연결이 있는 6명은
방송 상세 응답 200과 해당 가창 행의 노출도 확인했다.
실제 DB에서 같은 manifest를 다시 읽기 전용 검사한 결과 34개 배치 모두
`already_committed`, 신규 연결 계획 0건이었다.

2026-10-04 로컬 임시 PostgreSQL fixture 테스트 **5 passed**:
읽기 전용 미리보기, 반영·동일 manifest 재실행, 기존 크레딧 보존, 변경된 근거 거부,
감사 기록 실패 시 전체 transaction 롤백, 명시적 합창의 복수 관계를 검증했다.
fixture는 실제 provider·운영 DB를 호출하지 않으며 위 실데이터 검증과 구분한다.

## 남은 범위

snapshot에서 15,825행은 보류했다. 곡 여부 추가 검수 9,604행, 가창자 신원 근거
추가 확인 3,218행, 공동 방송의 곡별 크레딧 확인 2,324행, 다른 등록 아티스트가
제목에 있는 방송 254행, 비곡 표기 264행, 정보 댓글 102행, 노래방송 제목 근거
미충족 59행이다. 비곡·정보 행을 가창으로 연결해 수치를 채우지 않는다.

히비쿠의 기존 124행은 원문상 방송 정보·잡담 타임스탬프여서 연결하지 않았다.
실제 곡 목록 확보와 잘못 파싱된 행의 별도 교정이 필요하다. nayuta는 이번 근거를
통과한 행이 없으며 MiRan은 DB 계정 미등록·요청 채널 대상 확인이 남아 있다.

수집 worker는 계속 실행 중이다. 00:48 검증 때 요청 채널 전체는 51,822가창 행,
그중 연결된 가창은 33,268행이었다. snapshot 이후 추가된 2,729행은 이번 manifest에
없다. 이 snapshot 반영 당시에는 새 수집 가창의 자동 연결이 없었다. 이후
2026-10-04 후속 사용자 요청으로 단일 활성 채널 owner를 새 가창의 임시 가창자로
연결하도록 구현했다. 공동 방송·그룹 여부는 판정하지 않는다. [수집 계약과 로컬
검증](backend-service-step-3-youtube.md)을 따르며 운영 worker 배포·실행 검증은 남아
있다. 기존 보류·미연결 행의 후속 연결, 미연결 `song_id`, 한국어 곡명, 작품·Spotify
반영은 별도 작업이다.

## 도구와 자료

`scripts/link_performance_artists.py`는 검토한 manifest를 적용하며 후보를 자동으로
선정하지 않는다. DB instance, 행 버전, 원문 해시·원문 행·영상·계정 관계를 다시
검증한다. 기존 크레딧과 변경된 근거는 건너뛰고 영수증으로 동일 작업을 중복 적용하지 않는다.
관계 삽입에 따른 부모 행 version 증가는 기존 schema trigger의 정상 동작이다.

```powershell
.\.venv\Scripts\python.exe scripts/link_performance_artists.py --manifest MANIFEST.json --output dry-run.json
.\.venv\Scripts\python.exe scripts/link_performance_artists.py --manifest MANIFEST.json --output apply-result.json --apply
```

실데이터 자료는 Git 제외 `db-migration/reports/performance-artists-2026-10-04/`에
보존했다: `source-snapshot.json`, `manifest.json`, `excluded.json`, `dry-run.json`,
`apply-result.json`, `verification.json`, `retry-check.json`. DB URL·키·OAuth 토큰은 포함하지 않는다.
