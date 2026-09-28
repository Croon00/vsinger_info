"""Small, polite readers for public Z-aN and ZAIKO event pages."""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx

JST = timezone(timedelta(hours=9))
USER_AGENT = "schedule_music/1.0 (+public event calendar; daily polling)"
ZAN_CHANNELS = {
    "rkmusic": "https://www.zan-live.com/ko/channel/rkmusic",
    "virtual_kaf": "https://www.zan-live.com/ko/channel/virtual_kaf",
    "RIM_virtual": "https://www.zan-live.com/ko/channel/RIM_virtual",
    "KOKO__virtual": "https://www.zan-live.com/ko/channel/KOKO__virtual",
    "harusaruhi": "https://www.zan-live.com/ko/channel/harusaruhi",
    "isekaijoucho": "https://www.zan-live.com/ko/channel/isekaijoucho",
}
ZAIKO_CHANNEL = "https://riotmusic-live.zaiko.io/en/"
RIOT_INFO_PAGES = {
    "riot_info": "https://riot-music.com/info/",
    "mugensho_info": "https://riot-music.com/mugensho-record/info/",
}
_ZAN_DETAIL = re.compile(r"^/(?:ko|ja|en)/live/detail/(\d+)/?$")
_ZAIKO_DETAIL = re.compile(r"^/(?:[a-z-]+/)?(?:e|item)/[A-Za-z0-9_-]+/?$")
_RIOT_ARTICLE = re.compile(r"^/(?:mugensho-record/)?info/(?:20\d{2}/\d{2}/\d{2}/)?\d+/?$")
_KOREAN_DATE = re.compile(r"(20\d{2})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일")
_JAPANESE_DATE = re.compile(r"(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")
_NUMERIC_DATE = re.compile(r"(20\d{2})[./-](\d{1,2})[./-](\d{1,2})")
_START_TIME = re.compile(r"(?:공연\s*시작\s*시간|開演|Start|START)\s*[:：()\s]*([01]?\d|2[0-3]):([0-5]\d)", re.I)


@dataclass(frozen=True)
class PublicLive:
    source_url: str
    title: str
    event_date: date
    starts_at: datetime | None
    event_format: str
    venue: str | None
    excerpt: str
    ticket_url: str | None = None


class _Document(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, int]] = []
        self.text: list[str] = []
        self.meta: dict[str, str] = {}
        self.json_ld: list[str] = []
        self._hidden = 0
        self._json_script = False
        self._script_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "a" and values.get("href"):
            self.links.append((values["href"] or "", len(self.text)))
        if tag == "meta":
            key = values.get("property") or values.get("name")
            if key and values.get("content"):
                self.meta[key.lower()] = values["content"] or ""
        if tag == "script":
            self._json_script = values.get("type") == "application/ld+json"
            self._script_parts = []
            self._hidden += 1
        elif tag in {"style", "noscript"}:
            self._hidden += 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            if self._json_script:
                self.json_ld.append("".join(self._script_parts))
            self._json_script = False
            self._hidden = max(0, self._hidden - 1)
        elif tag in {"style", "noscript"}:
            self._hidden = max(0, self._hidden - 1)

    def handle_data(self, data: str) -> None:
        if self._json_script:
            self._script_parts.append(data)
        elif not self._hidden:
            value = " ".join(data.split())
            if value:
                self.text.append(value)


def _document(html: str) -> _Document:
    result = _Document()
    result.feed(html)
    return result


def event_links(channel_url: str, html: str) -> list[str]:
    """Only follow detail links on the channel's own host."""
    host = urlparse(channel_url).hostname
    found: dict[str, None] = {}
    doc = _document(html)
    # Z-aN repeats site-wide recommendations above every channel's own event list.
    start = next((i for i, value in enumerate(doc.text) if value in {"최신 이벤트", "最新イベント", "Latest Events"}), None)
    if host == "www.zan-live.com" and start is None:
        return []
    for href, position in doc.links:
        if start is not None and position < start:
            continue
        candidate = urljoin(channel_url, href).split("?", 1)[0].split("#", 1)[0]
        parsed = urlparse(candidate)
        if parsed.scheme != "https" or parsed.hostname != host:
            continue
        if host == "www.zan-live.com":
            match = _ZAN_DETAIL.fullmatch(parsed.path)
            if match:
                found[f"https://www.zan-live.com/ko/live/detail/{match.group(1)}"] = None
        elif host == "riotmusic-live.zaiko.io" and _ZAIKO_DETAIL.fullmatch(parsed.path):
            found[candidate] = None
        elif host == "riot-music.com" and _RIOT_ARTICLE.fullmatch(parsed.path):
            found[candidate] = None
    return list(found)[:24]


