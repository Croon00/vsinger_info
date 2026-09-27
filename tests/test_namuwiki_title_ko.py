"""Namu Wiki title lookup helpers (no network: mock transport)."""
import importlib.util
import json
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("namuwiki_title_ko", ROOT / "scripts/namuwiki_title_ko.py")
nw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nw)


def page(title, body, status=200):
    return httpx.Response(status, text=f"<html><head><title>{title} - 나무위키</title></head>"
                                       f"<body><script>x()</script>{body}</body></html>")


def test_names_and_text():
    assert nw.korean_name("불꽃(VOCALOID 오리지널 곡)") == "불꽃"
    assert nw.korean_name("裸の心") is None and nw.korean_name(None) is None
    assert nw.page_title("<title>밤을 달리다 - 나무위키</title>") == "밤을 달리다"
    assert nw.plain_text("<p>a&amp;b</p><script>no()</script>") == "a&b"
    assert nw.artist_on_page("작곡 DECO*27 가수 하츠네 미쿠", [{"name": "DECO*27"}])
    assert not nw.artist_on_page("다른 곡", [{"name": "DECO*27", "name_ko": None}])


def test_lookup_tries_artist_variant_and_caches(tmp_path):
    calls = []

    def respond(request):
        calls.append(request.url.path)
        if request.url.path == "/w/プロローグ":
            return page("プロローグ", "없는 문서", 404)
        return page("프롤로그(Uru)", "최근 수정 시각 Uru의 곡 プロローグ")

    namu = nw.Namu(tmp_path, transport=httpx.MockTransport(respond), interval=0)
    song = {"song_id": 1, "title_native": "プロローグ", "artists": [{"name": "Uru", "name_ko": None}]}
    result = nw.lookup(song, namu)
    assert [t["status"] for t in result["tried"]] == [404, 200] and result["title_ko"] == "프롤로그"
    assert result["where"] == "title" and not result["needs_content_check"]
    assert nw.lookup(song, namu)["title_ko"] == "프롤로그" and len(calls) == 2      # served from the cache
    reading = nw.excerpt(namu.get("プロローグ(Uru)"), song)
    assert reading.startswith("URL: ") and "DOCUMENT TITLE: 프롤로그(Uru)" in reading
    namu.close()


def test_excerpt_keeps_passages_after_the_opening():
    text = "메뉴 최근 수정 시각 " + "가" * 50 + " 오프닝 春擬き(봄 흉내) 설명"
    reading = nw.excerpt({"url": "u", "title": "애니", "text": text}, {"title_native": "春擬き"}, head=20, around=10)
    assert "PASSAGES WITH THE NATIVE TITLE" in reading and "春擬き(봄 흉내)" in reading
