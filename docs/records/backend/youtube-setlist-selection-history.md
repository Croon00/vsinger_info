# YouTube 세트리스트 후보 비교 이력

현재 계약은 [YouTube 세트리스트 후보 비교](../../youtube-setlist-selection.md)를 따른다. 이 문서는 당시 날짜의 구현·조사·검증·재수집 기록이며 수치는 기록 시점 값이다. 2026-11-23 계약 문서에서 분리했다.

## 버전 경과

- 2026-10-07 최초 모델 비교 구현.
- 2026-10-19 갱신: 선택 정책 `setlist-rules-first-1`, 규칙 추출 버전 `setlist-rules-1`. 당시 운영 배포·기존 DB 정정은 이 변경에 포함하지 않았다.
- 2026-10-30 사용자 요청에 따른 빈 세트리스트 조사·갱신과 모델 인증 제한은 [갱신 기록](../data/setlist-refresh-2026-10-30.md)에 별도로 정리했다.

## 2026-10-07 최초 구현 검증

2026-10-06 조사한 라이브 5850 댓글을 오프라인 fixture로 사용한다. 잡담 16줄과 실제 곡 목록 형식 14곡을 비교하며, 장식 헤더를 단순화하고 노래 행·잡담 행은 보존했다. LLM 의미 판정 응답은 mock이며 실제 모델의 판정 정확도를 검증한 결과가 아니다.

2026-10-07 로컬 일회용 PostgreSQL 및 mock provider 검증 결과:

- `python -m pytest tests/test_youtube_setlist_selection.py tests/test_youtube_catalog_collection.py tests/test_music_jobs.py tests/test_stage6_integrated_flow.py tests/test_phase4_boundaries.py -q --disable-warnings --maxfail=3`: **129 passed**, 111 warnings, 60.77초.
- 원문 검증 실패 사유 보존과 그 회귀 테스트 추가 후 `python -m pytest tests/test_youtube_setlist_selection.py tests/test_youtube_catalog_collection.py -q --disable-warnings --maxfail=2`: **90 passed**, 53 warnings, 29.07초.
- `git diff --check` 통과. 최초 샌드박스 내 PostgreSQL 시작은 Windows 제한 토큰 오류로 실패했으며, 로컬 테스트용 실행 권한으로 재실행한 결과가 위 기록이다.

알고리즘 변경만으로 기존 기록이 수정되지는 않는다. 라이브 5850은 후속 사용자 요청으로 2026-10-07 기존 16개를 보관하고 14곡으로 [별도 정정 완료](../data/live-5850-correction-2026-10-07.md)했다.

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

## 2026-10-09 토큰 검토와 재수집 축소

사용자 요청으로 v2 revision `4ba602f`와 v3를 비교했다. 실제 모델 호출 없이 `o200k_base`로 시스템 지시문·동일 댓글 문맥·JSON schema를 직렬화해 계산했다. 조사 자료의 영상별 최대 3개 저장 댓글을 사용한 185개 짝 비교이며, 후보 선정 변화나 API framing·내부 schema 처리·캐시·실제 출력 차이는 반영하지 않은 로컬 근사치다.

| 항목 | v2 | v3 |
| --- | ---: | ---: |
| 시스템 지시문 | 201 tokens | 469 tokens |
| 입력 평균(185개 동일 문맥) | 1,117 | 1,457 |
| 출력 평균(52개 기존 판정에 끝줄·짧은 ID 적용) | 626 | 686 |

입력 합계 기준 +30.5%, 표에 반올림한 출력 평균 기준 약 +9.6%다. 출력의 곡당 순증은 평균 약 5 tokens다. 출력 표는 실제 새 모델 출력이 아니라 동일 판정을 유지한 형식 비용 비교다. 댓글 최대 3개·각 20,000자와 출력 상한 12,000은 그대로이며 상한이 항상 사용되는 양을 뜻하지 않는다. 출력 오류에도 최대 2회 재시도를 추가했으므로 그 오류 건은 최대 3회 호출된다. 기존 `no_songs`의 시간 간격 댓글 재확인 비용도 별도로 존재한다. 비용 절감 후보는 지시문 압축과 동일 원문 재판정 억제이며 이 검토에서 추가 구현하지 않았다.

재수집 계획은 다음으로 축소했고 작업은 등록하지 않았다.

- 기존 빈 아카이브 1,053개 중 1단계 복구 28개와 9월 20일 00:00 KST 이후 방송의 최종 `invalid_response` 18개만 선택: 46개.
- 현재 진행 작업이 있는 2개는 중복 등록하지 않고 보류: 즉시 대상 44개.
- 宮島ルシェル 9월 27일 오수집 archive 5870은 비교·감사 정정 전용 1개로 별도 유지: 현재 실행 범위 총 45개, 24채널.
- 첫 묶음은 宮島ルシェル의 빈 아카이브 7개와 정정 1개, 총 8개다. 서버 v3와 실제 저장 결과를 확인한 뒤 나머지 대상으로 진행한다.
- 오래된 자료·단순 통신 오류 등 나머지 1,007개는 이번 재수집에서 제외한다. 영구 삭제나 기존 작업 취소는 아니다.
- Git 제외 `outputs/setlist-v3-recovery-2026-10-09/plan.json`을 축소 계획으로 교체했다. 이전 계획은 `plan-all-1053.json`에 보존했지만 실행 대상이 아니다. 토큰 근사치는 `token-review.json`, 대상 집계는 `reduced-summary.json`에 있다.

