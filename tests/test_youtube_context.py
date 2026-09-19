import asyncio

import httpx

from app.integrations import youtube_context


def test_setlist_candidate_accepts_timestamp_ranges_and_reads_later_pages(monkeypatch) -> None:
    requests = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.params.get("pageToken"):
            return httpx.Response(200, json={"items": [{
                "snippet": {"topLevelComment": {"snippet": {
                    "textOriginal": "1曲目 08:36~13:14「変わらないもの／奥華子」 95.192点\n2曲目 15:57〜20:39『茜色の約束 / いきものがかり』 96.446点"
                }}}
            }]})
        return httpx.Response(200, json={
            "items": [{"snippet": {"topLevelComment": {"snippet": {"textOriginal": "nice stream"}}}}],
            "nextPageToken": "next",
        })

    client_class = httpx.AsyncClient
    monkeypatch.setattr(youtube_context.settings, "youtube_api_key", "test-key")
    monkeypatch.setattr(youtube_context.httpx, "AsyncClient", lambda **kwargs: client_class(
        **kwargs, transport=httpx.MockTransport(respond)
    ))

    result = asyncio.run(youtube_context.fetch_setlist_comment("video"))

    assert result is not None
    assert "変わらないもの" in result.text
    assert len(requests) == 2
