from __future__ import annotations

import re
from html import unescape

import httpx


MAX_PAGE_TEXT_LENGTH = 6000


async def fetch_public_page_text(url: str) -> str | None:
    """Fetch a public page and return compact visible text for AI extraction."""
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=20,
            headers={"User-Agent": "UtaMowa/0.1"},
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
    except httpx.HTTPError:
        return None

    content_type = response.headers.get("content-type", "")
    if "text/html" not in content_type and "text/plain" not in content_type:
        return None

    text = _html_to_text(response.text)
    if not text:
        return None
    return text[:MAX_PAGE_TEXT_LENGTH]


def _html_to_text(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|noscript).*?>.*?</\1>", " ", html)
    html = re.sub(r"(?is)<br\s*/?>", "\n", html)
    html = re.sub(r"(?is)</(p|div|li|tr|h[1-6])>", "\n", html)
    html = re.sub(r"(?is)<[^>]+>", " ", html)
    text = unescape(html)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
