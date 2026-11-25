# 발매 커버 제외 설계

`app/repositories/released_cover_rules.py`의 `RELEASED_COVER_SQL`(녹음 별칭 `r`)과 `RELEASED_COVER_PARAMS`를 `song_explore.explore`의 오리지널 WHERE에 `AND NOT`으로 넣는다. 그룹 관계는 `artist_group_members`의 양방향(멤버→그룹, 그룹→멤버)으로 판정한다. 가사 내보내기(`scripts/export_original_lyrics.py`)는 같은 규칙으로 제외 목록 `excluded-covers.json`을 남긴다(`recording_lyrics.released_cover_entries`). DB 변경·마이그레이션은 없다.

공유 seed fixture의 녹음은 다른 아티스트에 크레딧된 곡에 연결돼 있어 새 규칙에서는 커버가 된다. 실제 데이터처럼 가창자를 원곡자로 추가하도록 오리지널 기대 테스트 3개(`test_original_recording_is_not_hidden_by_old_description_only_cover`, `test_artist_union_keeps_collaborator_names_and_scopes_before_pagination`, `test_filters_before_paging_and_recording_identity_guards`)를 고쳤다.
