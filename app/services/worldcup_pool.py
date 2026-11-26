"""Playable songs per agency and artist for the world cup setup screen.

Counts come from the same explore query the browser later pages through, so a count shown
on the setup screen matches the candidates it can draw. Results are cached briefly per kind.
"""
from collections import Counter
import time
from threading import Lock

from sqlalchemy import text

from app.services.catalog_read import CatalogRead

TTL_SECONDS = 600
_cache: dict[str, tuple[float, dict]] = {}
_lock = Lock()


def _entries(session, song_kind):
    return CatalogRead(session).explore_songs(kind=song_kind, agency='all', q='', order='name', offset=0,
                                              limit=1_000_000, published_only=True)['items']


def summarize(entries, artists):
    """Count each entry once per credited name and once per agency of those names."""
    by_name: dict[str, list[tuple[int, str | None]]] = {}
    for artist_id, name, agency in artists:
        by_name.setdefault(name, []).append((artist_id, agency))
    artist_counts, agency_counts = Counter(), Counter()
    for entry in entries:
        names = [name for name in (entry.get('artist_name') or '').split(' · ') if name]
        matched = [match for name in names for match in by_name.get(name, [])]
        for artist_id in {artist_id for artist_id, _ in matched}:
            artist_counts[artist_id] += 1
        for agency in {agency for _, agency in matched if agency}:
            agency_counts[agency] += 1
    return dict(
        total=len(entries),
        agencies=[dict(name=name, count=count) for name, count in agency_counts.most_common()],
        artists=[dict(id=artist_id, count=count) for artist_id, count in sorted(artist_counts.items())],
    )


def pool_summary(session, song_kind, now=None):
    now = time.monotonic() if now is None else now
    with _lock:
        cached = _cache.get(song_kind)
        if cached and now - cached[0] < TTL_SECONDS:
            return cached[1]
    artists = session.execute(text('''SELECT a.id,a.name_native,g.name_native FROM artists a
        LEFT JOIN agencies g ON g.id=a.agency_id AND g.archived_at IS NULL
        WHERE a.archived_at IS NULL''')).all()
    value = dict(song_kind=song_kind, **summarize(_entries(session, song_kind), artists))
    with _lock:
        _cache[song_kind] = (now, value)
    return value
