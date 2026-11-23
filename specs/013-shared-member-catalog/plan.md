# 공유 채널 멤버 연결 설계

FR-001~002: shared_youtube.py의 명시적 채널·멤버 규칙과 조회 CTE를 확장한다. 솔로 제목 및 검토한 듀엣/협업의 외부 영상 ID와 실제 publisher를 함께 확인한다. 그룹 owner는 유지한다.

추가 사용자 결정: HONK에만 allow_unnamed를 적용하고 MOCO/BAMBI를 완전한 이름 단위로 제목에서 찾는다. 외부 협업자 이름은 이 기본값을 막지 않으며, 같은 그룹의 이름이 하나라도 있으면 해당 이름만 적용한다. 검토 영상의 기존 기본 배정도 같은 채널의 명시적 이름에 우선하지 않는다. NUROJUNK의 미표기 정책과 본편/Shorts 판별은 유지한다.

FR-003~004: integrations/honk_youtube.py는 공식 멤버별 재생목록을 최대 20페이지 읽고 외부·비공개·불완전 항목을 제외한다. nurojunk_youtube.py는 검토한 24개 영상과 명시적 진행자 제목을 사용한다. repositories/shared_member_youtube.py는 owner·활성 관계·방송을 잠그고 진행자/멤버 연결과 감사를 같은 transaction에 저장한다. 타 가창자가 지정된 곡은 덮어쓰지 않는다. poll에서 기존 방송도 재대조하고 collect 저장 뒤에도 캐시 근거를 적용한다.

FR-004~005: catalog_read.SCOPE에서 네 개인 라이브/통계의 출처·비커버 범위를 제한한다. 원곡 MV의 기존 import는 삭제하지 않는다. CLI repair_shared_youtube_members.py는 검토한 영상 상세·재생목록 캐시로 누락 cover와 멤버 연결을 반영한다. 새 HTTP/schema migration·LLM·댓글 재수집·알림은 없다.

순수 규칙/API mock, disposable DB fixture, 별도 실제 DB/HTTP 대조와 재실행을 구분한다. [현재 계약과 결과](../../docs/shared-members-2026-11-22.md).
