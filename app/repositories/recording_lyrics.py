"""Write reviewed lyrics with their source document; existing lyrics are never replaced."""
import hashlib
import json

from sqlalchemy import bindparam, text


def original_entries(session, catalog):
    """Every original-song entry as the explore API lists it, with all grouped recording IDs."""
    entries, offset = [], 0
    while True:
        page = catalog.explore_songs(kind='original', agency='all', q='', order='name', offset=offset, limit=100)
        entries += page['items']
        offset += len(page['items'])
        if not page['items'] or offset >= page['total']:
            break
    videos = [e['youtube_video_id'] for e in entries if e.get('youtube_video_id')]
    grouped = {}
    if videos:
        rows = session.execute(text('''SELECT v.platform_video_id,r.id FROM recordings r JOIN videos v ON v.id=r.official_video_id
            WHERE r.archived_at IS NULL AND v.platform='youtube' AND v.platform_video_id IN :videos ORDER BY r.id''')
            .bindparams(bindparam('videos', expanding=True)), {'videos': videos}).all()
        for video, recording in rows:
            grouped.setdefault(video, []).append(recording)
    for entry in entries:
        own = int(entry['key'].split(':')[1])
        entry['recording_ids'] = sorted(set(grouped.get(entry.get('youtube_video_id'), []) + [own]))
    return entries


def existing_lyrics(session, recording_ids):
    if not recording_ids:
        return set()
    return set(session.execute(text('''SELECT recording_id FROM recording_lyrics
        WHERE archived_at IS NULL AND recording_id IN :ids''').bindparams(bindparam('ids', expanding=True)),
        {'ids': list(recording_ids)}).scalars())


def active_recordings(session, recording_ids):
    return set(session.execute(text('SELECT id FROM recordings WHERE archived_at IS NULL AND id IN :ids')
                               .bindparams(bindparam('ids', expanding=True)), {'ids': list(recording_ids)}).scalars())


def source_document(session, entry):
    content = entry.source_text or entry.original_lyrics
    canonical = json.dumps(dict(kind=entry.source_kind, url=entry.source_url, external_id=entry.source_external_id,
                                content=content), ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    existing = session.execute(text('SELECT id FROM source_documents WHERE content_hash=:hash ORDER BY id LIMIT 1'),
                               {'hash': digest}).scalar_one_or_none()
    if existing:
        return existing
    metadata = dict(purpose='recording_lyrics', entry_key=entry.key, extraction_method=entry.extraction_method,
                    author_is_channel_owner=entry.source_author_is_channel_owner)
    return session.execute(text('''INSERT INTO source_documents(source_kind,source_url,external_id,captured_at,
        content_text,content_hash,source_metadata)
        VALUES (:kind,:url,:external,:captured,:content,:hash,CAST(:metadata AS jsonb)) RETURNING id'''),
        dict(kind=entry.source_kind, url=entry.source_url, external=entry.source_external_id, captured=entry.captured_at,
             content=content, hash=digest, metadata=json.dumps(metadata, ensure_ascii=False))).scalar_one()


def insert(session, recording_id, entry, document_id):
    session.execute(text('''INSERT INTO recording_lyrics(recording_id,original_lyrics,translation_ko,pronunciation_ko,source_document_id)
        VALUES (:recording,:original,NULLIF(:translation,''),NULLIF(:pronunciation,''),:document)'''),
        dict(recording=recording_id, original=entry.original_lyrics.strip(), translation=entry.translation_ko.strip(),
             pronunciation=entry.pronunciation_ko.strip(), document=document_id))


def released_cover_entries(session):
    """Recordings of visible artists that the original-song list leaves out as released covers."""
    from app.repositories.released_cover_rules import RELEASED_COVER_PARAMS, RELEASED_COVER_SQL
    return [dict(r) for r in session.execute(text(f'''SELECT r.id recording_id,r.title_native title,
        concat_ws(' ', r.title_native, r.version_label) ~* :released_cover_marker title_marked,
        (SELECT string_agg(a.name_native,' · ' ORDER BY x.position,x.id) FROM recording_artists x
           JOIN artists a ON a.id=x.artist_id WHERE x.recording_id=r.id) singers,
        (SELECT string_agg(a.name_native,' · ' ORDER BY sa.position,sa.id) FROM song_artists sa
           JOIN artists a ON a.id=sa.artist_id WHERE sa.song_id=r.song_id) song_artists
        FROM recordings r WHERE r.archived_at IS NULL AND {RELEASED_COVER_SQL}
          AND EXISTS (SELECT 1 FROM recording_artists x JOIN artists a ON a.id=x.artist_id
                      WHERE x.recording_id=r.id AND a.archived_at IS NULL AND a.show_in_catalog)
        ORDER BY 4,2,1'''), RELEASED_COVER_PARAMS).mappings()]
