# 관리자 가져오기 JSON v1

2026-09-20. 실제 관리자 API가 받는 형식이다. AI에 자료 정제를 맡길 때 이 문서와 `envelope.schema.json`, `resources.json`을 함께 제공한다.

- 최상위에는 `schema_version: "1"`, `entities`만 넣는다. 검수 묶음은 웹에서 선택한다.
- `entity_type`은 테이블 이름이다. 예: `artists`, `songs`, `performances`. 단수 이름은 받지 않는다.
- `client_ref`는 같은 검수 묶음 안에서 고유해야 한다. 기존 DB ID를 복사하지 않는다.
- 아직 저장하지 않은 항목은 외래키 자리에 `{"$ref":"artist:example"}`로 연결한다.
- 이미 새 DB에 있는 항목은 해당 숫자 ID로 연결할 수 있다. 원격 자료가 실제로 존재하는지는 반영 미리보기에서 확인한다.
- `operation`은 `create`(기본) 또는 `update`. 수정에는 `target_id`와 `expected_version`이 필요하다. 수정에서 생략한 값은 유지하고, 명시적인 null은 비운다.
- 필드명·필수 여부·허용값은 resources 파일을 따른다. 모든 날짜시간에는 UTC offset을 넣는다. 예: `2026-09-20T19:00:00+09:00`.
- 검수/승인 상태, 새 ID, 비밀번호, SQL, 실행 명령을 넣지 않는다. 출처는 `provenance` 또는 `source_documents`로 남긴다.
- 파일당 10MiB, 최대 1,000개 항목. 한 검수 묶음 안에서 여러 파일의 참조를 연결할 수 있다. 다른 묶음의 초안 참조는 지원하지 않는다.
- 이름이 같아도 자동 병합하지 않는다. 한국어 표기 등 모르는 값은 만들지 말고 null로 둔다.
- JSON Schema는 필드 형식 검사에 사용한다. 날짜 간 관계·참조 존재·DB 고유값 등은 관리자 API가 추가 검사한다.

다음은 **형식 설명용 가상 예시**다. 실제 자료로 바꾸어 검수해야 하며 자동으로 가져오거나 반영하지 않는다.

```json
{
  "schema_version": "1",
  "entities": [
    {
      "client_ref": "artist:example",
      "entity_type": "artists",
      "data": {
        "slug": "replace-with-reviewed-artist",
        "name_native": "검수할 아티스트 원어 이름",
        "entity_kind": "solo",
        "show_in_catalog": false
      },
      "provenance": {"note": "직접 확인한 출처로 교체"}
    },
    {
      "client_ref": "song:example",
      "entity_type": "songs",
      "data": {"title_native": "검수할 곡 원어 제목", "title_ko": null}
    },
    {
      "client_ref": "song-artist:example",
      "entity_type": "song_artists",
      "data": {
        "song_id": {"$ref": "song:example"},
        "artist_id": {"$ref": "artist:example"}
      }
    }
  ]
}
```

계약을 수정했다면 루트에서 `python scripts/export_admin_contract.py`로 생성 파일을 갱신한다.
