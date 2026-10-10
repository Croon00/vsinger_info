# 셋리스트 비곡 항목 정리 (2026-10-10)

사용자 요청으로 신규 catalog의 전체 활성 performances를 검사했다. 명확한
인사말, 이모티콘·기호만 있는 제목, 시작·종료·토크·자기소개·공지·후원금 읽기
표시를 목록에서 제외한다. 원문 source_documents, song master, 기존 DB는 변경하지 않는다.

`scripts/clean_setlist_markers.py`는 기본 미리보기이며 `--apply`로 soft archive한다.
복구용 전체 이전 행은 `db-migration/reports/setlist-cleanup-2026-10-10/before.json`,
반영 결과는 같은 디렉터리 `result.json`에 기록한다. version을 확인하고 증가시킨다.

`StaRt`, `START!!`, `START:DASH!!`, `アンコール`, `ありがとう`, `＋♂`, `∞`
등 실제 곡명은 유지한다. 곡명 내부 기호·이모티콘은 일괄 삭제하지 않는다.
이는 저장된 항목의 일회성 정리이며 수집기의 자동 필터는 변경하지 않는다.
규칙으로 판별하기 어려운 일반 문장과 곡명이 유실된 파싱 결과의 복원은 별도 검수 대상이다.

2026-10-10 검증: 실제 신규 DB 전체 활성 항목 검사, 제외 후 해당 ID의 활성 행 0건
확인, 실제 곡명 보존 및 진행 표시 판별의 로컬 assertion 검사.
Discord·Calendar·LLM 및 재수집은 실행하지 않는다.
