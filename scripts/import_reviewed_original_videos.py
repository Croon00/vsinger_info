"""Import explicitly reviewed original MVs; dry-run by default, no provider calls."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import uuid

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy import text
from app.db.catalog_session import catalog_runtime_session,verify_catalog_identity
from app.integrations.youtube_catalog import Video
from app.integrations.youtube_cover_rules import is_cover_title
from app.repositories.shared_youtube import COVER_SOURCE_CHANNELS


def run(path,apply=False):
    raw=path.read_bytes();manifest=json.loads(raw);changes=[]
    with catalog_runtime_session() as s:
        identity=verify_catalog_identity(s)
        s.execute(text('SELECT pg_advisory_xact_lock(731064923)'))
        operation=str(uuid.uuid5(uuid.NAMESPACE_URL,identity+manifest['policy']))
        if s.execute(text('SELECT 1 FROM catalog_imports WHERE operation_id=:op'),{'op':operation}).first():
            return {'already_applied':True}
        def create(table,sql,params):
            value=dict(s.execute(text(sql),params).mappings().one())
            changes.append((table,value,'create',None));return value['id']
        planned=[]
        for item in manifest['items']:
            v=Video.model_validate(item['video'])
            if is_cover_title(v.title) or 'official music video' not in v.title.lower():
                raise ValueError('Reviewed original MV evidence required')
            if v.channel_id not in (COVER_SOURCE_CHANNELS['kmnz']+COVER_SOURCE_CHANNELS['vesperbell']
                                    + ['UCQXuGcIoseWY5HmW6-U7teg','UCuvYHCPdMxfvjW_F9w5LmRA']):
                raise ValueError('Unapproved publisher')
            account=s.execute(text("SELECT id FROM external_accounts WHERE platform='youtube' AND platform_id=:channel AND archived_at IS NULL"),{'channel':v.channel_id}).scalar_one_or_none()
            if account is None and apply:
                # This exact additional VESPERBELL music publisher was reviewed
                # against the primary uploads playlist and channels.list.
                if v.channel_id!='UCKaDMw10CmbE22XJhaunoiQ':
                    raise ValueError('Register missing sources through account review')
                account=create('external_accounts',"INSERT INTO external_accounts(platform,platform_id,url,collection_enabled) VALUES ('youtube',:channel,:url,true) RETURNING *",{'channel':v.channel_id,'url':'https://www.youtube.com/channel/'+v.channel_id})
                group=s.execute(text("SELECT id FROM artists WHERE slug='vesperbell' AND archived_at IS NULL")).scalar_one()
                create('artist_external_accounts',"INSERT INTO artist_external_accounts(artist_id,account_id,relationship,is_primary,label,position) VALUES (:artist,:account,'owner',false,'YouTube music source',100) RETURNING *",{'artist':group,'account':account})
            credits=[s.execute(text('SELECT id FROM artists WHERE slug=:slug AND archived_at IS NULL'),{'slug':slug}).scalar_one() for slug in item['artist_slugs']]
            existing=s.execute(text("SELECT id,source_account_id,archived_at FROM videos WHERE platform='youtube' AND platform_video_id=:id"),{'id':v.id}).mappings().first()
            if existing and (existing['source_account_id'] not in (None,account) or existing['archived_at']):
                raise ValueError('Existing video source or archive conflict')
            linked=existing and s.execute(text('SELECT id FROM recordings WHERE official_video_id=:id AND archived_at IS NULL'),{'id':existing['id']}).first()
            if not linked:planned.append((item,v,account,credits,existing))
        if not apply:return {'reviewed':len(manifest['items']),'new_recordings':len(planned)}
        for item,v,account,credits,existing in planned:
            if existing:
                video=existing['id']
                if existing['source_account_id'] is None:
                    before=dict(s.execute(text('SELECT * FROM videos WHERE id=:id'),{'id':video}).mappings().one())
                    after=dict(s.execute(text('UPDATE videos SET source_account_id=:account WHERE id=:id AND source_account_id IS NULL RETURNING *'),{'account':account,'id':video}).mappings().one())
                    changes.append(('videos',after,'update',before))
            else:
                video=create('videos',"INSERT INTO videos(platform,platform_video_id,source_account_id,title,published_at,duration_seconds,availability) VALUES ('youtube',:external,:account,:title,:published,:duration,:availability) RETURNING *",{'external':v.id,'account':account,'title':v.title,'published':v.published_at,'duration':v.duration_seconds,'availability':v.availability})
            recording=create('recordings','INSERT INTO recordings(title_native,official_video_id,duration_ms) VALUES (:title,:video,:duration) RETURNING *',{'title':item['title'],'video':video,'duration':v.duration_seconds*1000 if v.duration_seconds else None})
            for artist in credits:
                create('recording_artists',"INSERT INTO recording_artists(recording_id,artist_id,role) VALUES (:recording,:artist,'primary') RETURNING *",{'recording':recording,'artist':artist})
        receipt=s.execute(text("INSERT INTO catalog_imports(operation_id,catalog_instance_id,manifest_hash,source_kind,result_mapping,result_summary) VALUES (:op,:instance,:hash,'manual',CAST(:mapping AS jsonb),CAST(:summary AS jsonb)) RETURNING id"),{'op':operation,'instance':identity,'hash':hashlib.sha256(raw).hexdigest(),'mapping':json.dumps([{'entity_type':t,'id':v['id']} for t,v,_,_ in changes]),'summary':json.dumps({'policy':manifest['policy'],'manifest':str(path),'recordings':len(planned)})}).scalar_one()
        proof={'policy':manifest['policy'],'manifest':str(path),'sources':['https://www.youtube.com/watch?v='+v.id for _,v,_,_,_ in planned]}
        for table,value,action,before in changes:
            s.execute(text("INSERT INTO catalog_changes(import_id,entity_type,entity_id,action,before_data,after_data,provenance) VALUES (:receipt,:table,:id,:action,CAST(:before AS jsonb),CAST(:data AS jsonb),CAST(:proof AS jsonb))"),{'receipt':receipt,'table':table,'id':value['id'],'action':action,'before':json.dumps(before,default=str) if before else None,'data':json.dumps(value,default=str),'proof':json.dumps(proof)})
        return {'recordings':len(planned),'receipt':receipt}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest',type=Path)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    print(json.dumps(run(args.manifest,args.apply)))
