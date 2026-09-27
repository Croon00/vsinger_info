"""Korean song names from Namu Wiki (나무위키), for the title_ko review (plan step 6).

``fetch`` reads the round's inputs (scripts/title_ko_candidates.py prepare) and, one
request every few seconds, opens ``/w/<native title>`` -- then ``/w/<title>(<artist>)``
variants when that page does not exist. robots.txt allows /w/. Each page is cached as
HTML and plain text in git-ignored db-migration/reports/title-ko/round-N/namu/, and
namu-index.json records per song the page reached, its document title, whether one of
the song's artists appears on the page, and the Korean name when the document title
itself is Korean (a redirect like ヒバナ -> 불꽃(VOCALOID 오리지널 곡); the trailing
disambiguation is dropped). Pages whose title is not Korean are left for a reader to
check the content (namu-content-*.json). Nothing touches the catalog.

Namu Wiki text is CC BY-NC-SA 2.0 KR; only the name and the page URL are kept, and the
URL goes into the review file and catalog_changes as the source.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
import unicodedata
from pathlib import Path
from urllib.parse import quote, unquote

import httpx

ROOT = Path(__file__).resolve().parents[1]
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE = "https://namu.wiki/w/"
USER_AGENT = "schedule_music-title-lookup/0.1 (song catalog research; about 1 request per 3 seconds)"
HANGUL = re.compile(r"[\uac00-\ud7a3]")
TRAILING_PAREN = re.compile(r"\s*\([^()]*\)\s*$")
TITLE_TAG = re.compile(r"<title>(.*?)</title>", re.S)
TEXT_LIMIT = 60000


def page_title(markup: str) -> str | None:
    match = TITLE_TAG.search(markup)
    if not match:
        return None
    title = html.unescape(match.group(1)).strip()
    return title[: -len(" - 나무위키")] if title.endswith(" - 나무위키") else title


def korean_name(document_title: str | None) -> str | None:
    """'불꽃(VOCALOID 오리지널 곡)' -> '불꽃'; None unless the remaining name has Hangul."""
    if not document_title:
        return None
    name = TRAILING_PAREN.sub("", document_title).strip()
    return name if HANGUL.search(name) else None


def plain_text(markup: str) -> str:
    markup = re.sub(r"<(script|style|noscript)\b.*?</\1>", " ", markup, flags=re.S | re.I)
    text = html.unescape(re.sub(r"<[^>]+>", " ", markup))
    return re.sub(r"\s+", " ", text).strip()


def fold(value: str) -> str:
    return "".join(unicodedata.normalize("NFKC", value).casefold().split())


def artist_on_page(text: str, artists: list[dict]) -> bool:
    page = fold(text)
    names = [n for a in artists for n in (a.get("name"), a.get("name_ko")) if n]
    return any(fold(n) in page for n in names if len(fold(n)) >= 2)


def candidates(song: dict) -> list[str]:
    title = song["title_native"]
    paths = [title]
    for artist in song["artists"]:
        for name in (artist.get("name"), artist.get("name_ko")):
            if name:
                paths.append(f"{title}({name})")
    return list(dict.fromkeys(paths))


class Namu:
    def __init__(self, cache_dir: Path, *, transport=None, interval: float = 3.0):
        self.cache_dir, self.interval, self.requests, self._last = cache_dir, interval, 0, 0.0
        self.http = httpx.Client(headers={"User-Agent": USER_AGENT, "Accept-Language": "ko"}, timeout=30,
                                 follow_redirects=True, transport=transport)

    def get(self, path: str) -> dict:
        """{status, url, title, text} for /w/<path>, cached on disk."""
        key = re.sub(r'[\\/:*?"<>|]', "_", path)[:120]
        cached = self.cache_dir / f"{key}.json"
        if cached.exists():
            return json.loads(cached.read_text(encoding="utf-8"))
        for attempt in range(4):
            wait = self._last + self.interval - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            self.requests += 1
            try:
                response = self.http.get(BASE + quote(path))
            except httpx.TransportError:
                if attempt == 3:
                    raise
                time.sleep(10 * (attempt + 1))
                continue
            if response.status_code in (429, 500, 502, 503, 504) and attempt < 3:
                time.sleep(min(float(response.headers.get("Retry-After") or 20 * (attempt + 1)), 120))
                continue
            break
        page = {"status": response.status_code, "url": unquote(str(response.url)),
                "title": page_title(response.text), "text": plain_text(response.text)[:TEXT_LIMIT]}
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        cached.write_text(json.dumps(page, ensure_ascii=False), encoding="utf-8")
        return page

    def close(self) -> None:
        self.http.close()


def lookup(song: dict, namu: Namu) -> dict:
    tried = []
    for path in candidates(song):
        page = namu.get(path)
        tried.append({"path": path, "status": page["status"]})
        if page["status"] != 200:
            continue
        found = artist_on_page(page["text"], song["artists"])
        name = korean_name(page["title"])
        return {"song_id": song["song_id"], "title_native": song["title_native"], "tried": tried, "url": page["url"],
                "document_title": page["title"], "artist_on_page": found,
                "title_ko": name if found else None, "where": "title" if name and found else None,
                "needs_content_check": not (name and found), "text_file": None}
    return {"song_id": song["song_id"], "title_native": song["title_native"], "tried": tried, "url": None,
            "document_title": None, "artist_on_page": False, "title_ko": None, "where": None,
            "needs_content_check": True, "text_file": None}


def excerpt(page: dict, song: dict, *, head: int = 3500, around: int = 250, limit: int = 8) -> str:
    """What a reader needs to judge a page: its title, the opening (infobox, 개요) and the
    passages around the native title -- a redirect may land on an anime or album page."""
    text = page["text"]
    start = text.find("최근 수정 시각")
    body = text[start:] if start >= 0 else text
    parts = [f"URL: {page['url']}", f"DOCUMENT TITLE: {page['title']}", "", "OPENING:", body[:head]]
    hits, pos = [], 0
    needle = song["title_native"]
    while len(hits) < limit:
        at = body.find(needle, pos)
        if at < 0:
            break
        if at >= head:
            hits.append(body[max(0, at - around):at + len(needle) + around])
        pos = at + len(needle)
    if hits:
        parts += ["", "PASSAGES WITH THE NATIVE TITLE:"] + [f"... {h} ..." for h in hits]
    return "\n".join(parts)


def fetch_artists(work: Path, *, interval: float) -> dict:
    """For songs without their own page, fetch the artists' pages (discographies list Korean names)."""
    songs = {s["song_id"]: s for p in sorted(work.glob("input-*.json")) for s in json.loads(p.read_text(encoding="utf-8"))}
    index = json.loads((work / "namu-index.json").read_text(encoding="utf-8"))
    namu = Namu(work / "namu", interval=interval)
    found = 0
    try:
        for r in index:
            if r["url"]:
                continue
            r["artist_pages"] = []
            for artist in songs[r["song_id"]]["artists"]:
                for name in dict.fromkeys(n for n in (artist.get("name_ko"), artist.get("name")) if n):
                    page = namu.get(name)
                    if page["status"] == 200:
                        r["artist_pages"].append(name)
                        found += r["title_native"] in page["text"]
                        break
    finally:
        namu.close()
    (work / "namu-index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return {"requests": namu.requests, "songs_without_page": sum(1 for r in index if not r["url"]),
            "title_found_on_artist_page": found}


