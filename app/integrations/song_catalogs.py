"""Read-only lookups of original works in VocaDB/UtaiteDB and MusicBrainz.

These adapters only *propose* song-master candidates: they search by exact title and
return normalized models. Deciding that a setlist line is a given song, and any database
write, happens elsewhere after review. VocaDB/UtaiteDB content is CC BY 4.0 (keep the
entry URL for attribution); MusicBrainz core data is CC0. Lyrics are never requested.
"""
from __future__ import annotations

import re
import time
from email.utils import parsedate_to_datetime
from datetime import UTC, datetime
from typing import Callable, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field

USER_AGENT = "schedule_music-song-master/0.1 ( https://github.com/Croon00/vsinger_info )"
MBID = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
VOCADB_SITES = {"vocadb": "https://vocadb.net", "utaitedb": "https://utaitedb.net"}
MAX_RETRY_AFTER = 120.0


class CatalogFailure(Exception):
    def __init__(self, code: str, *, retry: bool = False):
        super().__init__(code)
        self.code, self.retry = code, retry


class CatalogName(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str = Field(min_length=1)
    language: str  # VocaDB: Japanese/Romaji/English/Unspecified; MusicBrainz: locale or "work"


class CatalogArtist(BaseModel):
    model_config = ConfigDict(extra="forbid")
    external_id: str | None = None  # absent for VocaDB custom-name credits
    name: str = Field(min_length=1)
    aliases: list[str] = []
    role: str  # producer, circle, band, vocalist, performer, composer, lyricist, writer, other


class CatalogWork(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: Literal["vocadb", "utaitedb", "musicbrainz_work"]
    external_id: str = Field(min_length=1)
    title: str = Field(min_length=1)  # original-language title as the provider shows it
    names: list[CatalogName]
    artists: list[CatalogArtist]
    url: str
    language: str | None = None
    recording_ids: list[str] = []  # MusicBrainz: recordings linked by a performance relation


class CatalogRecording(BaseModel):
    model_config = ConfigDict(extra="forbid")
    external_id: str = Field(pattern=MBID)
    title: str = Field(min_length=1)
    credit: str  # full artist credit as printed, joinphrases included
    artists: list[CatalogArtist]
    score: int = 0


def _retry_after(response: httpx.Response) -> float | None:
    header = response.headers.get("Retry-After", "")
    try:
        return max(0.0, float(header))
    except ValueError:
        try:
            return max(0.0, (parsedate_to_datetime(header) - datetime.now(UTC)).total_seconds())
        except (TypeError, ValueError):
            return None


class _Http:
    """One polite client per provider: fixed spacing, bounded retries, optional cache."""

    def __init__(self, base_url: str, *, interval: float, transport=None, retries: int = 3,
                 cache: dict | None = None, sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic):
        self.base_url, self.interval, self.retries, self.cache = base_url, interval, retries, cache
        self.sleep, self.clock, self.last = sleep, clock, None
        self.requests = 0
        self.client = httpx.Client(base_url=base_url, timeout=30, transport=transport,
                                   headers={"User-Agent": USER_AGENT, "Accept": "application/json"})

    def close(self) -> None:
        self.client.close()

    def get(self, path: str, params: dict) -> dict:
        key = self.base_url + path + "?" + "&".join(f"{k}={params[k]}" for k in sorted(params))
        if self.cache is not None and key in self.cache:
            return self.cache[key]
        for attempt in range(self.retries + 1):
            if self.last is not None:
                wait = self.interval - (self.clock() - self.last)
                if wait > 0:
                    self.sleep(wait)
            self.last = self.clock()
            self.requests += 1
            try:
                response = self.client.get(path, params=params)
            except httpx.TransportError:
                if attempt < self.retries:
                    self.sleep(2.0 * 2 ** attempt)
                    continue
                raise CatalogFailure("transport", retry=True) from None
            if response.status_code == 429 or response.status_code >= 500:
                if attempt < self.retries:
                    delay = _retry_after(response)
                    self.sleep(min(MAX_RETRY_AFTER, delay if delay is not None else 2.0 * 2 ** attempt))
                    continue
                raise CatalogFailure("rate_limited" if response.status_code in (429, 503) else "provider_error",
                                     retry=True)
            if response.is_error:
                raise CatalogFailure(f"http_{response.status_code}")
            try:
                value = response.json()
            except ValueError:
                raise CatalogFailure("malformed_response") from None
            if not isinstance(value, dict):
                raise CatalogFailure("malformed_response")
            if self.cache is not None:
                self.cache[key] = value
            return value
        raise CatalogFailure("retry_exhausted", retry=True)  # pragma: no cover - loop always returns/raises


def _text(value) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


_VOCADB_ROLES = (("Producer", "producer"), ("Circle", "circle"), ("Band", "band"), ("Vocalist", "vocalist"))


def work_from_vocadb(provider: str, item: dict) -> CatalogWork:
    if not isinstance(item, dict) or not isinstance(item.get("id"), int) or item["id"] <= 0:
        raise ValueError("invalid VocaDB song id")
    title = _text(item.get("defaultName")) or _text(item.get("name"))
    if not title:
        raise ValueError("VocaDB song without a name")
    names = [CatalogName(value=n["value"].strip(), language=str(n.get("language") or "Unspecified"))
             for n in item.get("names") or [] if isinstance(n, dict) and _text(n.get("value"))]
    artists = []
    for credit in item.get("artists") or []:
        if not isinstance(credit, dict) or credit.get("isSupport"):
            continue
        entry = credit.get("artist") if isinstance(credit.get("artist"), dict) else {}
        if entry.get("deleted"):
            continue
        name = _text(credit.get("name")) or _text(entry.get("name"))
        if not name:
            continue
        categories = str(credit.get("categories") or "")
        role = next((mapped for flag, mapped in _VOCADB_ROLES if flag in categories), "other")
        aliases = [a.strip() for a in str(entry.get("additionalNames") or "").split(",") if a.strip()]
        if _text(entry.get("name")) and entry["name"].strip() != name:
            aliases.insert(0, entry["name"].strip())
        artist_id = entry.get("id")
        artists.append(CatalogArtist(external_id=str(artist_id) if isinstance(artist_id, int) and artist_id > 0 else None,
                                     name=name, aliases=aliases, role=role))
    return CatalogWork(provider=provider, external_id=str(item["id"]), title=title, names=names, artists=artists,
                       url=f"{VOCADB_SITES[provider]}/S/{item['id']}",
                       language=_text(item.get("defaultNameLanguage")))


class VocaDbClient:
    """VocaDB and UtaiteDB share one API; ``provider`` picks the site."""

    def __init__(self, provider: Literal["vocadb", "utaitedb"] = "vocadb", *, transport=None,
                 interval: float = 1.0, cache: dict | None = None, sleep=time.sleep, clock=time.monotonic):
        self.provider = provider
        self.http = _Http(VOCADB_SITES[provider], interval=interval, transport=transport, cache=cache,
                          sleep=sleep, clock=clock)

    def close(self) -> None:
        self.http.close()

    def search_originals(self, title: str, *, limit: int = 10) -> list[CatalogWork]:
        """Original (non-cover) songs having a name exactly equal to ``title``."""
        data = self.http.get("/api/songs", {
            "query": title, "nameMatchMode": "Exact", "songTypes": "Original", "fields": "Names,Artists",
            "lang": "Default", "maxResults": min(max(limit, 1), 50), "preferAccurateMatches": "true",
            "sort": "FavoritedTimes"})
        items = data.get("items")
        if not isinstance(items, list):
            raise CatalogFailure("malformed_response")
        works = []
        for item in items:
            if isinstance(item, dict) and item.get("songType", "Original") == "Original" and not item.get("deleted"):
                try:
                    works.append(work_from_vocadb(self.provider, item))
                except ValueError:
                    continue
        return works


def _lucene_phrase(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _mb_artists(credits) -> tuple[str, list[CatalogArtist]]:
    printed, artists = "", []
    for credit in credits or []:
        if not isinstance(credit, dict) or not isinstance(credit.get("artist"), dict):
            continue
        entry = credit["artist"]
        name = _text(credit.get("name")) or _text(entry.get("name"))
        if not name:
            continue
        printed += name + str(credit.get("joinphrase") or "")
        aliases = [v for v in (_text(entry.get("name")), _text(entry.get("sort-name"))) if v and v != name]
        artist_id = entry.get("id") if isinstance(entry.get("id"), str) else None
        artists.append(CatalogArtist(external_id=artist_id, name=name, aliases=aliases, role="performer"))
    return printed.strip(), artists


def recording_from_musicbrainz(item: dict) -> CatalogRecording:
    if not isinstance(item, dict) or not _text(item.get("title")):
        raise ValueError("invalid recording")
    credit, artists = _mb_artists(item.get("artist-credit"))
    return CatalogRecording(external_id=item.get("id"), title=item["title"].strip(), credit=credit,
                            artists=artists, score=int(item.get("score") or 0))


def work_from_musicbrainz(item: dict) -> CatalogWork:
    if not isinstance(item, dict) or not _text(item.get("title")):
        raise ValueError("invalid work")
    title = item["title"].strip()
    names = [CatalogName(value=title, language="work")]
    for alias in item.get("aliases") or []:
        if isinstance(alias, dict) and _text(alias.get("name")):
            names.append(CatalogName(value=alias["name"].strip(), language=str(alias.get("locale") or "Unspecified")))
    artists, recordings = [], []
    for rel in item.get("relations") or []:
        if not isinstance(rel, dict):
            continue
        if rel.get("type") == "performance" and isinstance(rel.get("recording"), dict):
            recordings.append(str(rel["recording"].get("id")))
        elif rel.get("type") in ("composer", "lyricist", "writer") and isinstance(rel.get("artist"), dict):
            entry = rel["artist"]
            if _text(entry.get("name")):
                artists.append(CatalogArtist(external_id=entry.get("id") if isinstance(entry.get("id"), str) else None,
                                             name=entry["name"].strip(), role=rel["type"],
                                             aliases=[v for v in (_text(entry.get("sort-name")),) if v]))
    work = CatalogWork(provider="musicbrainz_work", external_id=str(item.get("id")), title=title, names=names,
                       artists=artists, url=f"https://musicbrainz.org/work/{item.get('id')}",
                       language=_text(item.get("language")), recording_ids=[r for r in recordings if r])
    if not re.fullmatch(MBID, work.external_id):
        raise ValueError("invalid work MBID")
    return work


class MusicBrainzClient:
    """Search API only (1 request/second policy; a little slower to stay under it)."""

    def __init__(self, *, transport=None, interval: float = 1.2, cache: dict | None = None,
                 sleep=time.sleep, clock=time.monotonic):
        self.http = _Http("https://musicbrainz.org", interval=interval, transport=transport, cache=cache,
                          sleep=sleep, clock=clock)

    def close(self) -> None:
        self.http.close()

    def search_recordings(self, title: str, artist: str, *, limit: int = 25) -> list[CatalogRecording]:
        query = f"recording:{_lucene_phrase(title)} AND artist:{_lucene_phrase(artist)}"
        data = self.http.get("/ws/2/recording", {"query": query, "limit": min(max(limit, 1), 100), "fmt": "json"})
        items = data.get("recordings")
        if not isinstance(items, list):
            raise CatalogFailure("malformed_response")
        result = []
        for item in items:
            try:
                result.append(recording_from_musicbrainz(item))
            except ValueError:
                continue
        return result

    def works_for_recordings(self, recording_ids: list[str], *, limit: int = 10) -> list[CatalogWork]:
        """Works linked to any of the given recordings by a performance relation."""
        ids = [r for r in dict.fromkeys(recording_ids) if re.fullmatch(MBID, r)][:20]
        if not ids:
            return []
        data = self.http.get("/ws/2/work", {"query": " OR ".join(f"rid:{r}" for r in ids),
                                            "limit": min(max(limit, 1), 25), "fmt": "json"})
        items = data.get("works")
        if not isinstance(items, list):
            raise CatalogFailure("malformed_response")
        result = []
        for item in items:
            try:
                result.append(work_from_musicbrainz(item))
            except ValueError:
                continue
        return result

