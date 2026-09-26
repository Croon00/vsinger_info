"""Song candidate rules with fake provider clients; no network, no database."""
from app.integrations.song_catalogs import (
    CatalogArtist, CatalogFailure, CatalogName, CatalogRecording, CatalogWork)
from app.services.song_candidates import (
    ArtistIndex, Target, describe, existing_matches, latin_title, lookup, loose)

REC = "2944ccfe-3bb1-4a63-87e5-00778e2bad72"
WORK = "39319331-ab9d-4599-a3ef-a622f9f7e8aa"


def vocadb_work(external_id, title, producer, *, vocalist="初音ミク", romaji=None):
    names = [CatalogName(value=title, language="Japanese")]
    if romaji:
        names.append(CatalogName(value=romaji, language="Romaji"))
    return CatalogWork(provider="vocadb", external_id=external_id, title=title, names=names,
                       url=f"https://vocadb.net/S/{external_id}", artists=[
                           CatalogArtist(name=producer, role="producer", aliases=[producer + "P"]),
                           CatalogArtist(name=vocalist, role="vocalist")])


class FakeVocaDb:
    def __init__(self, works=(), fail=False):
        self.works, self.fail, self.queries = list(works), fail, []

    def search_originals(self, title):
        self.queries.append(title)
        if self.fail:
            raise CatalogFailure("rate_limited", retry=True)
        return list(self.works)


class FakeMusicBrainz:
    def __init__(self, recordings=(), works=()):
        self.recordings, self.works, self.calls = list(recordings), list(works), []

    def search_recordings(self, title, artist):
        self.calls.append(("recording", title, artist))
        return list(self.recordings)

    def works_for_recordings(self, ids):
        self.calls.append(("work", tuple(ids)))
        return list(self.works)


def key(title, artist, spellings=None):
    from app.core.song_keys import normalize_text
    return Target("key", 1, title, artist, normalize_text(title),
                  spellings if spellings is not None else ({normalize_text(artist)} if artist else set()))


def test_unique_title_and_producer_match_is_auto_and_stops_the_chain():
    utaite, mb = FakeVocaDb([vocadb_work("9", "ロキ", "みきと")]), FakeMusicBrainz()
    result = lookup(key("ロキ", "みきとP"), vocadb=FakeVocaDb([vocadb_work("1", "ロキ", "みきと", romaji="Roki")]),
                    utaitedb=utaite, musicbrainz=mb)
    assert result["status"] == "auto" and result["providers"] == ["vocadb"]
    assert not utaite.queries and not mb.calls
    [candidate] = result["candidates"]
    assert (candidate["title_latin"], candidate["artist_exact"]) == ("Roki", True)
    assert candidate["matched_artists"] == ["みきと"]


def test_same_title_other_artist_falls_through_to_musicbrainz_performer():
    recording = CatalogRecording(external_id=REC, title="プロローグ", credit="Uru",
                                 artists=[CatalogArtist(name="Uru", role="performer")])
    other = CatalogRecording(external_id="1f89de82-8be3-4249-924d-272b1291f17b", title="プロローグ (Instrumental)",
                             credit="Uru", artists=[CatalogArtist(name="Uru", role="performer")])
    work = CatalogWork(provider="musicbrainz_work", external_id=WORK, title="プロローグ", url="u",
                       names=[CatalogName(value="プロローグ", language="work"),
                              CatalogName(value="프롤로그", language="ko")],
                       artists=[CatalogArtist(name="Uru", role="composer")], recording_ids=[REC])
    mb = FakeMusicBrainz([recording, other], [work])
    result = lookup(key("プロローグ", "Uru"), vocadb=FakeVocaDb([vocadb_work("7", "プロローグ", "someone")]),
                    utaitedb=FakeVocaDb(), musicbrainz=mb)
    assert result["status"] == "auto" and result["providers"] == ["vocadb", "utaitedb", "musicbrainz"]
    assert mb.calls[1] == ("work", (REC,))  # the instrumental with a different title is not used
    best = next(c for c in result["candidates"] if c["artist_exact"])
    assert (best["provider"], best["title_ko"], best["recording_ids"]) == ("musicbrainz_work", "프롤로그", [REC])
    assert best["performers"][0]["name"] == "Uru"


def test_two_strong_candidates_or_vocalist_only_need_review():
    twins = FakeVocaDb([vocadb_work("1", "夜", "A"), vocadb_work("2", "夜", "A")])
    assert lookup(key("夜", "A"), vocadb=twins)["status"] == "review"
    result = lookup(key("夜", "初音ミク"), vocadb=FakeVocaDb([vocadb_work("1", "夜", "A")]))
    assert result["status"] == "review" and result["candidates"][0]["vocalist_only"]


