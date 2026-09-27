"""Propose external works for setlist match keys and existing songs (plan step 5).

Pure decision rules plus a lookup chain over injected clients. Nothing here writes to
the database; the output is a candidate report that a person reviews before any apply.

A candidate is *strong* when one of its names equals the target title AND one of its
credited artists (VocaDB producer/circle/band, MusicBrainz recording performer or
work composer/lyricist) equals one of the target's artist spellings, both compared in
``loose`` form. A target is ``auto`` only when exactly one strong candidate exists.
Title-only matches are kept for review and never decide anything.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.core.song_keys import ascii_latin, normalize_text
from app.integrations.song_catalogs import CatalogFailure, CatalogRecording, CatalogWork

CREDIT_ROLES = {"producer", "circle", "band", "performer", "composer", "lyricist", "writer"}
_TILDES = re.compile(r"[~〜～∼⁓]")
_DASHES = re.compile(r"[‐‑‒–—―−]")
_SPACE = re.compile(r"\s+")


def loose(value: str | None) -> str:
    """Comparison form for external catalog text only (never stored, never a key):
    normalize_text plus tilde/dash variants folded and whitespace removed, so
    ``HELLO ～Paradise Kiss～`` meets ``HELLO〜PARADISE KISS〜`` and ``松田 聖子`` meets ``松田聖子``."""
    return _SPACE.sub("", _DASHES.sub("-", _TILDES.sub("~", normalize_text(value))))


def _loose_set(values) -> set[str]:
    return {v for v in map(loose, values) if v}


@dataclass
class Target:
    kind: str  # "key" (song_match_keys row) or "song" (existing songs row)
    ref: int
    title: str
    artist: str | None
    title_key: str
    artist_spellings: set[str]
    count: int = 0
    our_artist_ids: list[int] = field(default_factory=list)


@dataclass
class ArtistIndex:
    """Normalized spelling -> our artist ids, and artist id -> all its spellings."""
    by_spelling: dict[str, set[int]]
    spellings: dict[int, set[str]]

    def expand(self, raw: str | None) -> tuple[set[str], list[int]]:
        key = normalize_text(raw)
        if not key:
            return set(), []
        ids = sorted(self.by_spelling.get(key, set()))
        found = {key}
        for artist_id in ids:
            found |= self.spellings.get(artist_id, set())
        return found, ids


def _names(work: CatalogWork) -> set[str]:
    return _loose_set([work.title] + [n.value for n in work.names])


def _artist_spellings(artists) -> set[str]:
    found = []
    for artist in artists:
        if artist.role in CREDIT_ROLES:
            found += [artist.name, *artist.aliases]
    return _loose_set(found)


def recording_matches(recording: CatalogRecording, target: Target) -> bool:
    if loose(recording.title) != loose(target.title_key):
        return False
    spellings = _loose_set(target.artist_spellings)
    return loose(recording.credit) in spellings or bool(_artist_spellings(recording.artists) & spellings)


def latin_title(work: CatalogWork) -> str | None:
    """ASCII latin title proposal: the title itself when already Latin, else a romanization.
    English names are translations, not transliterations, so they are not used."""
    options = [work.title] + [n.value for lang in ("Romaji", "ja-Latn") for n in work.names if n.language == lang]
    return next((v for v in map(ascii_latin, options) if v), None)


def korean_title(work: CatalogWork) -> str | None:
    return next((n.value for n in work.names if n.language == "ko"), None)


def describe(work: CatalogWork, target: Target, *, performers: list | None = None) -> dict:
    spellings = _loose_set(target.artist_spellings)
    credit = _artist_spellings(work.artists) | _artist_spellings(performers or [])
    vocalists = _loose_set(a.name for a in work.artists if a.role == "vocalist")
    matched = [a.name for a in list(work.artists) + list(performers or [])
               if a.role in CREDIT_ROLES and _artist_spellings([a]) & spellings]
    return {
        "provider": work.provider, "external_id": work.external_id, "url": work.url, "title": work.title,
        "language": work.language,
        "names": [{"value": n.value, "language": n.language} for n in work.names],
        "artists": [a.model_dump() for a in work.artists],
        "performers": [a.model_dump() for a in performers or []],
        "matched_artists": list(dict.fromkeys(matched)),
        "title_latin": latin_title(work), "title_ko": korean_title(work),
        "title_exact": loose(target.title_key) in _names(work),
        "artist_exact": bool(credit & spellings),
        "vocalist_only": not (credit & spellings) and bool(vocalists & spellings),
    }


def classify(candidates: list[dict]) -> str:
    strong = {(c["provider"], c["external_id"]) for c in candidates if c["title_exact"] and c["artist_exact"]}
    if len(strong) == 1:
        return "auto"
    if strong or any(c["title_exact"] for c in candidates):
        return "review"
    return "none"


def lookup(target: Target, *, vocadb=None, utaitedb=None, musicbrainz=None) -> dict:
    """Walk VocaDB -> UtaiteDB -> MusicBrainz, stopping at the first strong match."""
    result = {"candidates": [], "providers": [], "errors": []}
    if not target.artist_spellings:
        result["status"] = "no_artist"
        return result
    queries = [target.title] + ([normalize_text(target.title)] if normalize_text(target.title) != target.title else [])

    def strong() -> bool:
        return any(c["title_exact"] and c["artist_exact"] for c in result["candidates"])

    for name, client in (("vocadb", vocadb), ("utaitedb", utaitedb)):
        if client is None or strong():
            continue
        result["providers"].append(name)
        try:
            seen = set()
            for query in queries:
                works = [w for w in client.search_originals(query) if w.external_id not in seen]
                seen |= {w.external_id for w in works}
                result["candidates"] += [describe(w, target) for w in works]
                if works:
                    break
        except CatalogFailure as exc:
            result["errors"].append({"provider": name, "code": exc.code})
    if musicbrainz is not None and not strong():
        result["providers"].append("musicbrainz")
        try:
            artist = target.artist or ""
            recordings = [r for r in musicbrainz.search_recordings(target.title, artist)
                          if recording_matches(r, target)]
            by_id = {r.external_id: r for r in recordings}
            if recordings:
                for work in musicbrainz.works_for_recordings(list(by_id)):
                    linked = [by_id[r] for r in work.recording_ids if r in by_id]
                    if not linked:
                        continue
                    performers = {a.name: a for r in linked for a in r.artists}.values()
                    entry = describe(work, target, performers=list(performers))
                    entry["recording_ids"] = [r.external_id for r in linked][:10]
                    result["candidates"].append(entry)
        except CatalogFailure as exc:
            result["errors"].append({"provider": "musicbrainz", "code": exc.code})
    result["status"] = "error" if result["errors"] and not result["candidates"] else classify(result["candidates"])
    return result


def existing_matches(candidate: dict, songs: list[dict], external: dict[tuple[str, str], int],
                     *, target_spellings: set[str] | None = None,
                     split_works: frozenset[tuple[str, str]] | set[tuple[str, str]] = frozenset()) -> list[int]:
    """Existing song ids a candidate already corresponds to.

    A stored external ID is the song: one work is one song whoever the setlist credits
    (writer vs singer, a well-known cover). Works listed in ``split_works`` are the
    user-approved exceptions kept apart per artist (e.g. 僕が死のうと思ったのは by
    中島美嘉 and by amazarashi): there the stored ID wins only when that song shares an
    artist with the target, else only songs matching title and target artist count.
    Without a stored ID: same title plus overlapping credit.
    """
    names = _loose_set([candidate["title"]] + [n["value"] for n in candidate["names"]])
    credit = []
    for artist in candidate["artists"] + candidate["performers"]:
        if artist["role"] in CREDIT_ROLES:
            credit += [artist["name"], *artist["aliases"]]
    credit = _loose_set(credit)
    wanted = _loose_set(target_spellings) if target_spellings is not None else credit
    by_title = [s for s in songs if loose(s["title_key"]) in names and _loose_set(s["artist_spellings"]) & credit]
    stored = external.get((candidate["provider"], candidate["external_id"]))
    if stored is None:
        return sorted(s["id"] for s in by_title)
    owner = next((s for s in songs if s["id"] == stored), None)
    work = (candidate["provider"], candidate["external_id"])
    if owner is None or work not in split_works or _loose_set(owner["artist_spellings"]) & wanted:
        return [stored]
    return sorted(s["id"] for s in by_title if s["id"] != stored and _loose_set(s["artist_spellings"]) & wanted)