def extract(work: Path) -> dict:
    """Write one reading file per song that reached a page (from the cache, no requests)."""
    songs = {s["song_id"]: s for p in sorted(work.glob("input-*.json")) for s in json.loads(p.read_text(encoding="utf-8"))}
    index = json.loads((work / "namu-index.json").read_text(encoding="utf-8"))
    namu = Namu(work / "namu", interval=0)
    out_dir = work / "namu-read"
    out_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    try:
        for r in index:
            song = songs[r["song_id"]]
            ok = [t for t in r["tried"] if t["status"] == 200]
            if ok:
                reading = excerpt(namu.get(ok[-1]["path"]), song)
            else:
                pages = [namu.get(name) for name in r.get("artist_pages", [])]
                pages = [p for p in pages if song["title_native"] in p["text"]]
                if not pages:
                    continue
                reading = "\n\n".join("NO SONG PAGE; ARTIST PAGE:\n" + excerpt(p, song, head=0) for p in pages)
            (out_dir / f"{r['song_id']}.txt").write_text(reading, encoding="utf-8")
            written += 1
    finally:
        namu.close()
    return {"reading_files": written, "nothing_to_read": len(index) - written}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["fetch", "artists", "extract"])
    parser.add_argument("--round", type=int, default=1)
    parser.add_argument("--interval", type=float, default=3.0)
    args = parser.parse_args()
    work = ROOT / "db-migration" / "reports" / "title-ko" / f"round-{args.round}"
    if args.command == "artists":
        print(json.dumps(fetch_artists(work, interval=args.interval), ensure_ascii=False, indent=2))
        return 0
    if args.command == "extract":
        print(json.dumps(extract(work), ensure_ascii=False, indent=2))
        return 0
    songs = [s for p in sorted(work.glob("input-*.json")) for s in json.loads(p.read_text(encoding="utf-8"))]
    namu = Namu(work / "namu", interval=args.interval)
    log = (work / "namu-fetch.log").open("a", encoding="utf-8")
    results = []
    try:
        for n, song in enumerate(songs, 1):
            result = lookup(song, namu)
            if result["url"] and result["needs_content_check"]:
                text_file = work / "namu-text" / f"{song['song_id']}.txt"
                text_file.parent.mkdir(parents=True, exist_ok=True)
                page = namu.get(result["tried"][-1]["path"])
                text_file.write_text(f"URL: {page['url']}\nTITLE: {page['title']}\n\n{page['text']}", encoding="utf-8")
                result["text_file"] = str(text_file)
            results.append(result)
            log.write(f"{n}/{len(songs)} {song['song_id']} {result['where'] or '-'} {result['document_title']}\n")
            log.flush()
    finally:
        namu.close()
        log.close()
    (work / "namu-index.json").write_text(json.dumps(results, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    summary = {"songs": len(results), "requests": namu.requests,
               "from_title": sum(1 for r in results if r["where"] == "title"),
               "page_needs_content_check": sum(1 for r in results if r["url"] and r["needs_content_check"]),
               "no_page": sum(1 for r in results if not r["url"])}
    (work / "namu-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
