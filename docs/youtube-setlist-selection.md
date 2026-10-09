# YouTube 세트리스트 후보 비교

갱신: 2026-10-09. 정책 버전: `setlist-comparison-3` (최초 구현 2026-10-07).
독립 YouTube worker의 신규 수집에 적용하는 계약이다. 운영 배포·기존 DB 정정은 이 변경에 포함하지 않는다.

## 후보와 판정

1. YouTube 댓글을 관련도 순 최대 3페이지/300개 읽는다. timestamp가 하나라도 있는 댓글을 후보로 받는다. 타임스탬프는 노래의 증거가 아니며 한 곡 방송도 허용한다. 전각 숫자·콜론과 60분 이상 경과 분 표기(`90:00`)도 후보로 받는다. 댓글 답글은 이번 확장 대상이 아니다.
2. 댓글 ID를 중복 제거하고 `SetList/セットリスト/セトリ/세트리스트/歌唱タイムスタンプ`, 곡명·원곡자 구분 구조, 곡 번호 구조를 가점으로 평가한다. 시간 행 이후 최대 3개의 연속 행도 구분 구조 평가에 포함하며 다음 시간 행이나 빈 줄에서 멈춘다. 공백 없는 구분자도 인정하되 URL은 이 가점에서 제외한다. 점수는 `8×제목표기 + 4×원곡자구조비율 + 2×번호구조비율 + min(시간행수,20)/20`이다. 이 점수는 모델에 보낼 후보를 고르는 용도이며 가창 등록 조건이 아니다. 동점이면 댓글 ID 순이다.
3. 상위 최대 3개 원문을 한 번의 구조화된 LLM 요청으로 비교한다. 각 댓글을 `setlist/mixed/chat/uncertain`으로 판단하고 하나를 선택하거나 `no_songs/uncertain`으로 보류한다. 곡 수가 다른 후보는 부분집합인지 비교하고, 곡명·시간 충돌을 해소할 근거가 없으면 보류하도록 지시한다. 원곡자·알려진 곡 DB·특정 헤더는 필수 조건이 아니다. 모델에는 원래 댓글 ID 대신 요청 내부 ID `c1..c3`를 enum으로 전달하고 응답에서 원래 ID로 정확히 복원한다. 모르는 ID는 유사 문자열로 추측하지 않는다.
4. 입력은 댓글별 원문 줄 번호를 붙인 최대 20,000자다. 원문 전체는 DB에 보존한다. 문맥이 잘린 댓글이 선택되면 자동 반영하지 않는다. 모델 요청 timeout 45초, SDK 내부 재시도 0회, 출력 최대 12,000토큰이며 출력 중단·schema 오류는 `invalid_response`다.
5. 선택 후보와 모든 후보 판정을 검증한다. 각 곡은 `line_number`~`end_line_number`로 원문에서 연속된 최대 4줄을 명시한다. 한 줄 형식은 시작·끝 번호가 같다. 이전 저장 응답에서 끝 번호가 없으면 한 줄로 해석한다.
6. 근거 범위에는 시간 행이 정확히 하나 있어야 한다. 시작 시각 하나 또는 `시작~끝` 범위만 허용하고 범위의 첫 시각을 사용한다. 다른 곡의 시간 행을 함께 묶거나 한 줄의 여러 곡을 합치는 선택은 거절한다. 시간은 초 값으로 비교해 `01:00`, `1:00`, `０１：００`의 동치를 허용하되 저장 timestamp는 원문 표기를 보존한다.
7. 곡명·원곡자는 해당 범위의 개별 원문 행에 정확히 포함되어야 한다. 시간과 곡명 행의 순서는 고정하지 않는다. 번역·철자 교정·문장부호 유사 매칭으로 출처 불일치를 덮지 않는다. 원곡자가 명시되지 않으면 null이다. 번호·키·버전 주석을 분리할 때도 원문 부분문자열만 사용하도록 모델에 지시한다.
8. 영상 길이 밖 시작 시각, 중복 시각, 겹치는 근거 범위, 잘린 문맥 또는 근거 없는 곡이 하나라도 있으면 선택 전체를 보류한다. 같은 곡이 다른 시간에 반복된 것은 별개 가창으로 유지한다. 검증된 곡만 시간순으로 저장한다.

책임은 `services/youtube_setlist.py`의 후보 선정·원문 검증, `integrations/youtube_setlist.py`의 구조화된 모델 호출, `services/youtube_collection.py`의 상태 전이, `repositories/youtube_collection.py`의 원자 저장으로 나뉜다. 기존 `parse_setlist`와 단일 댓글 AI helper는 보존 코드/도구에서 사용할 수 있지만 정상 worker의 가창 확정에는 사용하지 않는다.

