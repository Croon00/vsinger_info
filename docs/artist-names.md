# Artist names and catalogue identity

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

`GET /artists?grouped=true` presents one catalogue entry per confirmed identity.
The response retains `related_artist_ids`, `name_aliases`, all source IDs, and
source ownership. Profiles, visibility flags and images are combined for display.
Registration management uses the ungrouped endpoint: editing or deleting a
registration must not silently modify another owner's registration.

No artist, source, broadcast, event or notification record is deleted or moved.
Old profile URLs and event filters resolve all related IDs. Broadcast queries
accept either native or Latin aliases. Spotify uses an existing matched
registration preferentially, and displays the local bilingual label.

## Apply labels

Preview: `python scripts/normalize_artist_names.py`

Apply: `python scripts/normalize_artist_names.py --apply`

Only `display_name` and `updated_at` change. Initialization reapplies labels
idempotently, and presets/imports resolve curated aliases before inserting.
Changes to catalogue grouping require deploying the backend and frontend.

Checks: `python -m pytest tests/test_artist_identity.py`, `cd web` followed by
`npm run test:e2e` and `npm run build`.
