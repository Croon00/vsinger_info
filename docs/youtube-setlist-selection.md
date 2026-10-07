# YouTube 세트리스트 후보 비교

구현일: 2026-10-07. 정책 버전: `setlist-comparison-2`.
독립 YouTube worker의 신규 수집에 적용하는 계약이다. 운영 배포·기존 DB 정정은 이 변경에 포함하지 않는다.

## 후보와 판정

1. YouTube 댓글을 관련도 순 최대 3페이지/300개 읽는다. timestamp가 하나라도 있는 댓글을 후보로 받는다. 타임스탬프는 노래의 증거가 아니며 한 곡 방송도 허용한다.
2. 댓글 ID를 중복 제거하고 `SetList/セットリスト/セトリ/세트리스트`, 곡명·원곡자 구분 구조, 곡 번호 구조를 가점으로 평가한다. 점수는 `8×제목표기 + 4×원곡자구조비율 + 2×번호구조비율 + min(시간행수,20)/20`이다. 이 점수는 모델에 보낼 후보를 고르는 용도이며 가창 등록 조건이 아니다. 동점이면 댓글 ID 순이다.
3. 상위 최대 3개 원문을 한 번의 구조화된 LLM 요청으로 비교한다. 각 댓글을 `setlist/mixed/chat/uncertain`으로 판단하고 하나를 선택하거나 `no_songs/uncertain`으로 보류한다. 곡 수가 다른 후보는 부분집합인지 비교하고, 곡명·시간 충돌을 해소할 근거가 없으면 보류하도록 지시한다. 원곡자·알려진 곡 DB·특정 헤더는 필수 조건이 아니다.
4. 입력은 댓글별 원문 줄 번호를 붙인 최대 20,000자다. 원문 전체는 DB에 보존한다. 문맥이 잘린 댓글이 선택되면 자동 반영하지 않는다. 모델 요청 timeout 45초, SDK 내부 재시도 0회, 출력 최대 12,000토큰이며 출력 중단·schema 오류는 `invalid_response`다.
5. 선택 후보 ID와 모든 후보의 판정을 검증한다. 곡의 원문 줄 번호, 그 줄의 첫 timestamp와 완전히 동일한 시간, 같은 줄에 존재하는 곡명·명시된 원곡자를 검증한다. 영상 길이 밖 시간·중복 시작 시각·근거 없는 행이 하나라도 있으면 선택 전체를 보류한다. 검증된 곡만 시간순으로 저장한다.

책임은 `services/youtube_setlist.py`의 후보 선정·원문 검증, `integrations/youtube_setlist.py`의 구조화된 모델 호출, `services/youtube_collection.py`의 상태 전이, `repositories/youtube_collection.py`의 원자 저장으로 나뉜다. 기존 `parse_setlist`와 단일 댓글 AI helper는 보존 코드/도구에서 사용할 수 있지만 정상 worker의 가창 확정에는 사용하지 않는다.

## 상태와 재시도

| 판정/호출 상태 | 가창 저장 | 후속 동작 |
| --- | --- | --- |
| `selected` | 원문 검증 통과 행만 저장 | `collected`; 신규 세트리스트는 `partial` |
| `no_songs` | 0건 | 다른 댓글이 생길 수 있어 기존 1시간 간격·최대 168회 댓글 대기 계약 사용 |
| `uncertain` | 0건 | `review_required`; 자동 재시도 없음 |
| `unconfigured` | 0건 | 키 설정 전 `review_required`; 자동 재시도 없음 |
| `provider_error` | 0건 | 401/403 등 영구 오류를 보류; 자동 재시도 없음 |
| `invalid_response` | 0건 | schema·출력 중단·원문 검증 실패 보류; 자동 재시도 없음 |
| `transient_error` | 0건 | 연결 오류/timeout/429/5xx는 최대 2회 후속 작업; 소진 시 `review_required` |

