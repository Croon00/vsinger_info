# Artist names and catalogue identity

Current identity rules, reviewed against repository code on 2026-09-18.
For frontend contracts see [read API v2](read-api-v2.md); the planned native/Korean/alias separation is tracked in [the roadmap](backend-roadmap.md).

`app/data/artist_identities.json` contains reviewed name pairs and aliases. Known
kanji names use `Native (Latin)`; artists without kanji do not receive invented
kanji names. Spaces and underscores are ignored for alias matching, but fuzzy
matching and machine-generated transliterations are not used.

The existing profile seed provides the RIOT/V.W.P names and LIVE UNION native
names. Additional RK names are supported by the official
[roster](https://rkmusic.jp/info/30/) and [KISAKI profile](https://rkmusic.jp/artist/312/).
The six Girls Revolution Project names and Latin account identifiers are listed
in the [official KAMITSUBAKI pamphlet](https://kamitsubaki.jp/wp-content/uploads/2025/01/KAMICOLLE_Pamphlet.pdf).

## Data preservation

`GET /api/artists?grouped=true` presents one catalogue entry per confirmed identity.
The legacy grouped response retains related registration IDs, aliases and source metadata.
The new frontend uses `GET /api/artists`, a smaller read model with
`related_artist_ids`, `name_aliases` and active public source fields. It does not
expose source ownership or fetch a representative video for every artist.
Registration management uses the ungrouped endpoint: editing or deleting a
registration must not silently modify another owner's registration.

No artist, source, broadcast, event or notification record is deleted or moved.
Related IDs remain available for profile and event lookups. The catalog live scope
uses source-linked artist IDs first and unique exact registered aliases only for
source-less archives. Spotify lookup selects a linked registration within the group.
Legacy `display_name` may be `Native (Latin)`; it is not a Korean-name field.
The new frontend does not treat it as a Korean subtitle or invent a translation.

## Apply labels

Preview: `python scripts/normalize_artist_names.py`

Apply: `python scripts/normalize_artist_names.py --apply`

Only `display_name` and `updated_at` change. Initialization reapplies labels
idempotently, and presets/imports resolve curated aliases before inserting.
Changes to catalogue grouping require deploying the backend and frontend.

Checks: `python -m pytest tests/test_artist_identity.py tests/test_read_api.py`.
For frontend validation see the [QA guide](../web/docs/qa.md).
The official source links above are preserved provenance, not a new external
verification performed during the documentation cleanup.
# 사용자 지정 한글 이름 보완 (2026-11-21)

사용자 요청 표기를 신규 DB의 빈 `name_ko`에 반영했다: 오토노세 라코(ID 1041, otonose-raco), 스이우 시노(1044, suiu-shino), 니비이로 유루시(1045, nibiiro-yurushi), 아야무기(1046, yayamugi). 원어 이름·ID·소유권은 유지했다. 정확한 ID/slug를 확인한 dry-run 후 적용했으며 영수증 9924와 변경 이력 4건을 남겼다. 실제 프론트 프록시의 `/api/artists`에서 네 display_name을 대조했다. 사용자 지정 표기이며 별도 공식 한국어 표기 조사 결과는 아니다.