### 2026-10-09 서버 재수집 등록

사용자의 배포 완료 확인과 실행 요청에 따라 첫 8개를 서버 대기열에 등록했다. 요청 라벨 `setlist-v3-recovery-2026-10-09`, 추출 버전 `comparison-3`, job IDs `76843–76850`. 대상 archive는 `16355,15994,16385,16010,16170,17370,17371,5870`이다. 기존 가창이 있는 5870은 서버 추출 결과를 검토 후보로 보존하며 자동 교체하지 않는다.

2026-10-09 13:18 KST 조회 기준 8개 모두 pending/attempt_count=0. 기존 YouTube job `76442`의 `rate_limited`와 `next_attempt_at=2026-10-10 10:49:29 KST`가 provider 전체 선점을 막고 있다. 제한은 변경하지 않았다. 이 시각은 DB의 다음 시도 예약이며 실제 quota 회복을 보장하지 않는다. 서버 v3 실행·곡 저장은 아직 확인하지 못했으므로 남은 37개 등록은 보류했다. 등록 성공을 재수집 완료로 간주하지 않는다.

후속: 제한 이후 첫 8개의 정책·선택 상태·가창 저장을 확인하고 나머지 37개를 `.tmp/enqueue_v3_recovery.py --remaining`으로 등록한다(실행 직전 계정·기존 가창·진행 작업을 다시 확인하는 일회성 도구). 5870은 원문 비교 후 별도 감사 정정해야 한다. 요청 계획과 등록 영수증은 `outputs/setlist-v3-recovery-2026-10-09/`에 보존한다.

## 2026-10-19 규칙 우선 추출과 과거 덤프 검증

사용자가 제공한 `D:\06_Dev\세트리스트\setlist-patterns\REPORT.md`와 `REVALIDATION.md`를 참고했다. 해당 폴더의 과거 `archives.jsonl`에서 비어 있지 않은 댓글 6,148건을 읽어 현재 규칙에 오프라인으로 적용했다. 기존 덤프의 setlist 결과와 패턴 분류는 정답으로 사용하지 않았다.

- 댓글별 규칙 통과: **1,528건**, 추출 행 **20,292개**. 그 외 댓글은 규칙 미확정이다.
- 이는 각 댓글을 단독 검사한 형식 지원 범위이며, 정답률·최신 실패 영상의 복구 건수·운영 수집 성공률이 아니다. 실제 worker는 영상별 최대 3개 후보의 충돌도 검사하므로 모델 생략 건수는 달라진다.
- 전체 통과 결과의 원문·행 범위를 로컬 `.tmp/rule-corpus-review.json`에 저장하고, 시작/끝/잡담 유사 문자열·긴 행·제목 괄호·대표 댓글을 확인했다. 전체 곡의 의미를 수동 검수하거나 실제 음원을 대조한 결과는 아니다. 로컬 재현 도구와 요약은 `.tmp/audit_setlist_rules.py`, `.tmp/rule-corpus-summary.json`이며 Git 제외 자료다.
- 보고서의 장식 표제, 시간/곡명 역순, 나무 모양 들여쓰기, 숫자 곡명, 혼합 콜론, 제목 안의 slash·START/END, 번호 붙은 시작 안내를 회귀 테스트로 고정했다. 곡명 괄호·`-ERROR`·콜론 끝 제목, 단독 MC 뒤 가창, 후보 충돌, 최대 4줄 근거도 검사한다.
- 실제 저장 테스트는 일시 오류로 재시도가 소진된 빈 archive를 명시적 목록으로 다시 처리하는 경로, 원문·출처 URL·선택 문서 연결·규칙 버전·모델 호출 0회, 재실행 중복 방지·수동 수정 보존을 포함한다. 재시도 소진 작업을 자동으로 새로 등록하는 기능은 추가하지 않았다.

검증일 2026-10-19:

- `python -B -m pytest tests/test_youtube_setlist_rules.py tests/test_youtube_setlist_selection.py tests/test_youtube_comment_formats.py tests/test_youtube_catalog_collection.py tests/test_music_jobs.py tests/test_stage6_integrated_flow.py tests/test_phase4_boundaries.py -q -p no:cacheprovider --disable-warnings --maxfail=3` — **237 passed**, 109 warnings, 64.63초. 일회용 로컬 PostgreSQL 및 mock provider/LLM을 사용했다.
- 최종 `Song List` 후보 가점 보완 후 앞의 규칙·선택·댓글 형식 테스트 3개 파일 재검증 — **136 passed**, 0.96초.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`을 사용했으며 Windows 제한 토큰의 asyncio 정지 때문에 로컬 실행 권한으로 테스트했다. `git diff --check` 통과. 실제 YouTube·LLM·Discord·Calendar 호출은 0회다.

운영 배포·운영 DB 변경·재수집 등록은 수행하지 않았다. `transient_error` 자체의 provider 원인과 복구는 이번 규칙 개선 범위에서 제외했다.
