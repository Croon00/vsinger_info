# YouTube 오리지널 일일 수집 설계

2026-11-22 추가: [곡 목록·즐겨찾기 화면 설계](ui.md)와 [실제 과거 보완 결과](../../docs/youtube-original-backfill-2026-11-22.md)를 연결한다. `scripts/backfill_youtube_originals.py`는 공식 owner 계정의 업로드 캐시·head 갱신·영상 상세를 체크포인트로 보존한다. API 요청 예산/대기 시각을 지키며 일일 worker와 독립적으로 명시적 실행한다. 작업별 Session과 기존 수집 원자 저장을 재사용한다.

기존 일일 poll → youtube_collect(purpose=original) → 근거 판정 → 원문/검토 후보 또는 녹음/명의/영상 저장 순서다. integrations.youtube_catalog.purpose의 기존 cover/archive 계약은 유지하고 services.youtube_collection에서 미분류 일반 업로드를 오리지널 검증 후보로 추가한다. 후보라는 사실만으로 곡을 생성하지 않는다.

services.youtube_original은 Pydantic 판정 모델과 순수 규칙, 기존 recording_youtube_match의 곡명·버전·길이 비교를 사용한다. repositories.youtube_original은 owner·별칭·기존 녹음/발매를 읽고 저장 직전에 관계와 판정을 재검증한다. 기존 영상별 잠금과 계정/lease/snapshot 검증 안에서 명의·대상 녹음도 잠근다. 원문은 source_documents, 전후 값과 출처는 catalog_imports/catalog_changes에 보존한다. schema migration과 새 HTTP 경로는 없다.

YOUTUBE_POLL_INTERVAL_SECONDS=86400을 공유하며 runtime/agent guard는 바꾸지 않는다. 최초 기준선 이전 과거 수집과 근거 부족 후보의 재검토는 후속이다. 새 purpose를 구버전 collect worker가 해석하지 못하므로 poll·collect worker 모두 업데이트한 뒤 일일 처리를 활성화한다.

tests/test_youtube_original.py에서 키워드 유무·설명 근거·정확한 가창·미등록 협업·버전/예약/공개 상태·후보 전달·댓글/모델 미호출을 검사한다. PostgreSQL fixture는 생성/연결·감사/조회·재실행·기존 분류·소유 변경·기준선 보존을 검사한다. 기존 YouTube/Spotify/작업 키·매칭 회귀도 실행하며 실제 provider 호출은 테스트에서 하지 않는다.
