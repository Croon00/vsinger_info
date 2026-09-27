"""Conservative normalization of setlist song text into comparable match keys.

The key only groups identical spellings (width, case, spacing, wrapping quotes).
It never decides that two different spellings are the same song.
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping

# song_match_keys.key_version produced by song_key(); bump only with a re-keying plan.
KEY_VERSION = 1

_SPACE = re.compile(r"\s+")
_WRAPPERS = ("「」", "『』", '""', "“”", "''", "‘’", "【】", "〈〉", "《》")


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    text = _SPACE.sub(" ", unicodedata.normalize("NFKC", value).casefold()).strip()
    changed = True
    while changed and len(text) >= 2:
        changed = False
        for opening, closing in _WRAPPERS:
            inner = text[1:-1]
            # Strip only one wrapping pair, never 「A」と「B」-style inner quoting.
            if text[0] == opening and text[-1] == closing and opening not in inner and closing not in inner:
                text, changed = inner.strip(), True
                break
    return text


def song_key(title: str | None, artist: str | None) -> tuple[str, str]:
    """(normalized title, normalized original artist); artist is '' when unknown."""
    return normalize_text(title), normalize_text(artist)


# Rule-parsed setlist lines keep "title / artist" or "title - artist" in raw_title.
_COMBINED_SEPARATOR = re.compile(r"\s*[/／]\s*|\s+[-－–—]\s+")


def lookup_keys(title: str | None, artist: str | None) -> list[tuple[str, str]]:
    """Exact key first, then every (title, artist) split of a combined line when no artist is given.

    Splits are only lookup candidates against confirmed keys; they are never stored.
    """
    exact = song_key(title, artist)
    keys = [exact]
    if exact[1] or not title:
        return keys
    for match in _COMBINED_SEPARATOR.finditer(title):
        key = song_key(title[:match.start()], title[match.end():])
        if key[0] and key[1] and key not in keys:
            keys.append(key)
    return keys


def resolve_key(candidates: list[tuple[str, str]], confirmed: Mapping[tuple[str, str], int]) -> tuple[str, str] | None:
    """The exact key if confirmed; else the split key when all confirmed splits name one song."""
    if not candidates:
        return None
    if candidates[0] in confirmed:
        return candidates[0]
    matched = [key for key in candidates[1:] if key in confirmed]
    return matched[0] if len({confirmed[key] for key in matched}) == 1 else None


def ascii_latin(value: str | None) -> str | None:
    """Latin-field form: diacritics stripped (Tōkyō -> Tokyo), printable ASCII only.

    Returns None when anything outside printable ASCII remains (kana, kanji, symbols),
    matching the revision 003 CHECK on ``title_latin`` / ``name_latin``.
    """
    if not value:
        return None
    decomposed = unicodedata.normalize("NFKD", unicodedata.normalize("NFKC", value))
    text = _SPACE.sub(" ", "".join(c for c in decomposed if not unicodedata.combining(c))).strip()
    if not text or any(not " " <= c <= "~" for c in text):
        return None
    return text
