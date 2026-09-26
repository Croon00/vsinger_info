"""VocaDB/UtaiteDB and MusicBrainz adapters against mock transports; no network."""
import httpx
import pytest

from app.integrations.song_catalogs import CatalogFailure, MusicBrainzClient, VocaDbClient

MB_WORK = "39319331-ab9d-4599-a3ef-a622f9f7e8aa"
MB_REC = "2944ccfe-3bb1-4a63-87e5-00778e2bad72"


def vocadb_item(**extra):
    item = {
        "id": 19094, "songType": "Original", "defaultName": "ロストワンの号哭", "defaultNameLanguage": "Japanese",
        "names": [{"language": "Japanese", "value": "ロストワンの号哭"},
                  {"language": "Romaji", "value": "Lost One no Goukoku"}, {"language": "English", "value": ""}],
        "artists": [
            {"categories": "Producer", "name": "Neru", "isSupport": False,
             "artist": {"id": 1, "name": "Neru", "additionalNames": "押入れP, Oshiire-P"}},
            {"categories": "Vocalist", "name": "鏡音リン", "artist": {"id": 14, "name": "鏡音リン"}},
            {"categories": "Other", "name": "helper", "isSupport": True, "artist": {"id": 99, "name": "helper"}},
            {"categories": "Producer", "name": "custom credit"},
        ],
    }
    item.update(extra)
    return item


class Recorder:
    def __init__(self, *responses):
        self.responses, self.requests = list(responses), []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.responses.pop(0)


def client(cls, recorder, **kw):
    sleeps = []
    return cls(transport=httpx.MockTransport(recorder), sleep=sleeps.append, clock=lambda: 0.0, **kw), sleeps


def test_vocadb_parses_originals_and_credit_roles():
    rec = Recorder(httpx.Response(200, json={"items": [vocadb_item(), vocadb_item(id=5, songType="Cover")]}))
    api, _ = client(VocaDbClient, rec)
    works = api.search_originals("ロストワンの号哭")
    assert [w.external_id for w in works] == ["19094"]
    work = works[0]
    assert (work.provider, work.url, work.title) == ("vocadb", "https://vocadb.net/S/19094", "ロストワンの号哭")
    assert [(a.name, a.role, a.external_id) for a in work.artists] == [
        ("Neru", "producer", "1"), ("鏡音リン", "vocalist", "14"), ("custom credit", "producer", None)]
    assert work.artists[0].aliases == ["押入れP", "Oshiire-P"]
    assert [n.language for n in work.names] == ["Japanese", "Romaji"]
    params = rec.requests[0].url.params
    assert (params["nameMatchMode"], params["songTypes"], params["fields"]) == ("Exact", "Original", "Names,Artists")
    assert "schedule_music" in rec.requests[0].headers["User-Agent"]


def test_utaitedb_uses_its_own_site_and_cache_skips_repeat_calls():
    rec = Recorder(httpx.Response(200, json={"items": [vocadb_item()]}))
    cache = {}
    api, _ = client(VocaDbClient, rec, provider="utaitedb", cache=cache)
    assert api.search_originals("x")[0].url == "https://utaitedb.net/S/19094"
    assert api.search_originals("x")[0].external_id == "19094"
    assert len(rec.requests) == 1 and rec.requests[0].url.host == "utaitedb.net"


def test_retries_503_with_retry_after_then_succeeds():
    rec = Recorder(httpx.Response(503, headers={"Retry-After": "7"}), httpx.Response(200, json={"items": []}))
    api, sleeps = client(VocaDbClient, rec)
    assert api.search_originals("x") == []
    assert 7.0 in sleeps and len(rec.requests) == 2


@pytest.mark.parametrize("response, code", [
    (httpx.Response(404, json={}), "http_404"),
    (httpx.Response(200, content=b"not json"), "malformed_response"),
    (httpx.Response(200, json={"items": "nope"}), "malformed_response"),
])
def test_permanent_failures_are_not_retried(response, code):
    rec = Recorder(response)
    api, _ = client(VocaDbClient, rec)
    with pytest.raises(CatalogFailure) as exc:
        api.search_originals("x")
    assert exc.value.code == code and len(rec.requests) == 1


def test_persistent_rate_limit_gives_up_after_bounded_retries():
    rec = Recorder(*[httpx.Response(429) for _ in range(4)])
    api, _ = client(MusicBrainzClient, rec)
    with pytest.raises(CatalogFailure) as exc:
        api.search_recordings("a", "b")
    assert exc.value.code == "rate_limited" and exc.value.retry and len(rec.requests) == 4


def test_musicbrainz_recording_search_escapes_phrases_and_parses_credit():
    body = {"recordings": [{"id": MB_REC, "score": 100, "title": "勇者", "artist-credit": [
        {"name": "YOASOBI", "joinphrase": " feat. ", "artist": {"id": "a" * 8, "name": "YOASOBI", "sort-name": "YOASOBI"}},
        {"name": "幾田りら", "artist": {"id": "b" * 8, "name": "幾田りら", "sort-name": "Ikuta, Lilas"}}]},
        {"id": "bad", "title": "x"}]}
    rec = Recorder(httpx.Response(200, json=body))
    api, _ = client(MusicBrainzClient, rec)
    [recording] = api.search_recordings('say "hi"', "YOASOBI")
    assert recording.credit == "YOASOBI feat. 幾田りら"
    assert recording.artists[1].aliases == ["Ikuta, Lilas"]
    assert rec.requests[0].url.params["query"] == 'recording:"say \\"hi\\"" AND artist:"YOASOBI"'


def test_musicbrainz_works_by_recording_ids():
    body = {"works": [{"id": MB_WORK, "title": "勇者", "language": "jpn",
                       "aliases": [{"name": "Yuusha", "locale": "ja-Latn"}, {"name": "용사", "locale": "ko"}],
                       "relations": [{"type": "composer", "artist": {"id": "c" * 8, "name": "Ayase"}},
                                     {"type": "performance", "recording": {"id": MB_REC}}]},
                      {"id": "not-an-mbid", "title": "broken"}]}
    rec = Recorder(httpx.Response(200, json=body))
    api, _ = client(MusicBrainzClient, rec)
    assert api.works_for_recordings(["junk"]) == [] and not rec.requests
    [work] = api.works_for_recordings([MB_REC, MB_REC])
    assert work.url == f"https://musicbrainz.org/work/{MB_WORK}" and work.recording_ids == [MB_REC]
    assert [(a.name, a.role) for a in work.artists] == [("Ayase", "composer")]
    assert [(n.value, n.language) for n in work.names] == [("勇者", "work"), ("Yuusha", "ja-Latn"), ("용사", "ko")]
    assert rec.requests[0].url.params["query"] == f"rid:{MB_REC}"


def test_request_spacing_is_enforced():
    rec = Recorder(httpx.Response(200, json={"items": []}), httpx.Response(200, json={"items": []}))
    sleeps, now = [], [0.0]
    api = VocaDbClient(transport=httpx.MockTransport(rec), interval=1.0, sleep=sleeps.append, clock=lambda: now[0])
    api.search_originals("a")
    now[0] = 0.25
    api.search_originals("b")
    assert sleeps == [0.75]