def test_no_artist_is_not_looked_up_and_failures_are_reported():
    vocadb = FakeVocaDb([vocadb_work("1", "こんつきー", "A")])
    assert lookup(key("こんつきー", None), vocadb=vocadb)["status"] == "no_artist" and not vocadb.queries
    failed = lookup(key("夜", "A"), vocadb=FakeVocaDb(fail=True))
    assert failed["status"] == "error" and failed["errors"] == [{"provider": "vocadb", "code": "rate_limited"}]
    assert lookup(key("夜", "A"), vocadb=FakeVocaDb())["status"] == "none"


def test_width_variant_query_is_retried_normalized():
    vocadb = FakeVocaDb()
    lookup(key("ＬＯＶＥ", "A"), vocadb=vocadb)
    assert vocadb.queries == ["ＬＯＶＥ", "love"]


def test_our_artist_aliases_bridge_spellings():
    index = ArtistIndex({"mikito-p": {89}, "みきとp": {89}}, {89: {"mikito-p", "みきとp"}})
    spellings, ids = index.expand(" Mikito-P ")
    assert ids == [89] and "みきとp" in spellings
    result = lookup(key("ロキ", "Mikito-P", spellings), vocadb=FakeVocaDb([vocadb_work("1", "ロキ", "みきと")]))
    assert result["status"] == "auto"


def test_existing_song_found_by_stored_id_then_by_title_and_artist():
    candidate = lookup(key("ロキ", "みきとP"), vocadb=FakeVocaDb([vocadb_work("1", "ロキ", "みきと")]))["candidates"][0]
    songs = [{"id": 13, "title_key": "ロキ", "artist_spellings": {"みきとp"}},
             {"id": 14, "title_key": "ロキ", "artist_spellings": {"someone"}}]
    assert existing_matches(candidate, songs, {}) == [13]
    assert existing_matches(candidate, songs, {("vocadb", "1"): 99}) == [99]
    assert existing_matches(candidate, [songs[1]], {}) == []


def test_stored_work_of_another_artist_does_not_absorb_a_separate_version():
    work = CatalogWork(provider="musicbrainz_work", external_id=WORK, title="僕が死のうと思ったのは", url="u",
                       names=[], artists=[CatalogArtist(name="秋田ひろむ", role="composer")])
    target = key("僕が死のうと思ったのは", "中島美嘉")
    candidate = describe(work, target, performers=[CatalogArtist(name="中島美嘉", role="performer")])
    songs = [{"id": 208, "title_key": "僕が死のうと思ったのは", "artist_spellings": {"amazarashi"}},
             {"id": 10, "title_key": "僕が死のうと思ったのは", "artist_spellings": {"中島美嘉"}}]
    stored = {("musicbrainz_work", WORK): 208}
    assert existing_matches(candidate, songs, stored, target_spellings={"中島美嘉"}) == [10]
    assert existing_matches(candidate, songs, stored, target_spellings={"amazarashi"}) == [208]
    assert existing_matches(candidate, songs[:1], stored, target_spellings={"中島美嘉"}) == []



def test_loose_comparison_folds_tildes_dashes_and_spaces_only():
    assert loose("HELLO ～Paradise Kiss～") == loose("HELLO〜PARADISE KISS〜")
    assert loose("Butter-Fly") == loose("Butter‐Fly") and loose("松田 聖子") == loose("松田聖子")
    assert loose("PON PON PON") == loose("PONPONPON")
    assert loose("夜に駆ける") != loose("よるにかける") and loose("ロキ") != loose("ロキー")
    work = vocadb_work("3", "HELLO〜PARADISE KISS〜", "YUI")
    result = lookup(key("HELLO ～Paradise Kiss～", "YUI"), vocadb=FakeVocaDb([work]))
    assert result["status"] == "auto"


def test_english_translation_is_not_a_latin_title():
    work = CatalogWork(provider="vocadb", external_id="4", title="嘘月", url="u", artists=[],
                       names=[CatalogName(value="嘘月", language="Japanese"),
                              CatalogName(value="Liar Moon", language="English")])
    assert latin_title(work) is None
    work.names.append(CatalogName(value="Usotsuki", language="Romaji"))
    assert latin_title(work) == "Usotsuki"
    assert latin_title(vocadb_work("5", "Planetes", "ryo")) == "Planetes"