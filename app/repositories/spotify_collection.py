"""Spotify catalog writes. One claimed job, one transaction, existing edits retained."""
from __future__ import annotations

import hashlib
import json
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import bindparam, text

from app.repositories import worker_jobs
from app.schemas.worker_jobs import JobRequest


def scope(session, account_id):
    source = session.execute(text('''SELECT a.platform_id FROM external_accounts a
        WHERE a.id=:id AND a.platform='spotify' AND a.collection_enabled AND a.archived_at IS NULL'''),
        {'id': account_id}).scalar_one_or_none()
    if source is None:
        raise worker_jobs.JobConflict('Spotify account is not active and registered')
    links = session.execute(text('''SELECT a.platform_id,e.artist_id FROM external_accounts a
        JOIN artist_external_accounts e ON e.account_id=a.id
        JOIN artists artist ON artist.id=e.artist_id
        WHERE a.platform='spotify' AND a.collection_enabled AND a.archived_at IS NULL
          AND e.relationship='owner' AND artist.archived_at IS NULL''')).all()
    spotify_artists = {}
    for external, artist in links:
        spotify_artists.setdefault(external, []).append(artist)
    if source not in spotify_artists:
        raise worker_jobs.JobConflict('Registered account has no active owner relation')
    channels = session.execute(text('''SELECT y.id,y.platform_id FROM external_accounts y
        JOIN artist_external_accounts e ON e.account_id=y.id AND e.relationship='owner'
        WHERE y.platform='youtube' AND y.collection_enabled AND y.archived_at IS NULL
          AND e.artist_id IN :artists AND y.platform_id ~ '^UC[A-Za-z0-9_-]{22}$'
        GROUP BY y.id,y.platform_id ORDER BY y.id''').bindparams(bindparam('artists', expanding=True)),
        {'artists': tuple(spotify_artists[source])}).all()
    return dict(source_id=source, artists=spotify_artists, youtube_channels=[dict(id=r[0], platform_id=r[1]) for r in channels])


def snapshot(session, album_ids, track_ids):
    albums = {}
    for external in album_ids:
        album = session.execute(text('SELECT id,version,archived_at FROM albums WHERE spotify_album_id=:id'),
                                {'id': external}).mappings().one_or_none()
        albums[external] = dict(album) if album else None
    tracks = {}
    for external in track_ids:
        recording = session.execute(text('''SELECT r.id,r.version,r.archived_at,r.official_video_id
            FROM recording_external_ids x JOIN recordings r ON r.id=x.recording_id
            WHERE x.platform='spotify' AND x.external_id=:id'''), {'id': external}).mappings().one_or_none()
        tracks[external] = dict(recording) if recording else None
    return dict(albums=albums, tracks=tracks)


def _receipt(session, job, payload, value, actions):
    body = dict(provider='spotify', account_id=job.external_account_id, artist_id=payload.spotify_artist_id,
                offset=payload.album_offset, next=value['has_next'], actions=actions,
                albums=[album.model_dump(mode='json') for album in value['albums']],
                skipped_uncredited=value['skipped_uncredited'],
                youtube_matches=value['youtube_matches'])
    manifest = hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False,
                                          separators=(',', ':')).encode()).hexdigest()
    session.execute(text('''INSERT INTO catalog_imports(operation_id,catalog_instance_id,manifest_hash,source_kind,result_summary)
        VALUES (:operation,(SELECT id FROM catalog_instance),:hash,'batch_import',CAST(:summary AS jsonb))
        ON CONFLICT (operation_id) DO NOTHING'''),
        dict(operation=str(uuid5(NAMESPACE_URL, f'spotify-job:{job.id}')), hash=manifest,
             summary=json.dumps(body, ensure_ascii=False)))


