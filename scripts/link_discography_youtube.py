"""Explicit official-channel API scan, audited links, and unresolved URL worksheet.

Does not run from a read endpoint. Uses bounded uploads lists rather than one
100-unit search call per track. Cache contains public video metadata only.
"""
import argparse,asyncio,csv,hashlib,json,sys
from collections import defaultdict,Counter
from pathlib import Path
from uuid import uuid5,NAMESPACE_URL
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from sqlalchemy import text
from sqlalchemy.orm import Session
import httpx
from app.core.config import settings
from app.db.catalog_session import catalog_engine,catalog_url,verify_catalog_identity
from app.integrations.youtube_catalog import YouTubeClient,YouTubeFailure
from app.services.recording_youtube_match import choose


def csv_cell(value):
    # Public provider titles are data, including when the worksheet is opened in Excel.
    value=str(value)
    return "'"+value if value.lstrip().startswith(('=','+','-','@')) else value


def save_json(path,value):
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')
    temporary.replace(path)


def snapshot(session):
    identity=verify_catalog_identity(session)
    artists={r['id']:dict(r) for r in session.execute(text('SELECT id,name_native,name_latin,name_ko FROM artists WHERE archived_at IS NULL')).mappings()}
    aliases=defaultdict(list)
    for r in session.execute(text('SELECT artist_id,alias FROM artist_aliases')):
        aliases[r[0]].append(r[1])
    accounts=[dict(r) for r in session.execute(text("SELECT e.id,e.platform_id,a.artist_id FROM external_accounts e JOIN artist_external_accounts a ON a.account_id=e.id AND a.relationship='owner' JOIN artists ar ON ar.id=a.artist_id AND ar.archived_at IS NULL AND ar.show_in_catalog WHERE e.platform='youtube' AND e.archived_at IS NULL AND e.platform_id ~ '^UC[A-Za-z0-9_-]{22}$'")).mappings()]
    channel_map=defaultdict(dict)
    for account in accounts:
        channel_map[account['artist_id']][account['platform_id']]=account['id']
    credits=defaultdict(list)
    for r in session.execute(text('SELECT recording_id,artist_id FROM recording_artists ORDER BY recording_id,position')):
        credits[r[0]].append(r[1])
    provider_names=defaultdict(list)
    for r in session.execute(text("""WITH first_credit AS (
        SELECT DISTINCT ON (x.recording_id) x.recording_id,x.external_id
        FROM recording_external_ids x WHERE x.platform='spotify' AND EXISTS (
            SELECT 1 FROM recording_provider_credits c WHERE c.platform='spotify' AND c.track_id=x.external_id)
        ORDER BY x.recording_id,x.id)
        SELECT f.recording_id,c.name FROM first_credit f JOIN recording_provider_credits c
          ON c.platform='spotify' AND c.track_id=f.external_id ORDER BY f.recording_id,c.position""")):
        provider_names[r[0]].append(r[1])
    albums=defaultdict(list)
    for r in session.execute(text('SELECT t.recording_id,a.title_native FROM album_tracks t JOIN albums a ON a.id=t.album_id AND a.archived_at IS NULL')):
        albums[r[0]].append(r[1])
    recordings=[]
    for row in session.execute(text('SELECT id,version,title_native,duration_ms,official_video_id FROM recordings WHERE archived_at IS NULL ORDER BY id')).mappings():
        aid=[x for x in credits[row['id']] if x in channel_map]
        if row['id'] not in albums:continue
        recording=dict(row)
        recording.update(channels={k:v for x in aid for k,v in channel_map[x].items()},
            aliases=list(dict.fromkeys([name for x in aid for name in [artists[x]['name_native'],artists[x]['name_latin'],artists[x]['name_ko'],*aliases[x]] if name])),
            artist_names=provider_names[row['id']] or [artists[x]['name_native'] for x in credits[row['id']] if x in artists],
            albums=list(dict.fromkeys(albums[row['id']])))
        recordings.append(recording)
    return identity,recordings,accounts


