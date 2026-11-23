# 전환 시기 YouTube 아카이브 복구 — 2026-10-09

사용자 요청의 1단계(누락 아카이브 복구)를 운영 신규 DB에 반영했다. 세트리스트 수집조건 개선과 미수집 세트리스트 재검증은 각각 2·3단계로 남긴다.

## 조사 범위

- 현재 수집 활성·미보관 YouTube 계정 104개를 조사했다.
- 기간: 2026-09-20 00:00 이상, 2026-09-24 00:00 미만(KST). 실제 시작·종료·공개 시각 중 하나라도 해당하는 완료 노래 방송을 포함했다. 날짜가 바뀌어 종료·공개된 9월 19일 밤 방송도 포함한다.
- 공개 uploads 목록을 채널당 최대 200개 읽었다. 초기 9개 채널은 기존 recent 조회를 사용했고, 나머지는 기간 이전 경계를 확인하면 목록 조회를 종료했다. 모든 채널에서 해당 기간 이전까지의 목록 또는 목록 끝을 확인했다. API 오류 0개.
- 제목의 기존 노래방송 판정과 실제 시작·종료 시각을 확인했다. 공개 목록에 없는 비공개·삭제·일부 공개 영상이나 기존 제목 규칙이 놓치는 방송까지 완전 복구했다는 의미는 아니다.
- 발견 92개: 기존 아카이브 64개, 영상·작업 모두 없는 25개, 기존 영상·작업만 있고 아카이브가 없는 3개.

## 반영 결과

- 누락 아카이브 28개, 신규 영상 25개, 진행자 연결 28개, 메타데이터 출처 문서 28개, 출처 연결 28개 생성.
- 신규 28개는 모두 `setlist_state=unprocessed`, 가창 0개다. 댓글·LLM 추출을 실행하지 않았다.
- 신규 DB identity 검사, 최신 YouTube 영상·계정 소유권 재검증, 기존 worker와 동일한 영상별 advisory lock 후 한 transaction으로 저장했다. 기존 방송 메타데이터 복구 도구의 계약을 따른다.
- 기존 아카이브·가창·수동 수정·작업·수집 기준선·운영 활성 설정은 변경하지 않았다. 구 DB와 Discord·Calendar·Spotify는 호출하지 않았다.
- `catalog_imports.id=6309`, `catalog_changes` 생성 기록 137개. 정책: `cutover-archives-metadata-2026-10-09-v1`.
- 로컬 근거: `outputs/youtube-cutover-2026-10-09/`의 `inventory.json`, `preview.json`, `receipt.json`, `verification.json`, `idempotency.json`, 일회성 `restore_archives.py`. 해당 디렉터리는 Git 제외이며 DB에도 영수증·출처를 보존했다.
- Inventory SHA-256: `120be028587020ac6bedaefb3ee9164d9cc7637de34eadfa78506d3ac4cc26e0`.

## 복구한 방송