일시 오류 후속 작업은 `selection_retry_count=0..2`를 사용한다. 최소 1시간 뒤 실행하며 더 긴 `Retry-After`가 있으면 그 이후로 예약한다. 댓글 대기 횟수와 독립된 누적 한도다. 원문과 후속 작업을 같은 transaction에 저장한다. 기본값 0은 작업 키 계산에서 제외하며 기존 v1 payload를 재검증하므로 배포 전 작업의 idempotency key를 유지한다.

보류·모델 재시도용 신규 archive는 `unprocessed`로 만들고 가창은 비워 둔다. 단순 댓글 대기는 기존대로 영상·출처·후속 작업만 저장하며 이때 출처는 `video_id` metadata로 찾을 수 있다. API가 재수집이나 모델 호출을 시작하지 않는다.

`OPENAI_API_KEY`는 세트리스트 자동 등록에 필요하다. 미설정 시 규칙 추출을 대신 공개하지 않는다. `/ready`는 활성 YouTube 계정에 대해 해당 키 누락을 표시한다. `OPENAI_MODEL` 설정을 사용하며 모델을 이 변경에서 바꾸지 않는다.

## 보존과 기존 자료

기존 `source_documents`/`archive_sources` 테이블을 사용하므로 DB migration은 없다. 후보별 댓글 ID·URL·전체 원문·확보 시각과 아래 metadata를 보존한다.

- `candidate`: 순위, 점수, 항목별 근거, 입력 잘림 여부.
- `selection`: 정책 버전, 상태, 모델, 후보 수/보존 수/비교 호출 수, 모델의 선택·분류·이유·추출 응답, 원문 검증 실패 사유, provider 재시도 대기값.
- `selected`: 해당 댓글이 최종 선택된 원문인지 여부. 최상위 `rows`는 선택 댓글에만 채운다.
- `disposition`: 실제 새 가창에 적용한 원문은 `applied`, 다른 후보·보류는 `review_candidate`, 경합은 `version_conflict`.

같은 원문·추출/판정 metadata 재처리는 기존 hash로 중복을 막는다. 모델 출력이 달라지면 새 관측 문서로 남을 수 있다. `performances.source_document_id`는 선택된 댓글 문서만 가리킨다. 기존 가창·수동 크레딧은 자동 교체하지 않는다. 검토·정정 UI/API는 구현하지 않았다.

라이브 5850의 기존 잘못된 가창 16개 정정은 별도 작업이다. 이번 변경만으로 기존 기록이 수정되지 않는다.

## 검증 범위

2026-10-06 조사한 라이브 5850 댓글을 오프라인 fixture로 사용한다. 잡담 16줄과 실제 곡 목록 형식 14곡을 비교하며, 장식 헤더를 단순화하고 노래 행·잡담 행은 보존했다. LLM 의미 판정 응답은 mock이며 실제 모델의 판정 정확도를 검증한 결과가 아니다.

회귀 검증은 후보 순위·최대 3개 보존, 단일 곡·원곡자 없음·혼합 댓글, 빈 결과·불확실·출력 오류에서 규칙 결과 부활 금지, 원문 근거/시간 검증, 영구/일시 오류, 재시도 한도·예약·작업 키 호환, 중복 방지와 기존 가창·수동 크레딧 보존, 공개 API 조회를 포함한다. 실제 YouTube·LLM·Discord·Calendar 호출과 운영 DB 변경은 하지 않는다.

2026-10-07 로컬 일회용 PostgreSQL 및 mock provider 검증 결과:

- `python -m pytest tests/test_youtube_setlist_selection.py tests/test_youtube_catalog_collection.py tests/test_music_jobs.py tests/test_stage6_integrated_flow.py tests/test_phase4_boundaries.py -q --disable-warnings --maxfail=3`: **129 passed**, 111 warnings, 60.77초.
- 원문 검증 실패 사유 보존과 그 회귀 테스트 추가 후 `python -m pytest tests/test_youtube_setlist_selection.py tests/test_youtube_catalog_collection.py -q --disable-warnings --maxfail=2`: **90 passed**, 53 warnings, 29.07초.
- `git diff --check` 통과. 최초 샌드박스 내 PostgreSQL 시작은 Windows 제한 토큰 오류로 실패했으며, 로컬 테스트용 실행 권한으로 재실행한 결과가 위 기록이다.