async def index_channels(provider,channels,output,max_pages):
    path=output/'channel-cache.json'
    cache=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    for channel in channels:
        if channel in cache and cache[channel].get('done'):continue
        state=cache.setdefault(channel,dict(items=[],token=None,done=False,pages=0))
        try:
            if not state.get('playlist'):
                data=await provider.get('channels',part='contentDetails',id=channel)
                state['playlist']=data['items'][0]['contentDetails']['relatedPlaylists']['uploads']
            for _ in range(max_pages-state['pages']):
                data=await provider.get('playlistItems',part='snippet,contentDetails',playlistId=state['playlist'],maxResults=50,
                    **({'pageToken':state['token']} if state['token'] else {}))
                for item in data['items']:
                    snippet=item['snippet']
                    if snippet.get('videoOwnerChannelId',channel)!=channel:continue
                    state['items'].append(dict(id=item['contentDetails']['videoId'],title=snippet['title'],channel_id=channel,
                        description=snippet.get('description','')))
                state.update(token=data.get('nextPageToken'),pages=state['pages']+1,done=not data.get('nextPageToken'))
                save_json(path,cache)
                if state['done']:break
            print(json.dumps(dict(channel=channel,pages=state['pages'],items=len(state['items']),complete=state['done'])),flush=True)
        except (IndexError,KeyError,TypeError):
            state['error']='malformed_or_unavailable_channel'
            save_json(path,cache)
        except YouTubeFailure as exc:
            state['error']=exc.reason
            save_json(path,cache)
            print(json.dumps(dict(provider_error=exc.reason,retry_after=exc.retry_after)),flush=True)
            break
    return cache


