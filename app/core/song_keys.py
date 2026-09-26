"""Conservative normalization of setlist song text into comparable match keys.

The key only groups identical spellings (width, case, spacing, wrapping quotes).
It never decides that two different spellings are the same song.
"""
from __future__ import annotations

import re
import unicodedata

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