def persist(session, job, payload, value):
    # Fences absent-row inserts and checks identity before anything is applied.
    session.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:id, 941204))'), {'id': payload.spotify_artist_id})
    current_scope = scope(session, job.external_account_id)
    if current_scope != value['scope']:
        raise worker_jobs.JobConflict('Registered account relationships changed during collection')
    current = snapshot(session, [album.id for album in value['albums']],
                       list({track.id for album in value['albums'] for track in album.tracks}))
    actions = []
    created_tracks = set()
    for album in value['albums']:
        before = value['snapshot']['albums'][album.id]
        existing = current['albums'][album.id]
        if before != existing or (existing and existing['archived_at']):
            actions.append(dict(album_id=album.id, status='version_conflict'))
            continue
        credits = [artist for external in album.artist_ids for artist in current_scope['artists'].get(external, [])]
        if existing:
            # An existing release may have manual title, translated text, track
            # exclusions and artist ordering. Recollecting only records evidence.
            actions.append(dict(album_id=album.id, status='review_candidate'))
            continue
        album_type = album.album_type if album.album_type in ('single','album','compilation') else 'other'
        album_id = session.execute(text('''INSERT INTO albums(spotify_album_id,title_native,album_type,
            release_year,release_month,release_day,cover_image_url)
            VALUES (:external,:title,:type,:year,:month,:day,:cover) RETURNING id'''),
            dict(external=album.id, title=album.title, type=album_type, year=album.release_year,
                 month=album.release_month, day=album.release_day, cover=album.cover_image_url)).scalar_one()
        for position, artist in enumerate(dict.fromkeys(credits)):
            session.execute(text('INSERT INTO album_artists(album_id,artist_id,position) VALUES (:album,:artist,:position)'),
                            dict(album=album_id, artist=artist, position=position))
        for track in album.tracks:
            before_track = value['snapshot']['tracks'][track.id]
            current_track = current['tracks'][track.id]
            if before_track and (before_track != current_track or before_track['archived_at']):
                actions.append(dict(album_id=album.id, track_id=track.id, status='recording_version_conflict'))
                continue
            if before_track is None and current_track is not None and track.id not in created_tracks:
                actions.append(dict(album_id=album.id, track_id=track.id, status='recording_version_conflict'))
                continue
            if current_track is None:
                recording_id = session.execute(text('''INSERT INTO recordings(title_native,duration_ms)
                    VALUES (:title,:duration) RETURNING id'''),
                    dict(title=track.title, duration=track.duration_ms)).scalar_one()
                session.execute(text("INSERT INTO recording_external_ids(recording_id,platform,external_id) VALUES (:id,'spotify',:external)"),
                                dict(id=recording_id, external=track.id))
                created_tracks.add(track.id)
                current['tracks'][track.id] = {'id': recording_id, 'version': 1, 'archived_at': None, 'official_video_id': None}
                track_credits = [artist for external in track.artist_ids for artist in current_scope['artists'].get(external, [])]
                for position, artist in enumerate(dict.fromkeys(track_credits)):
                    session.execute(text('''INSERT INTO recording_artists(recording_id,artist_id,role,position)
                        VALUES (:recording,:artist,:role,:position)'''),
                        dict(recording=recording_id, artist=artist, role='primary' if position == 0 else 'featured',
                             position=position))
                match = value['youtube_matches'].get(track.id)
                if match and match['status'] == 'matched':
                    found = session.execute(text("SELECT id,source_account_id,archived_at FROM videos WHERE platform='youtube' AND platform_video_id=:id FOR UPDATE"),
                                            {'id': match['video_id']}).mappings().one_or_none()
                    if not found:
                        found_id = session.execute(text('''INSERT INTO videos(platform,platform_video_id,source_account_id,title,availability)
                            VALUES ('youtube',:external,:account,:title,'public') RETURNING id'''),
                            dict(external=match['video_id'], account=match['account_id'], title=match['title'])).scalar_one()
                    elif found['archived_at'] or found['source_account_id'] not in (None, match['account_id']):
                        found_id = None
                    else:
                        found_id = found['id']
                    if found_id:
                        session.execute(text('UPDATE recordings SET official_video_id=:video WHERE id=:id'),
                                        dict(video=found_id, id=recording_id))
                        current['tracks'][track.id]['official_video_id'] = found_id
                    else:
                        match['status'] = 'existing_video_conflict'
                        actions.append(dict(album_id=album.id, track_id=track.id, status='existing_video_conflict'))
            else:
                recording_id = current_track['id']
            # A Spotify track can appear on more than one release, but a manually
            # occupied slot is never moved or replaced.
            slot = session.execute(text('''SELECT recording_id FROM album_tracks
                WHERE album_id=:album AND disc_number=:disc AND track_number=:number'''),
                dict(album=album_id, disc=track.disc_number, number=track.track_number)).scalar_one_or_none()
            if slot is None:
                session.execute(text('''INSERT INTO album_tracks(album_id,recording_id,disc_number,track_number)
                    VALUES (:album,:recording,:disc,:number)'''),
                    dict(album=album_id, recording=recording_id, disc=track.disc_number, number=track.track_number))
            elif slot != recording_id:
                actions.append(dict(album_id=album.id, track_id=track.id, status='slot_conflict'))
        actions.append(dict(album_id=album.id, status='created'))
    _receipt(session, job, payload, value, actions)
    if value['has_next']:
        next_offset = payload.album_offset + 10
        if next_offset > 1000:
            raise worker_jobs.JobConflict('Spotify album page limit reached')
        next_payload = payload.model_dump()
        next_payload['album_offset'] = next_offset
        worker_jobs.enqueue(session, JobRequest(job_type='spotify_collect', external_account_id=job.external_account_id,
                                                 payload=next_payload, max_attempts=job.max_attempts))
