"""Audited shared-channel hosts from official playlists or reviewed video evidence."""
from datetime import UTC, datetime
import hashlib
import json
from uuid import NAMESPACE_URL, uuid5
from sqlalchemy import text
from app.integrations.honk_youtube import CHANNEL, PLAYLISTS, Membership
from app.integrations.nurojunk_youtube import CHANNEL as NURO_CHANNEL

POLICY = 'honk-official-member-playlists-v1'


def reconcile(session, account, raw):
    proof = Membership.model_validate(raw)
    is_nuro = proof.channel_id == NURO_CHANNEL
    channel = NURO_CHANNEL if is_nuro else CHANNEL
    group_slug = 'nurojunk' if is_nuro else 'honk-the-horn'
    member_slugs = ['sakuya','kagura'] if is_nuro else list(PLAYLISTS)
    if proof.channel_id != channel or set(proof.playlists) != set(member_slugs):
        raise ValueError('Unexpected HONK playlist proof')
    owners = session.execute(text('''SELECT a.id FROM external_accounts e JOIN artist_external_accounts ae ON ae.account_id=e.id
        JOIN artists a ON a.id=ae.artist_id WHERE e.id=:account AND e.platform='youtube' AND e.platform_id=:channel
        AND e.archived_at IS NULL AND ae.relationship='owner' AND a.slug=:slug AND a.archived_at IS NULL
        FOR SHARE OF e,ae,a'''), {'account': account, 'channel': channel, 'slug':group_slug}).scalars().all()
    if len(owners) != 1:
        raise ValueError('Official group owner required')
    group = owners[0]
    members = dict(session.execute(text('''SELECT a.slug,a.id FROM artist_group_members gm JOIN artists a ON a.id=gm.member_id
        WHERE gm.group_id=:group AND gm.left_on IS NULL AND a.slug=ANY(:slugs) AND a.archived_at IS NULL
        FOR SHARE OF gm,a'''), {'group': group,'slugs':member_slugs}).all())
    if set(members) != set(member_slugs):
        raise ValueError('Active members required')
    evidence = {'policy': POLICY, 'channel_id': channel, 'basis':proof.basis,'playlists': {
        slug: {'url': 'https://www.youtube.com/channel/'+channel if is_nuro else 'https://www.youtube.com/playlist?list='+PLAYLISTS[slug], 'videos': sorted(set(ids)),
               **({'thumbnail_urls':['https://i.ytimg.com/vi/'+id+'/mqdefault.jpg' for id in sorted(set(ids))]} if is_nuro else {})}
        for slug, ids in proof.playlists.items()}}
    digest = hashlib.sha256(json.dumps(evidence, sort_keys=True).encode()).hexdigest()
    changes = []
    rows = session.execute(text('''SELECT l.* ,v.platform_video_id external FROM live_archives l JOIN videos v ON v.id=l.video_id
        WHERE v.source_account_id=:account AND l.archived_at IS NULL AND v.archived_at IS NULL
        AND NOT EXISTS(SELECT 1 FROM covers c WHERE c.video_id=v.id AND c.archived_at IS NULL)
        ORDER BY l.id FOR UPDATE OF l'''), {'account': account}).mappings().all()
    for row in rows:
        ids = [members[slug] for slug, videos in proof.playlists.items() if row['external'] in videos]
        if not ids or row['primary_artist_id'] not in [None, group, *ids]:
            continue
        primary = ids[0] if len(ids) == 1 else group
        if row['primary_artist_id'] != primary:
            before = {k:v for k,v in row.items() if k != 'external'}
            after = dict(session.execute(text('UPDATE live_archives SET primary_artist_id=:artist WHERE id=:id RETURNING *'),
                                         {'artist': primary, 'id': row['id']}).mappings().one())
            changes.append(('live_archives','update',before,after))
        for i, artist in enumerate(ids):
            added = session.execute(text('''INSERT INTO archive_artists(archive_id,artist_id,role,position)
                SELECT :archive,:artist,'host',:position WHERE NOT EXISTS(SELECT 1 FROM archive_artists
                WHERE archive_id=:archive AND artist_id=:artist) RETURNING *'''),
                {'archive': row['id'], 'artist': artist, 'position': i+1}).mappings().all()
            changes.extend(('archive_artists','create',None,dict(x)) for x in added)
            added = session.execute(text('''INSERT INTO performance_artists(performance_id,artist_id,role,position)
                SELECT p.id,:artist,'lead',:position FROM performances p WHERE p.archive_id=:archive AND p.archived_at IS NULL
                AND EXISTS(SELECT 1 FROM performance_artists old WHERE old.performance_id=p.id AND old.artist_id=:group)
                AND NOT EXISTS(SELECT 1 FROM performance_artists old WHERE old.performance_id=p.id AND old.artist_id<>:group
                               AND old.artist_id NOT IN (SELECT member_id FROM artist_group_members WHERE group_id=:group AND left_on IS NULL))
                AND NOT EXISTS(SELECT 1 FROM performance_artists old WHERE old.performance_id=p.id AND old.artist_id=:artist)
                RETURNING *'''), {'archive': row['id'], 'artist': artist, 'group': group, 'position': i+1}).mappings().all()
            changes.extend(('performance_artists','create',None,dict(x)) for x in added)
    if not changes:
        return {'changed': 0}
    metadata = json.dumps(evidence)
    source = session.execute(text('''INSERT INTO source_documents(source_kind,source_url,external_id,captured_at,content_hash,source_metadata)
        SELECT 'official_page',:url,:external,:captured,:hash,CAST(:metadata AS jsonb)
        WHERE NOT EXISTS(SELECT 1 FROM source_documents WHERE content_hash=:hash) RETURNING id'''),
        {'url': 'https://www.youtube.com/channel/'+channel, 'external': channel,
         'captured': datetime.now(UTC), 'hash': digest, 'metadata': metadata}).scalar_one_or_none()
    if source is None:
        source = session.execute(text('SELECT id FROM source_documents WHERE content_hash=:hash LIMIT 1'), {'hash': digest}).scalar_one()
    instance = session.execute(text('SELECT id::text FROM catalog_instance')).scalar_one()
    mapping = [{'entity_type':t,'id':a['id']} for t,_,_,a in changes]
    operation = str(uuid5(NAMESPACE_URL, instance+POLICY+digest+json.dumps(mapping)))
    receipt = session.execute(text('''INSERT INTO catalog_imports(operation_id,catalog_instance_id,manifest_hash,source_kind,result_mapping,result_summary)
        VALUES (:op,:instance,:hash,'correction',CAST(:mapping AS jsonb),CAST(:summary AS jsonb)) RETURNING id'''),
        {'op': operation,'instance': instance,'hash':digest,'mapping':json.dumps(mapping),
         'summary':json.dumps({'policy':POLICY,'source_document_id':source,'changed':len(changes)})}).scalar_one()
    session.execute(text('''INSERT INTO catalog_changes(import_id,entity_type,entity_id,action,before_data,after_data,provenance)
        SELECT :receipt,x.table_name,x.id,x.action,x.before_data,x.after_data,CAST(:proof AS jsonb)
        FROM jsonb_to_recordset(CAST(:rows AS jsonb)) x(table_name text,id integer,action text,before_data jsonb,after_data jsonb)'''),
        {'receipt':receipt,'proof':json.dumps({'policy':POLICY,'source_document_id':source,'source_hash':digest}),
         'rows':json.dumps([{'table_name':t,'id':a['id'],'action':act,'before_data':b,'after_data':a} for t,act,b,a in changes],default=str)})
    return {'changed':len(changes),'receipt':receipt}
