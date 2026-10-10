# YouTube 수집 운영 상태 점검 — 2026-10-11

확인 시각: 2026-10-11 02:50 KST. 현재 로컬 DATABASE_URL의 신규 DB를 읽기 전용으로 확인했다. Railway 관리 로그·배포 환경은 직접 조회하지 못했으므로 DB 작업 기록에서 확인되는 실행 상태와 Railway 프로세스 직접 검증을 구분한다. DB 쓰기, worker 시작, 재수집 등록, YouTube·LLM 호출, 알림 전송은 수행하지 않았다.

## 확인 결과

- 수집 활성 YouTube 계정 104개 전부 최근 26시간 내 poll 완료. 마지막 poll 범위는 10월 10일 11:01–11:28 KST. 미확인 계정·next_poll_at 경과 계정은 0개였다.
- 점검 중 youtube_collect 완료 기록이 갱신됐으며 running 1개도 관찰됐다. 따라서 DB에 기록을 남기는 worker는 동작 중이다. 각 작업을 수행한 호스트가 Railway인지는 직접 확인하지 않았다.
- 대기 작업 약 410개, 그중 실행 시각이 지난 작업 약 124개. 가장 이른 시각은 약 15분 전이며 만료된 running lease는 없었다. snapshot마다 worker 진행으로 수치는 변한다. 기본 initial 290개 외 MAIR·Noa Polaris 요청 backfill도 대기 중이다.
- job succeeded는 단계 처리/원문 저장 성공이며 세트리스트 곡 저장 성공을 뜻하지 않는다. 댓글 없음·판정 재시도·검토 보류도 해당 작업은 succeeded이고 후속 작업이 만들어지거나 종료된다.

## 세트리스트 결과

최신 setlist-comparison-3 기록을 영상 ID별 마지막 결과로 집계하면 총 48개 중 selected 0개, review_required + transient_error 41개, selection_retry + transient_error 7개였다. 마지막 오류는 10월 11일 02:48 KST에도 기록됐다. 댓글 후보는 확보됐으나 모델 판정 결과가 없다.

최근 24시간 performances 생성은 10행/1개 방송뿐이며 앞선 사용자 요청으로 수동 등록한 AZKi archive 17430에 해당한다. 최신 v3 자동 추출 성공을 확인하지 못했다. 마지막 selection.status=selected 기록은 v2의 10월 8일 05:38 KST다. 별도 이전·수동 도구의 collected나 performance 생성과 정상 worker 모델 성공을 혼동하지 않는다.

최근 72시간 최종 후보 판정에는 이전 v2 transient_error 보류 283개, invalid_response 보류 82개도 남아 있다. 최근 5일 최종 failed job은 ValidationError 561개, PermanentJobError 3개, DataError 1개이며 최근 실패 시각은 10월 9일 03:00 KST다. 이는 v3 후보 판정 상태와 다른 집계다.

## 원인 범위와 후속

현재 코드는 모델 APIConnectionError 또는 HTTP 429/5xx를 transient_error 하나로 보존한다. 현재 DB만으로 연결·사용량/속도 제한·provider 서버 오류를 구분할 수 없다. retry_after_seconds=0도 원인 확정 근거가 아니다. 기존 세트리스트 계획 문서에는 앞선 실제 모델 429 기록이 있으나 이번에도 같은 원인이라고 단정하지 않는다.

후속으로 Railway 모델 호출 오류의 실제 HTTP status/error code와 배포 환경 설정을 비밀값 노출 없이 확인해야 한다. 원인을 해결한 뒤 제한된 대상의 selected·실제 가창 저장을 확인하고 보류 영상을 선별 재처리해야 한다. succeeded 작업 수만으로 정상 상태를 판단하지 않는다. 이번 점검에서는 운영 환경·재시도 정책·대기열·데이터를 변경하지 않았다.

근거: Git 제외 outputs/youtube-runtime-audit-2026-10-11/audit.json 및 detail.json. 진단 도구: .tmp/audit_youtube_runtime.py. 기존 후보 비교·복구 기록: [세트리스트 후보 비교](youtube-setlist-selection.md).
