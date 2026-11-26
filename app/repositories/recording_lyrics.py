"""Write reviewed lyrics with their source document; existing lyrics are never replaced."""
import hashlib
import json
from uuid import uuid4

from sqlalchemy import bindparam, text

from app.repositories.original_song_groups import ORIGINAL_GROUPS_CTE
from app.repositories.song_explore import (
    ORIGINAL_ARTIST_SQL, ORIGINAL_RECORDING_PARAMS, ORIGINAL_RECORDING_SQL, ORIGINAL_VIDEO_JOIN_SQL,
)


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


def lock_original(session, recording_id):
    return session.execute(text(f"""WITH {ORIGINAL_GROUPS_CTE}
        SELECT r.title_native FROM recordings r {ORIGINAL_VIDEO_JOIN_SQL}
        WHERE r.id=:recording AND {ORIGINAL_RECORDING_SQL}
          AND EXISTS (
            SELECT 1 FROM recording_artists ra
            JOIN artists credited ON credited.id=ra.artist_id AND credited.archived_at IS NULL
            LEFT JOIN original_groups og ON og.member_id=ra.artist_id
            JOIN artists a ON a.id=COALESCE(og.group_id,ra.artist_id)
            WHERE ra.recording_id=r.id AND {ORIGINAL_ARTIST_SQL}
          ) FOR UPDATE OF r"""), ORIGINAL_RECORDING_PARAMS | {'recording': recording_id}).scalar_one_or_none()


def current_for_edit(session, recording_id):
    return session.execute(text("""SELECT to_jsonb(l) snapshot,d.source_url
        FROM recording_lyrics l LEFT JOIN source_documents d ON d.id=l.source_document_id
        WHERE l.recording_id=:recording FOR UPDATE OF l"""), {'recording': recording_id}).mappings().one_or_none()


def save_edit(session, recording_id, draft, document_id, previous):
    params = draft.model_dump() | {'recording': recording_id, 'document': document_id}
    if previous is None:
        after = session.execute(text("""INSERT INTO recording_lyrics AS l
            (recording_id,original_lyrics,translation_ko,pronunciation_ko,source_document_id)
            VALUES (:recording,:original_lyrics,NULLIF(:translation_ko,''),NULLIF(:pronunciation_ko,''),:document)
            ON CONFLICT (recording_id) DO NOTHING RETURNING to_jsonb(l)"""), params).scalar_one_or_none()
        if after is None:
            return False
    else:
        after = session.execute(text("""UPDATE recording_lyrics l SET original_lyrics=:original_lyrics,
            translation_ko=NULLIF(:translation_ko,''),pronunciation_ko=NULLIF(:pronunciation_ko,''),
            source_document_id=:document
            WHERE recording_id=:recording RETURNING to_jsonb(l)"""), params).scalar_one()
    summary = json.dumps({'recording_id': recording_id, 'source_document_id': document_id})
    canonical = json.dumps({'recording_id': recording_id, **draft.model_dump()}, sort_keys=True)
    receipt = session.execute(text("""INSERT INTO catalog_imports
        (operation_id,catalog_instance_id,manifest_hash,source_kind,result_mapping,result_summary)
        SELECT :operation,id,:digest,'manual',CAST(:mapping AS jsonb),CAST(:summary AS jsonb)
        FROM catalog_instance RETURNING id"""), {
        'operation': uuid4(), 'digest': hashlib.sha256(canonical.encode()).hexdigest(), 'summary': summary,
        'mapping': json.dumps([{'entity_type': 'recording_lyrics', 'id': after['id'], 'version': after['version']}]),
    }).scalar_one()
    session.execute(text("""INSERT INTO catalog_changes
        (import_id,entity_type,entity_id,action,before_data,after_data,provenance)
        VALUES (:receipt,'recording_lyrics',:id,:action,CAST(:before AS jsonb),CAST(:after AS jsonb),
                CAST(:summary AS jsonb))"""), {
        'receipt': receipt, 'id': after['id'], 'action': 'create' if previous is None else 'update',
        'before': None if previous is None else json.dumps(previous), 'after': json.dumps(after), 'summary': summary,
    })
    return True


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
