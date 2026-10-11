"""Exact-name candidate decisions for explicit account registration tools."""
import unicodedata


def name_key(value: str) -> str:
    # Retain internal spaces and punctuation: short/generic names must not widen.
    return unicodedata.normalize('NFKC', value).strip().casefold()


def artist_names(artist: dict) -> list[str]:
    names = [artist.get(key) for key in ('name_native', 'name_latin', 'name_ko')]
    return list(dict.fromkeys(name for name in names if name and name.strip()))


def decide(artist: dict, candidates: list[dict], *, complete: bool,
           occupied_ids: set[str], rejected_ids: set[str]) -> dict:
    keys = {name_key(name) for name in artist_names(artist)}
    exact = {item['id']: item for item in candidates if name_key(item['name']) in keys}
    result = {'artist_id': artist['id'], 'artist_version': artist['version'],
              'artist_name': artist['name_native'], 'candidates': list(exact.values())}
    if not complete:
        return dict(result, status='review', reason='incomplete_search')
    if not exact:
        return dict(result, status='missing', reason='no_exact_name')
    if len(exact) != 1:
        return dict(result, status='review', reason='multiple_exact_names')
    item = next(iter(exact.values()))
    if item['id'] in rejected_ids:
        return dict(result, status='review', reason='previously_rejected_identity')
    if item['id'] in occupied_ids:
        return dict(result, status='review', reason='existing_account_ownership')
    return dict(result, status='match', spotify_id=item['id'], spotify_name=item['name'],
                reason='unique_exact_name')