def _schema_event(doc: _Document) -> dict | None:
    for script in doc.json_ld:
        try:
            payload = json.loads(script)
        except ValueError:
            continue
        queue = payload if isinstance(payload, list) else [payload]
        while queue:
            item = queue.pop(0)
            if not isinstance(item, dict):
                continue
            kinds = item.get("@type", [])
            if kinds == "Event" or "Event" in kinds:
                return item
            queue.extend(x for x in item.get("@graph", []) if isinstance(x, dict))
    return None


def parse_live_detail(url: str, html: str) -> PublicLive | None:
    """Use structured Event data first; fall back to visible Z-aN labels."""
    doc = _document(html)
    riot_article = urlparse(url).hostname == "riot-music.com"
    ticket_url = next((
        link for href, _ in doc.links
        if (link := urljoin(url, href)).startswith("https://riotmusic-live.zaiko.io/")
        and _ZAIKO_DETAIL.fullmatch(urlparse(link).path)
    ), None)
    if riot_article and not ticket_url:
        return None
    schema = _schema_event(doc)
    title = str((schema or {}).get("name") or doc.meta.get("og:title") or "").strip()
    title = re.sub(r"\s+[|｜-]\s+Z-aN$", "", title).strip()
    if riot_article:
        title = re.split(r"\s*[|｜]\s*(?:INFORMATION|RIOT MUSIC|無原唱レコード)", title, maxsplit=1)[0].strip()
    if not title:
        return None

    visible = " ".join(doc.text)
    date_match = re.search(
        r"(?:개최일|開催日|公演日時|開催日時|公演日程|日程)\s*[:：]?(.{0,220})", visible
    )
    date_context = date_match.group(1) if date_match else ("" if riot_article else visible[:1000])
    raw_start = (schema or {}).get("startDate")
    starts_at = None
    event_date = None
    if isinstance(raw_start, str):
        try:
            if len(raw_start) == 10:
                event_date = date.fromisoformat(raw_start)
            else:
                starts_at = datetime.fromisoformat(raw_start.replace("Z", "+00:00"))
                if starts_at.tzinfo is None:
                    starts_at = starts_at.replace(tzinfo=JST)
                event_date = starts_at.astimezone(JST).date()
        except ValueError:
            pass
    if event_date is None:
        match = (_KOREAN_DATE.search(date_context) or _JAPANESE_DATE.search(date_context)
                 or _NUMERIC_DATE.search(date_context))
        if not match:
            return None
        try:
            event_date = date(*(int(value) for value in match.groups()))
        except ValueError:
            return None
        time_match = _START_TIME.search(date_context[:200])
        if time_match:
            starts_at = datetime.combine(event_date, time(int(time_match[1]), int(time_match[2])), JST)

    location = (schema or {}).get("location")
    venue = location.get("name") if isinstance(location, dict) else None
    if not venue:
        venue_match = re.search(r"[＜<]会場[＞>]\s*([^\s（）()]{2,80})", visible)
        venue = venue_match.group(1) if venue_match else None
    summary = "" if riot_article else doc.meta.get("description", "")
    if not summary:
        # Z-aN repeats site-wide recommendations before the event body. Start at
        # the event title closest to its date label so unrelated artists cannot
        # become participants through the recommendation carousel.
        body_start = date_match.start() if date_match else 0
        title_start = visible.rfind(title, 0, body_start) if body_start else -1
        if title_start >= 0:
            body_start = title_start
        summary = visible[body_start:body_start + 1800]
    # A Z-aN detail page can include both a venue and a stream ticket.
    context = summary.lower()
    onsite = bool(venue or re.search(r"会場|행사장|現地|venue", context))
    streaming = bool(re.search(r"配信|스트리밍|streaming|온라인", context))
    event_format = "hybrid" if onsite and streaming else "onsite" if onsite else "online"
    return PublicLive(url, title, event_date, starts_at, event_format, venue, summary[:1800], ticket_url)


class PublicSiteReader:
    def __init__(self, client: httpx.AsyncClient):
        self.client = client
        self._robots: dict[str, RobotFileParser | None] = {}

    async def get(self, url: str) -> str:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in self._robots:
            response = await self.client.get(f"{origin}/robots.txt", timeout=15)
            if response.status_code == 404:
                self._robots[origin] = None
            elif response.status_code == 200:
                rules = RobotFileParser()
                rules.parse(response.text.splitlines())
                self._robots[origin] = rules
            else:
                response.raise_for_status()
        rules = self._robots[origin]
        if rules is not None and not rules.can_fetch(USER_AGENT, url):
            raise PermissionError(f"robots.txt disallows {parsed.path}")
        await asyncio.sleep(0.5)
        response = await self.client.get(url, timeout=20)
        response.raise_for_status()
        return response.text
