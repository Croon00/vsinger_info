"""Apply reviewed official HONK inventory and member playlist attribution only."""
import argparse
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import sys
from uuid import NAMESPACE_URL, uuid5

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy import text
from app.db.catalog_session import catalog_runtime_session,verify_catalog_identity
from app.integrations.youtube_catalog import Video,purpose
from app.integrations.honk_youtube import CHANNEL,PLAYLISTS
from app.integrations.nurojunk_youtube import CHANNEL as NURO_CHANNEL, memberships
from app.repositories.shared_member_youtube import reconcile
from app.repositories.youtube_cover_backfill import save_page
from app.repositories.youtube_collection import _document

POLICY='honk-member-repair-20261122-v1'


def run(path,apply=False,group='honk-the-horn'):
    videos=[Video.model_validate(x) for x in json.loads((path/'videos.json').read_text(encoding='utf-8'))]
    channel=NURO_CHANNEL if group=='nurojunk' else CHANNEL
    if group=='nurojunk':
        member_proof=memberships(videos)
    else:
        playlists=json.loads((path/'playlist-items.json').read_text(encoding='utf-8'))
        member_proof={'channel_id':CHANNEL,'playlists':{}}
        for slug,external in PLAYLISTS.items():
            playlist=next(x for x in playlists if x['id']==external)
            if playlist['truncated']:
                raise ValueError('Incomplete playlist')
            member_proof['playlists'][slug]=[x['contentDetails']['videoId'] for x in playlist['items']
                if x['snippet'].get('channelId')==CHANNEL and x['snippet'].get('videoOwnerChannelId')==CHANNEL]
    if any(v.channel_id!=channel for v in videos):
        raise ValueError('Foreign publisher')
    with catalog_runtime_session() as s:
        instance=verify_catalog_identity(s)
        s.execute(text('SELECT pg_advisory_xact_lock(731064923)'))
        account=s.execute(text("SELECT id FROM external_accounts WHERE platform='youtube' AND platform_id=:channel AND archived_at IS NULL AND collection_enabled"),{'channel':channel}).scalar_one()
        ids=[v.id for v in videos]
        def snapshot():
            out={}
            for table,sql in [('videos',"SELECT v.* FROM videos v WHERE v.platform='youtube' AND v.platform_video_id=ANY(:ids)"),
                              ('covers',"SELECT c.* FROM covers c JOIN videos v ON v.id=c.video_id WHERE v.platform='youtube' AND v.platform_video_id=ANY(:ids)")]:
                out[table]={r['id']:dict(r) for r in s.execute(text(sql),{'ids':ids}).mappings()}
            return out
        before=snapshot()
        covers=[v for v in videos if purpose(v)=='cover']
        if not apply:
            return {'official_videos':len(videos),'cover_candidates':len(covers),'playlist_members':{k:len(v) for k,v in member_proof['playlists'].items()}}
        save_page(s,{'id':account,'platform_id':channel},covers)
        # One old cover premiere was incorrectly an archive with no source.
        # Exact fresh publisher proof lets us add its cover row, preserving the archive.
        for v in covers:
            vid=s.execute(text("SELECT id FROM videos WHERE platform='youtube' AND platform_video_id=:id AND source_account_id=:account AND archived_at IS NULL"),{'id':v.id,'account':account}).scalar_one_or_none()
            if vid and not s.execute(text('SELECT 1 FROM covers WHERE video_id=:id'),{'id':vid}).first():
                s.execute(text('INSERT INTO covers(video_id) VALUES (:id)'),{'id':vid})
                _document(s,video_id=v.id,kind='video_description',external_id=v.id,content=v.description,
                    metadata={'policy':POLICY,'video':v.model_dump(mode='json'),'reason':'reviewed_official_cover_premiere'},
                    disposition='applied',captured_at=datetime.now(UTC))
        after=snapshot();changes=[]
        for table,rows in after.items():
            for id,value in rows.items():
                old=before[table].get(id)
                if old!=value:changes.append((table,id,'update' if old else 'create',old,value))
        if changes:
            proof={'policy':POLICY,'source_url':'https://www.youtube.com/channel/'+channel,'video_ids':ids}
            digest=hashlib.sha256(json.dumps(proof).encode()).hexdigest()
            receipt=s.execute(text('''INSERT INTO catalog_imports(operation_id,catalog_instance_id,manifest_hash,source_kind,result_mapping,result_summary)
                VALUES (:op,:instance,:hash,'correction',CAST(:mapping AS jsonb),CAST(:proof AS jsonb)) RETURNING id'''),
                {'op':str(uuid5(NAMESPACE_URL,instance+POLICY+channel)), 'instance':instance,'hash':digest,
                 'mapping':json.dumps([{'entity_type':t,'id':id} for t,id,_,_,_ in changes]),'proof':json.dumps(proof)}).scalar_one()
            s.execute(text('''INSERT INTO catalog_changes(import_id,entity_type,entity_id,action,before_data,after_data,provenance)
                SELECT :receipt,x.table_name,x.id,x.action,x.before_data,x.after_data,CAST(:proof AS jsonb)
                FROM jsonb_to_recordset(CAST(:rows AS jsonb)) x(table_name text,id integer,action text,before_data jsonb,after_data jsonb)'''),
                {'receipt':receipt,'proof':json.dumps(proof),'rows':json.dumps([{'table_name':t,'id':id,'action':act,'before_data':b,'after_data':a} for t,id,act,b,a in changes],default=str)})
        else:receipt=None
        s.execute(text('''INSERT INTO collection_states(external_account_id,provider_state) VALUES (:account,CAST(:state AS jsonb))
            ON CONFLICT(external_account_id) DO UPDATE SET provider_state=collection_states.provider_state||EXCLUDED.provider_state'''),
            {'account':account,'state':json.dumps({'honk_memberships':member_proof})})
        return {'inventory_changes':len(changes),'inventory_receipt':receipt,'members':reconcile(s,account,member_proof)}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,default=Path('outputs/honk-members-2026-11-22'))
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--group',choices=['honk-the-horn','nurojunk'],default='honk-the-horn')
    args=parser.parse_args()
    try:print(json.dumps(run(args.input,args.apply,args.group)))
    except Exception as exc:
        print(json.dumps({'stopped':type(exc).__name__}))
        raise SystemExit(1) from None