## 상태와 재시도

| 판정/호출 상태 | 가창 저장 | 후속 동작 |
| --- | --- | --- |
| `selected` | 원문 검증 통과 행만 저장 | `collected`; 신규 세트리스트는 `partial` |
| `no_songs` | 0건 | 다른 댓글이 생길 수 있어 기존 1시간 간격·최대 168회 댓글 대기 계약 사용 |
| `uncertain` | 0건 | `review_required`; 자동 재시도 없음 |
| `unconfigured` | 0건 | 키 설정 전 `review_required`; 자동 재시도 없음 |
| `provider_error` | 0건 | 401/403 등 영구 오류를 보류; 자동 재시도 없음 |
| `invalid_response` | 0건 | schema·출력 중단·원문 검증 실패는 최대 2회 후속 작업; 소진 시 `review_required` |
| `transient_error` | 0건 | 연결 오류/timeout/429/5xx는 최대 2회 후속 작업; 소진 시 `review_required` |

일시 오류와 출력 오류 후속 작업은 `selection_retry_count=0..2`를 사용한다. 최소 1시간 뒤 실행하며 더 긴 `Retry-After`가 있으면 그 이후로 예약한다. 댓글 대기 횟수와 독립된 누적 한도이며 일시 오류·출력 오류가 같은 2회 예산을 공유한다. 불확실한 의미 판정은 자동 재시도하지 않는다. 원문과 후속 작업을 같은 transaction에 저장한다. 기본값 0은 작업 키 계산에서 제외하며 기존 v1 payload를 재검증하므로 배포 전 작업의 idempotency key를 유지한다.

보류·모델 재시도용 신규 archive는 `unprocessed`로 만들고 가창은 비워 둔다. 단순 댓글 대기는 기존대로 영상·출처·후속 작업만 저장하며 이때 출처는 `video_id` metadata로 찾을 수 있다. API가 재수집이나 모델 호출을 시작하지 않는다.

`OPENAI_API_KEY`는 세트리스트 자동 등록에 필요하다. 미설정 시 규칙 추출을 대신 공개하지 않는다. `/ready`는 활성 YouTube 계정에 대해 해당 키 누락을 표시한다. `OPENAI_MODEL` 설정을 사용하며 모델을 이 변경에서 바꾸지 않는다.

## 보존과 기존 자료

기존 `source_documents`/`archive_sources` 테이블을 사용하므로 DB migration은 없다. 후보별 댓글 ID·URL·전체 원문·확보 시각과 아래 metadata를 보존한다.

- `candidate`: 순위, 점수, 항목별 근거, 입력 잘림 여부.
- `selection`: 정책 버전, 상태, 모델, 후보 수/보존 수/비교 호출 수, 모델의 선택·분류·이유·추출 응답, 원문 검증 실패 사유, provider 재시도 대기값.
- `selected`: 해당 댓글이 최종 선택된 원문인지 여부. 최상위 `rows`는 선택 댓글에만 채운다. 각 행의 원문 시작·끝 번호와 여러 줄 `raw_line`을 보존한다.
- `disposition`: 실제 새 가창에 적용한 원문은 `applied`, 다른 후보·보류는 `review_candidate`, 경합은 `version_conflict`.

같은 원문·추출/판정 metadata 재처리는 기존 hash로 중복을 막는다. 모델 출력이 달라지면 새 관측 문서로 남을 수 있다. `performances.source_document_id`는 선택된 댓글 문서만 가리킨다. 기존 가창·수동 크레딧은 자동 교체하지 않는다. 검토·정정 UI/API는 구현하지 않았다.

알고리즘 변경만으로 기존 기록이 수정되지는 않는다. 라이브 5850은 후속 사용자 요청으로 2026-10-07 기존 16개를 보관하고 14곡으로 [별도 정정 완료](live-5850-correction-2026-10-07.md)했다.

## 검증 범위

2026-10-06 조사한 라이브 5850 댓글을 오프라인 fixture로 사용한다. 잡담 16줄과 실제 곡 목록 형식 14곡을 비교하며, 장식 헤더를 단순화하고 노래 행·잡담 행은 보존했다. LLM 의미 판정 응답은 mock이며 실제 모델의 판정 정확도를 검증한 결과가 아니다.

