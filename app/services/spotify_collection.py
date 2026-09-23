"""Registered Spotify account collection; no discovery or translation."""
from __future__ import annotations

import re

from app.core.config import settings
from app.integrations.spotify_catalog import SpotifyCatalogClient, SpotifyFailure
from app.integrations.youtube_catalog import YouTubeClient, YouTubeFailure, purpose
from app.repositories import spotify_collection as repository


def client():
    return SpotifyCatalogClient(settings.spotify_client_id or '', settings.spotify_client_secret or '')


def _translate(exc):
    from app.services.music_jobs import RetryableJobError, PermanentJobError
    if exc.retry:
        raise RetryableJobError(retry_after=exc.retry_after) from None
    raise PermanentJobError(str(exc)) from None


def _normal(value):
    return ''.join(character.casefold() for character in value if character.isalnum())


async def _youtube_matches(albums, scope, existing):
    """Only an explicitly requested match on one already registered channel."""
    result = {}
    channels = scope['youtube_channels']
    if len(channels) != 1:
        return {track.id: {'status': 'no_unique_registered_youtube_channel'}
                for album in albums for track in album.tracks
                if existing['tracks'].get(track.id) is None}
    if not settings.youtube_api_key:
        from app.services.music_jobs import PermanentJobError
        raise PermanentJobError('YOUTUBE_API_KEY is required for explicit matching')
    channel = channels[0]
    provider = YouTubeClient(settings.youtube_api_key)
    scanned = 0
    for album in albums:
        for track in album.tracks:
            if track.id in result or existing['tracks'].get(track.id) is not None:
                continue
            if scanned >= 20:
                result[track.id] = {'status': 'deferred_match_limit'}
                continue
            scanned += 1
            try:
                data = await provider.get('search', part='snippet', type='video', channelId=channel['platform_id'],
                                          q=track.title + ' official', maxResults=5)
                candidates = []
                for item in data['items']:
                    snippet = item.get('snippet') or {}
                    external = (item.get('id') or {}).get('videoId')
                    title = snippet.get('title') or ''
                    if (snippet.get('channelId') == channel['platform_id'] and
                            isinstance(external, str) and re.fullmatch(r'[A-Za-z0-9_-]{11}', external) and
                            _normal(track.title) in _normal(title) and
                            any(word in title.casefold() for word in ('official', 'music video', ' mv', '公式'))):
                        candidates.append(external)
                if len(set(candidates)) != 1:
                    result[track.id] = {'status': 'ambiguous_or_missing', 'candidate_ids': list(dict.fromkeys(candidates))}
                    continue
                details = await provider.videos(candidates[:1])
                if (len(details) != 1 or details[0].channel_id != channel['platform_id']
                        or details[0].availability not in ('public', 'unlisted') or purpose(details[0]) is not None):
                    result[track.id] = {'status': 'unverified'}
                    continue
                result[track.id] = dict(status='matched', video_id=details[0].id, account_id=channel['id'], title=details[0].title)
            except YouTubeFailure as exc:
                _translate(exc)
    return result


async def collect(job, payload):
    from app.services.music_jobs import db_call, PermanentJobError
    scope = await db_call(repository.scope, job.external_account_id)
    if scope['source_id'] != payload.spotify_artist_id:
        raise PermanentJobError('Registered Spotify ID changed')
    provider = client()
    try:
        summaries, has_next = await provider.albums_page(payload.spotify_artist_id, offset=payload.album_offset)
        if has_next and payload.album_offset >= 1000:
            raise PermanentJobError('Spotify album page limit reached')
        unique = dict.fromkeys(summary.get('id') for summary in summaries)
        if None in unique or any(not isinstance(external, str) or not re.fullmatch(r'[A-Za-z0-9]{22}', external) for external in unique):
            raise PermanentJobError('Spotify album IDs are malformed')
        albums = []
        skipped = []
        for external in unique:
            album = await provider.album(external)
            if album.id != external:
                raise PermanentJobError('Spotify album ID does not match the request')
            if (payload.spotify_artist_id not in album.artist_ids
                    and not any(payload.spotify_artist_id in track.artist_ids for track in album.tracks)):
                skipped.append(external)
                continue
            albums.append(album)
        snapshot = await db_call(repository.snapshot, [album.id for album in albums],
                                 list({track.id for album in albums for track in album.tracks}))
        matches = await _youtube_matches(albums, scope, snapshot) if payload.link_youtube else {}
    except SpotifyFailure as exc:
        _translate(exc)
    return dict(scope=scope, albums=albums, skipped_uncredited=skipped,
                has_next=has_next, snapshot=snapshot, youtube_matches=matches)


def handlers():
    from app.services.music_jobs import Handler
    return {'spotify_collect': Handler(collect, repository.persist, timeout_seconds=900)}
