# 라이브 5850 세트리스트 정정

2026-10-07 사용자 요청으로 신규 통합 운영 DB에 반영했다.

- 대상: archive `5850`, video `6642`, YouTube `e9mcsY5gVC8`, 아티스트 `27`(深影).
- 근거: [14곡 세트리스트 댓글](https://www.youtube.com/watch?v=e9mcsY5gVC8&lc=UgyPJCWjrgLwuN6k7Qp4AaABAg). 적용 전 실제 공개 댓글을 다시 조회하고 곡명·원곡자·시작 시각을 대조했다. LLM 호출은 하지 않았다.
- 기존 잡담 가창 `75080–75095` 16개는 `archived_at`으로 보관했다. 원문 문서 `6789`와 기존 관계는 유지했다. 보관 행에도 적용되는 ordinal 고유 제약 때문에 기존 ordinal에 1000을 더했으며, 변경 전 ordinal을 포함한 전체 행은 감사 이력의 `before_data`에 보존했다.
- 새 가창 `228840–228853` 14개, 원문 문서 `19266`, `archive_sources` 근거 관계를 생성했다. 첫 곡은 `00:06:30 STAND-ALONE / Aimer`, 마지막 곡은 `03:12:41 楓 / スピッツ`다.
- 이미 확정된 곡 매칭으로 10곡을 연결했다. 나머지 4곡은 원문을 유지하며 `song_id=NULL`로 두었고 새 작품을 추측하여 생성하지 않았다.
- 현재 단일 채널 owner인 아티스트 27을 새 가창 14개의 lead로 연결했다. 감사 provenance에 `basis=channel_owner`, `review_status=provisional`을 기록했다. 기존 잘못된 16개에는 가창자 관계가 없었다.
- `setlist_state=partial` 유지. 정정은 영상 직접 청취에 의한 전체 검수를 뜻하지 않는다.

원본 snapshot과 일치하는지 잠금 아래에서 확인하고, 새 원문·보관·가창·크레딧·감사 기록을 단일 transaction으로 반영했다. 초기 두 시도는 영수증 UPDATE가 append-only 제약에 걸려 전부 롤백됐다. 최종 시도는 모든 영수증과 감사 행을 INSERT로만 생성했다.

정정 영수증은 `catalog_imports.id=5590`, `source_kind=correction`, 정책은 `live-5850-setlist-correction-2026-10-07`이다. `catalog_changes` 47개에 기존 가창 보관 16개, 새 가창 14개, 크레딧 14개, 새 원문·출처 관계·archive 변경 각 1개를 기록했다. 이전 이력과 다른 라이브는 변경하지 않았다.

검증: 커밋 후 읽기 전용 조회에서 활성 가창 14개·보관 가창 16개와 47개 감사 행을 확인했다. 현재 로컬 FastAPI 조회 router를 운영 DB의 읽기 전용 session으로 호출해 `/api/lives/5850` HTTP 200, 14곡, 첫·마지막 시작 시각을 확인했다. 원래 제공된 Railway 도메인의 동일 API는 HTTP 404를 반환하여 배포된 화면 확인은 완료하지 못했다. 이는 운영 DB 정정 검증과 구분한다.