회귀 검증은 후보 순위·최대 3개 보존, 단일 곡·원곡자 없음·혼합 댓글, 빈 결과·불확실·출력 오류에서 규칙 결과 부활 금지, 원문 근거/시간 검증, 영구/일시 오류, 재시도 한도·예약·작업 키 호환, 중복 방지와 기존 가창·수동 크레딧 보존, 공개 API 조회를 포함한다. 실제 YouTube·LLM·Discord·Calendar 호출과 운영 DB 변경은 하지 않는다.

2026-10-07 로컬 일회용 PostgreSQL 및 mock provider 검증 결과:

- `python -m pytest tests/test_youtube_setlist_selection.py tests/test_youtube_catalog_collection.py tests/test_music_jobs.py tests/test_stage6_integrated_flow.py tests/test_phase4_boundaries.py -q --disable-warnings --maxfail=3`: **129 passed**, 111 warnings, 60.77초.
- 원문 검증 실패 사유 보존과 그 회귀 테스트 추가 후 `python -m pytest tests/test_youtube_setlist_selection.py tests/test_youtube_catalog_collection.py -q --disable-warnings --maxfail=2`: **90 passed**, 53 warnings, 29.07초.
- `git diff --check` 통과. 최초 샌드박스 내 PostgreSQL 시작은 Windows 제한 토큰 오류로 실패했으며, 로컬 테스트용 실행 권한으로 재실행한 결과가 위 기록이다.

## 2026-10-09 댓글 유형 조사와 2단계 개선

운영 DB를 읽기 전용으로 조사해 65개 채널의 최신 후보 문서 305건을 확보했다. 댓글 ID와 원문 내용 기준으로 중복을 제외하면 245개다. 대표 추출은 채널별 최신 6개 관측이며, 전체 댓글 모집단의 무작위 표본이나 모델 정확도 평가가 아니다. 원문 연구 자료는 Git 제외 `outputs/youtube-comment-research-2026-10-09/samples.json`에 보관한다.

| 유형 | 확인한 채널 예시 | 처리 |
| --- | --- | --- |
| 시간 범위 다음 줄에 곡·원곡자 | 宮島ルシェル, 松永依織, 時庭らんぜ | 최대 4줄의 명시적 근거 범위 |
| 세 번째 줄에 번역·로마자 병기 | 皇美緒奈, ミナミイズミ, 朱名, 傘屋くぐる | 별도 곡으로 만들지 않고 원문 표기 선택 |
| 번호·이모지·버전 주석 | NUROJUNK, shin | 원문 부분문자열을 사용하며 주석 제거는 모델에 지시 |
| 공백 없는 곡/원곡자, 원곡자 먼저 | MEDA, 鈴鳴すばる | 구분 순서를 고정하지 않음 |
| 원곡자 없는 목록 | ノア・ポラリス | 원곡자를 추측하지 않고 null |
| 한 곡만 있는 방송 | MEDA | 한 곡도 허용 |
| 노래·잡담·공지 혼합 | MEDA, 燈舞りん | 모델은 실제 가창만 선택; 규칙 결과 자동 복구 금지 |
| 부분·로마자·서로 다른 시간 목록 | 大神ミオ | 후보별 비교, 근거 있는 더 완전한 목록 선택; 모호한 충돌 보류 |
| 감상·박수·링크·날짜/시간·시간만 나열 | HACHI, CULUA, 鈴鳴すばる, ノア・ポラリス | 시간 존재만으로 가창 확정 금지 |

`tests/fixtures/youtube_comment_formats.json`에는 14개의 짧은 실제 발췌·출처 URL·원래 시작 줄과 검수한 필드를 남겼다. 이 중 일부 형식은 기존에도 처리 가능했으며 회귀 방지를 위해 포함했다. 전각 시간·90분 표기·역순 근거·범위 경계·잘못된 ID 등은 별도의 합성 fixture로 검증한다. 실제 의미 판정 응답은 mock이므로 실제 LLM 품질 개선률을 주장하지 않는다.

코드 배포, 실제 모델 품질 확인, 기존 미수집/오수집 아카이브 정정은 아직 수행하지 않았다. 1단계 복구한 28개를 포함한 기존 자료 재검증은 3단계다.

검증일 2026-10-09: `python -B -m pytest tests/test_youtube_setlist_selection.py tests/test_youtube_comment_formats.py tests/test_youtube_catalog_collection.py tests/test_music_jobs.py tests/test_stage6_integrated_flow.py tests/test_phase4_boundaries.py -q -p no:cacheprovider --disable-warnings --maxfail=3` — **180 passed**, 109 warnings, 66.98초. 일회용 로컬 PostgreSQL 및 mock provider/LLM을 사용했다. 실제 운영 DB 쓰기·모델 호출·알림은 0회다.