def apply(session,identity,matches):
    if verify_catalog_identity(session)!=identity:raise ValueError('Catalog changed')
    if not matches:return dict(status='no_matches',linked=0)
    sids=sorted((r['id'],r['match']['video']['id']) for r in matches)
    digest=hashlib.sha256(json.dumps(sids).encode()).hexdigest()
    operation=str(uuid5(NAMESPACE_URL,identity+':discography-youtube-v1:'+digest))
    session.execute(text('SELECT pg_advisory_xact_lock(731064924)'))
    session.execute(text('SELECT pg_advisory_xact_lock(731064925)'))
    prior=session.execute(text('SELECT id FROM catalog_imports WHERE operation_id=:op'),dict(op=operation)).scalar_one_or_none()
    if prior:return dict(receipt_id=prior,status='already_applied')
    changes=[]
    for recording in matches:
        current=dict(session.execute(text('SELECT * FROM recordings WHERE id=:id FOR UPDATE'),dict(id=recording['id'])).mappings().one())
        if current['official_video_id'] or current['archived_at']:continue
        if current['version']!=recording['version']:raise ValueError('Recording changed since scan')
        video=recording['match']['video'];account=recording['channels'][video['channel_id']]
        owner=session.execute(text("SELECT 1 FROM external_accounts ea JOIN artist_external_accounts ae ON ae.account_id=ea.id AND ae.relationship='owner' JOIN recording_artists ra ON ra.artist_id=ae.artist_id AND ra.recording_id=:recording JOIN artists ar ON ar.id=ra.artist_id AND ar.archived_at IS NULL AND ar.show_in_catalog WHERE ea.id=:account AND ea.platform='youtube' AND ea.platform_id=:channel AND ea.archived_at IS NULL"),dict(recording=recording['id'],account=account,channel=video['channel_id'])).first()
        if not owner:raise ValueError('Channel ownership changed')
        found=session.execute(text("SELECT * FROM videos WHERE platform='youtube' AND platform_video_id=:id FOR UPDATE"),dict(id=video['id'])).mappings().one_or_none()
        if found and (found['archived_at'] or found['source_account_id'] not in (None,account)):continue
        if not found:
            found=dict(session.execute(text("INSERT INTO videos(platform,platform_video_id,source_account_id,title,published_at,duration_seconds,availability) VALUES ('youtube',:external,:account,:title,:published,:duration,:availability) RETURNING *"),dict(external=video['id'],account=account,title=video['title'],published=video.get('published_at'),duration=video['duration_seconds'],availability=video['availability'])).mappings().one())
            changes.append(('videos',None,found,recording['match']))
        elif found['availability'] not in ('public','unlisted'):
            before=dict(found)
            found=dict(session.execute(text('UPDATE videos SET availability=:available,duration_seconds=:duration,version=version+1,updated_at=clock_timestamp() WHERE id=:id RETURNING *'),dict(available=video['availability'],duration=video['duration_seconds'],id=found['id'])).mappings().one())
            changes.append(('videos',before,found,recording['match']))
        after=dict(session.execute(text('UPDATE recordings SET official_video_id=:video,version=version+1,updated_at=clock_timestamp() WHERE id=:id RETURNING *'),dict(video=found['id'],id=recording['id'])).mappings().one())
        changes.append(('recordings',current,after,recording['match']))
    receipt=session.execute(text("INSERT INTO catalog_imports(operation_id,catalog_instance_id,manifest_hash,source_kind,result_mapping,result_summary) VALUES (:op,:instance,:hash,'manual','[]'::jsonb,CAST(:summary AS jsonb)) RETURNING id"),dict(op=operation,instance=identity,hash=digest,summary=json.dumps(dict(policy='discography-youtube-v1',linked=sum(t=='recordings' for t,_,_,_ in changes))))).scalar_one()
    audit_rows=[dict(receipt=receipt,table=table,id=after['id'],action='update' if before else 'create',
        before=json.dumps(before,default=str) if before else None,after=json.dumps(after,default=str),
        provenance=json.dumps(dict(policy='discography-youtube-v1',authority='user_requested_track_youtube_links',
            basis=match['reason'],video_id=match['video']['id'],channel_id=match['video']['channel_id'])))
        for table,before,after,match in changes]
    if audit_rows:
        session.execute(text("INSERT INTO catalog_changes(import_id,entity_type,entity_id,action,before_data,after_data,provenance) VALUES (:receipt,:table,:id,:action,CAST(:before AS jsonb),CAST(:after AS jsonb),CAST(:provenance AS jsonb))"),audit_rows)
    return dict(receipt_id=receipt,linked=sum(t=='recordings' for t,_,_,_ in changes))


