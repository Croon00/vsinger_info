"""Daily original-upload scope and audited, non-destructive persistence."""
import hashlib
import json
from uuid import NAMESPACE_URL, uuid5
from sqlalchemy import text

from app.services.youtube_original import POLICY, decide


def scope(session, account_id, *, lock=False):
    owners = [dict(row) for row in session.execute(text('''
        SELECT a.id,a.entity_kind kind,ARRAY_REMOVE(ARRAY[a.name_native,a.name_ko,a.name_latin],NULL) ||
          ARRAY(SELECT al.alias FROM artist_aliases al WHERE al.artist_id=a.id ORDER BY al.id) aliases
        FROM artists a JOIN artist_external_accounts ae ON ae.artist_id=a.id
        JOIN external_accounts e ON e.id=ae.account_id
        WHERE ae.account_id=:account AND ae.relationship='owner' AND a.archived_at IS NULL
          AND e.archived_at IS NULL AND e.collection_enabled AND e.platform='youtube'
        ORDER BY a.id
    ''' + (' FOR SHARE OF a,ae,e' if lock else '')), {'account': account_id}).mappings()]
    if lock:
        session.execute(text('SELECT id FROM recording_artists WHERE artist_id=ANY(CAST(:artists AS integer[])) FOR SHARE'),
                        {'artists': [o['id'] for o in owners]}).all()
    account = session.execute(text("SELECT platform_id FROM external_accounts WHERE id=:id"), {'id': account_id}).scalar_one()
    recordings = [dict(row) for row in session.execute(text('''
        SELECT DISTINCT r.id,r.version,r.title_native,r.duration_ms,v.platform_video_id official_video_id,
          r.official_video_id official_video_db_id,
          ARRAY(SELECT al.title_native FROM album_tracks at JOIN albums al ON al.id=at.album_id
                WHERE at.recording_id=r.id AND al.archived_at IS NULL) albums,
          ARRAY(SELECT credit.artist_id FROM recording_artists credit WHERE credit.recording_id=r.id) artist_ids
        FROM recordings r JOIN recording_artists ra ON ra.recording_id=r.id
        LEFT JOIN videos v ON v.id=r.official_video_id
        WHERE r.archived_at IS NULL AND ra.artist_id=ANY(CAST(:artists AS integer[]))
        ORDER BY r.id
    '''), {'artists': [o['id'] for o in owners]}).mappings()]
    for recording in recordings:
        aliases = sorted({alias for owner in owners if owner['id'] in recording['artist_ids']
                          for alias in owner['aliases'] if alias})
        recording.update(channels={account: account_id}, aliases=aliases)
        # A hidden/deleted video is still an existing manual link; never treat
        # the missing external identifier as permission to replace that link.
        if recording['official_video_db_id'] and not recording['official_video_id']:
            recording['official_video_id'] = '__existing_link__'
    return {'owners': owners, 'recordings': recordings}


def persist(session, job, payload, value, *, current, video_id, conflict):
    from app.repositories.youtube_collection import _document
    video = value['video']
    decision = value.get('original')
    if video is not None and decision is not None:
        latest = decide(video, scope(session, job.external_account_id, lock=True)).model_dump()
        conflict = conflict or latest != decision
    linked_before = None
    if decision and decision['status'] == 'link_recording' and not conflict:
        linked_before = dict(session.execute(text('SELECT * FROM recordings WHERE id=:id FOR UPDATE'),
                                             {'id': decision['recording_id']}).mappings().one())
        conflict = bool(linked_before['archived_at'] or linked_before['version'] != decision['recording_version']
                        or linked_before['official_video_id'] not in (None, video_id))
    supported = (not conflict and video_id is not None and decision is not None
                 and decision['status'] in ('new_original', 'link_recording')
                 and not current['archive'] and not current['cover'])
    linked = session.execute(text('SELECT id FROM recordings WHERE official_video_id=:video ORDER BY id FOR UPDATE'),
                             {'video': video_id}).scalars().all() if video_id else []
    if linked:
        supported = False
    metadata = dict(collector='youtube-catalog', video_id=payload.youtube_video_id,
                    extraction_version=payload.extraction_version, extractor=POLICY,
                    outcome=value['outcome'], original=decision, video=video.model_dump(mode='json') if video else None,
                    existing_recordings=linked, model_calls=0)
    document, _ = _document(session, video_id=payload.youtube_video_id, kind='video_description',
                            external_id=payload.youtube_video_id, content=video.description if video else '',
                            metadata=metadata, disposition='version_conflict' if conflict else
                            'applied' if supported else 'review_candidate', captured_at=value['captured_at'])
    if not supported:
        return
    changes = []
    if decision['status'] == 'link_recording':
        before = linked_before
        after = dict(session.execute(text('''UPDATE recordings SET official_video_id=:video,
            version=version+1,updated_at=clock_timestamp() WHERE id=:id RETURNING *'''),
            {'video': video_id, 'id': before['id']}).mappings().one())
        changes.append(('recordings', 'update', before, after))
    else:
        after = dict(session.execute(text('''INSERT INTO recordings(title_native,official_video_id,duration_ms)
            VALUES (:title,:video,:duration) RETURNING *'''),
            {'title': decision['title'], 'video': video_id,
             'duration': video.duration_seconds * 1000 if video.duration_seconds else None}).mappings().one())
        changes.append(('recordings', 'create', None, after))
        for position, artist in enumerate(decision['artist_ids']):
            credit = dict(session.execute(text('''INSERT INTO recording_artists(recording_id,artist_id,role,position)
                VALUES (:recording,:artist,'primary',:position) RETURNING *'''),
                {'recording': after['id'], 'artist': artist, 'position': position}).mappings().one())
            changes.append(('recording_artists', 'create', None, credit))
    identity = session.execute(text('SELECT id::text FROM catalog_instance')).scalar_one()
    proof = dict(policy=POLICY, job_id=job.id, account_id=job.external_account_id,
                 source_document_id=document, source_url=f'https://www.youtube.com/watch?v={payload.youtube_video_id}',
                 decision=decision)
    digest = hashlib.sha256(json.dumps(proof, sort_keys=True).encode()).hexdigest()
    receipt = session.execute(text('''INSERT INTO catalog_imports(operation_id,catalog_instance_id,manifest_hash,
        source_kind,result_mapping,result_summary) VALUES (:op,:instance,:hash,'batch_import',CAST(:mapping AS jsonb),
        CAST(:summary AS jsonb)) RETURNING id'''),
        {'op': str(uuid5(NAMESPACE_URL, identity + ':' + POLICY + ':' + str(job.id))),
         'instance': identity, 'hash': digest,
         'mapping': json.dumps([{'entity_type': table, 'id': data['id']} for table, _, _, data in changes]),
         'summary': json.dumps(proof)}).scalar_one()
    for table, action, before, after in changes:
        session.execute(text('''INSERT INTO catalog_changes(import_id,entity_type,entity_id,action,before_data,
            after_data,provenance) VALUES (:receipt,:table,:id,:action,CAST(:before AS jsonb),
            CAST(:after AS jsonb),CAST(:proof AS jsonb))'''),
            {'receipt': receipt, 'table': table, 'id': after['id'], 'action': action,
             'before': json.dumps(before, default=str) if before else None,
             'after': json.dumps(after, default=str), 'proof': json.dumps(proof)})