| 아티스트 | 방송 시작(KST) | 영상 | 아카이브 ID |
| --- | --- | --- | --- |
| VESPERBELL | 09-20 20:01 | [8bsAZ64Sqbs](https://www.youtube.com/watch?v=8bsAZ64Sqbs) | 17345 |
| VESPERBELL | 09-21 22:15 | [31R8RvPiBYo](https://www.youtube.com/watch?v=31R8RvPiBYo) | 17346 |
| wouca | 09-21 21:57 | [EKOiR-PLRPY](https://www.youtube.com/watch?v=EKOiR-PLRPY) | 17347 |
| MEDA | 09-20 21:28 | [_-52f43qEiM](https://www.youtube.com/watch?v=_-52f43qEiM) | 17348 |
| 妃玖 | 09-19 22:03 | [FMsAfifcdMs](https://www.youtube.com/watch?v=FMsAfifcdMs) | 17349 |
| 深影 | 09-22 00:57 | [W5pDUFJlFbU](https://www.youtube.com/watch?v=W5pDUFJlFbU) | 17350 |
| 羽緒 | 09-22 02:00 | [JTFNnPm9u9E](https://www.youtube.com/watch?v=JTFNnPm9u9E) | 17351 |
| 羽緒 | 09-19 21:07 | [u5vUZOP7qTk](https://www.youtube.com/watch?v=u5vUZOP7qTk) | 17352 |
| LEWNE | 09-23 21:04 | [0K9Mi2JQEVc](https://www.youtube.com/watch?v=0K9Mi2JQEVc) | 17353 |
| XIDEN | 09-20 13:06 | [T_jz25rlH8I](https://www.youtube.com/watch?v=T_jz25rlH8I) | 17354 |
| 瀬戸乃とと | 09-21 18:16 | [7J-hVq5C5CY](https://www.youtube.com/watch?v=7J-hVq5C5CY) | 17355 |
| 焔魔るり | 09-20 00:02 | [eXDfdIEsUzQ](https://www.youtube.com/watch?v=eXDfdIEsUzQ) | 17356 |
| 水瀬凪 | 09-20 19:57 | [AXPS0hCUpVE](https://www.youtube.com/watch?v=AXPS0hCUpVE) | 17357 |
| 水瀬凪 | 09-20 16:00 | [r1EcfZHCiUo](https://www.youtube.com/watch?v=r1EcfZHCiUo) | 17359 |
| 氷夏至 | 09-20 19:54 | [ShM7N7_oOmA](https://www.youtube.com/watch?v=ShM7N7_oOmA) | 17360 |
| 伊月知世 | 09-21 17:06 | [BRNyfpWSMPk](https://www.youtube.com/watch?v=BRNyfpWSMPk) | 17361 |
| 伊月知世 | 09-21 17:27 | [HxtNxOFgakk](https://www.youtube.com/watch?v=HxtNxOFgakk) | 17362 |
| 伊月知世 | 09-20 12:03 | [SGHVlux1Al4](https://www.youtube.com/watch?v=SGHVlux1Al4) | 17363 |
| 白河しらせ | 09-23 13:05 | [7iaNhXZLul4](https://www.youtube.com/watch?v=7iaNhXZLul4) | 17364 |
| 白河しらせ | 09-20 23:02 | [UowsTkMC8ak](https://www.youtube.com/watch?v=UowsTkMC8ak) | 17365 |
| ミナミイズミ | 09-21 19:31 | [as_4sW4W7PM](https://www.youtube.com/watch?v=as_4sW4W7PM) | 17366 |
| ミナミイズミ | 09-19 22:00 | [3kg87Z-QDr8](https://www.youtube.com/watch?v=3kg87Z-QDr8) | 17367 |
| 朱名 | 09-23 17:35 | [TLG-xH9Bcfw](https://www.youtube.com/watch?v=TLG-xH9Bcfw) | 17368 |
| メーメントヴァニタス | 09-20 13:01 | [ABP6mAN2YQw](https://www.youtube.com/watch?v=ABP6mAN2YQw) | 17369 |
| 宮島ルシェル | 09-23 10:31 | [qc9eAM_AkPU](https://www.youtube.com/watch?v=qc9eAM_AkPU) | 17370 |
| 宮島ルシェル | 09-19 22:30 | [E-aBHDHZIio](https://www.youtube.com/watch?v=E-aBHDHZIio) | 17371 |
| 傘屋くぐる | 09-21 16:00 | [P-183AMbhus](https://www.youtube.com/watch?v=P-183AMbhus) | 17372 |
| Nijyuna | 09-20 17:58 | [UzddNvJTR0c](https://www.youtube.com/watch?v=UzddNvJTR0c) | 17373 |

宮島ルシェル의 20일 표시 영상은 업로드 기준으로 9월 20일 00:33이며, 실제 방송 시작은 9월 19일 22:30이다. 실제 시작을 `broadcast_at`에 보존했으므로 방송 기준 화면에서는 19일로 표시될 수 있다.

## 검증 — 2026-10-09

- 실제 운영 DB 조회: 조사 대상 92개 모두 활성 아카이브 존재, 기존 64개 ID 유지. 복구 28개 모두 미처리 상태·가창 0개·메타데이터 출처 연결 확인.
- 실제 운영 DB에 연결한 로컬 FastAPI TestClient: `/api/lives/{id}` 28개 모두 HTTP 200, YouTube ID 일치. `/api/artists/79/lives`에서 宮島ルシェル의 17370·17371 확인.
- 동일 입력으로 반영 재실행: 28개 모두 기존 아카이브로 건너뜀, 추가 생성 0개.
- fixture 테스트나 배포 웹 브라우저 검증으로 보고하지 않는다. 이번에는 수집기 구현을 바꾸지 않았으며, 세트리스트 품질 검증도 수행하지 않았다.

## 후속 단계

2. 여러 줄에 걸친 timestamp·곡명·원곡자 근거와 후보 ID 검증을 개선하고 실패·보류의 재시도 계약을 점검한다.
3. 이번 복구 28개를 포함해 미수집 세트리스트를 재검증한다. 宮島ルシェル 9월 27일의 잡담 2개 오수집은 기존 가창 보존·정정 절차로 별도 처리한다.