async def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--direct-connect',action='store_true')
    parser.add_argument('--max-pages',type=int,default=60)
    args=parser.parse_args()
    if not 1<=args.max_pages<=100:raise ValueError('max-pages must be 1..100')
    args.output.mkdir(parents=True,exist_ok=True)
    engine=catalog_engine(catalog_url())
    with Session(engine) as session:
        session.execute(text('SET TRANSACTION READ ONLY'))
        session.execute(text("SET LOCAL statement_timeout='30s'"))
        identity,recordings,accounts=snapshot(session)
    needed=list(dict.fromkeys(channel for r in recordings if not r['official_video_id'] for channel in r['channels']))
    provider=YouTubeClient(settings.youtube_api_key or '',transport=httpx.AsyncHTTPTransport() if args.direct_connect else None)
    cache=await index_channels(provider,needed,args.output,args.max_pages)
    # Metadata detail calls only for title candidates, batched in groups of 50.
    from app.services.recording_youtube_match import title_matches
    candidate_ids=set()
    for r in recordings:
        if r['official_video_id']:continue
        for channel in r['channels']:
            candidate_ids.update(v['id'] for v in cache.get(channel,{}).get('items',[]) if title_matches(r['title_native'],v['title'],r['aliases']))
    detail_path=args.output/'video-cache.json'
    details=json.loads(detail_path.read_text(encoding='utf-8')) if detail_path.exists() else {}
    missing=sorted(candidate_ids-set(details))
    for start in range(0,len(missing),50):
        try:
            videos=await provider.videos(missing[start:start+50])
            for video in videos:details[video.id]=video.model_dump(mode='json')
            save_json(detail_path,details)
        except YouTubeFailure as exc:
            print(json.dumps(dict(provider_error=exc.reason)),flush=True);break
    by_channel=defaultdict(list)
    for video in details.values():by_channel[video['channel_id']].append(video)
    for r in recordings:
        r['match']=dict(status='existing') if r['official_video_id'] else choose(r,[v for c in r['channels'] for v in by_channel[c]])
        if not r['channels'] and not r['official_video_id']:
            r['match']=dict(status='unresolved',reason='no_registered_performer_channel')
        elif r['match']['status']=='unresolved' and any(not cache.get(c,{}).get('done') for c in r['channels']):
            r['match']['reason']='channel_scan_incomplete'
    report=dict(catalog_instance_id=identity,counts=dict(Counter(r['match']['status'] for r in recordings)),items=recordings)
    (args.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    if args.apply:
        with Session(engine) as session,session.begin():
            session.execute(text("SET LOCAL lock_timeout='10s'"))
            report['application']=apply(session,identity,[r for r in recordings if r['match']['status']=='matched'])
        # Ownership/archival conflicts deliberately preserve existing rows. Put any
        # unapplied candidate back in the worksheet instead of implying it was linked.
        matched_ids=[r['id'] for r in recordings if r['match']['status']=='matched']
        if matched_ids:
            with Session(engine) as session:
                session.execute(text('SET TRANSACTION READ ONLY'))
                verify_catalog_identity(session)
                linked=set(session.execute(text('SELECT id FROM recordings WHERE id=ANY(CAST(:ids AS integer[])) AND official_video_id IS NOT NULL AND archived_at IS NULL'),dict(ids=matched_ids)).scalars())
            for r in recordings:
                if r['match']['status']=='matched' and r['id'] not in linked:
                    r['match']=dict(status='unresolved',reason='existing_row_conflict_or_unapplied_link')
            report['counts']=dict(Counter(r['match']['status'] for r in recordings))
        (args.output/'receipt.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    with (args.output/'unresolved.csv').open('w',encoding='utf-8-sig',newline='') as file:
        writer=csv.writer(file);writer.writerow(['recording_id','artist','song','album','reason','youtube_url'])
        for r in recordings:
            if r['match']['status']=='unresolved':writer.writerow([r['id'],csv_cell(' / '.join(r['artist_names'])),csv_cell(r['title_native']),csv_cell(' / '.join(r['albums'])),r['match']['reason'],''])
    groups=defaultdict(list)
    for r in recordings:
        if r['match']['status']=='unresolved':groups[' / '.join(r['artist_names']) or '명의 미확인'].append(r)
    lines=['# YouTube URL 확인이 필요한 곡', '',
        '아티스트 · 곡명 · recording_id와 URL을 보내거나 CSV의 youtube_url 열을 채워 주세요.',
        'Instrumental·리믹스·라이브 버전은 해당 버전의 URL이 필요합니다. 목록은 YouTube에 영상이 없다는 뜻이 아니라 자동 연결을 확정하지 못한 결과입니다.', '']
    reasons=dict(no_registered_performer_channel='등록된 가창자의 공식 채널 없음',
        channel_scan_incomplete='채널 조회 미완료 또는 최대 범위 도달',
        no_verified_title_version_and_artist_match='곡명·버전·재생 길이와 일치하는 영상 미확정',
        multiple_verified_candidates='공식 영상 후보가 여러 개',
        live_release_requires_version_review='라이브 음원 버전 확인 필요')
    for artist,items in sorted(groups.items()):
        lines.extend([f'## {artist}', ''])
        for r in items:lines.append(f"- `{r['id']}` {r['title_native']} — {' / '.join(r['albums'])} ({reasons.get(r['match']['reason'],r['match']['reason'])})")
        lines.append('')
    (args.output/'unresolved.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps(dict(counts=report['counts'],application=report.get('application'))),flush=True)

if __name__=='__main__':asyncio.run(main())
