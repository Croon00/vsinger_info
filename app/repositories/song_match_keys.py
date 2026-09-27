"""Confirmed song_match_keys lookup for linking newly collected performances.

Read-only: it never creates songs, keys or decisions. Only a key already confirmed
by review or rule yields a song_id (``song_keys.lookup_keys``/``resolve_key``: exact
normalized title + original artist, or an unambiguous split of a combined
"title / artist" line). Keys of archived or merged-away songs are ignored, like the
backfill link script.
"""
from __future__ import annotations

import json
from collections.abc import Sequence

from sqlalchemy import text

from app.core.song_keys import KEY_VERSION, lookup_keys, resolve_key


def confirmed_song_ids(session, keys) -> dict[tuple[str, str], int]:
    """Map each confirmed key among ``keys`` to its song_id."""
    keys = sorted({key for key in keys if key[0]})
    if not keys:
        return {}
    # Revision 004 adds these tables; before it is applied, collection behaves as before.
    if not session.execute(text("SELECT to_regclass('public.song_match_keys') IS NOT NULL")).scalar_one():
        return {}
    rows = session.execute(text('''SELECT k.title_key,k.artist_key,k.song_id
        FROM jsonb_to_recordset(CAST(:keys AS jsonb)) x(title_key text,artist_key text)
        JOIN song_match_keys k ON k.key_version=:version AND k.title_key=x.title_key AND k.artist_key=x.artist_key
        JOIN songs s ON s.id=k.song_id AND s.archived_at IS NULL
        WHERE k.status='confirmed'
          AND NOT EXISTS (SELECT 1 FROM song_merges m WHERE m.source_song_id=k.song_id)'''),
        {'keys': json.dumps([{'title_key': t, 'artist_key': a} for t, a in keys], ensure_ascii=False),
         'version': KEY_VERSION}).mappings()
    return {(row['title_key'], row['artist_key']): row['song_id'] for row in rows}


def link_song_ids(session, entries: Sequence[tuple[str | None, str | None]]) -> list[int | None]:
    """song_id (or None) for each (raw title, raw original artist) entry, in order."""
    candidates = [lookup_keys(title, artist) for title, artist in entries]
    confirmed = confirmed_song_ids(session, [key for keys in candidates for key in keys])
    resolved = [resolve_key(keys, confirmed) for keys in candidates]
    return [confirmed[key] if key else None for key in resolved]
