import json
import pytest
from sqlalchemy.orm import Session
from sqlalchemy import text
from test_catalog_migration import local_server, database, row
from test_new_catalog_read import store
from app.repositories.shared_youtube import RULES, members_for_title
from app.repositories.song_explore import explore
from app.services.catalog_read import CatalogRead


@pytest.mark.parametrize('group,title,expected', [
    ('kmnz','Song (Cover) / KMNZ',{'kmnz-lita','kmnz-tina','kmnz-nero'}),
    ('kmnz','Song (Cover) / KMNZ TINA',{'kmnz-tina'}),
    ('kmnz','Song (Cover) / KMNZ TINA × NERO',{'kmnz-tina','kmnz-nero'}),
    ('kmnz','Song (Cover) / KMNZ LITA',{'kmnz-lita'}),
    ('kmnz','Song cover #KMNZTINA',{'kmnz-tina'}),
    ('kmnz','The Best - Tina Turner (Cover) / KMNZ',{'kmnz-lita','kmnz-tina','kmnz-nero'}),
    ('kmnz','Song (Cover) / KMNZ LIZ',set()),
    ('vesperbell','Song (Cover) / VESPERBELL',{'vesperbell-yomi','vesperbell-kasuka'}),
    ('vesperbell','Song (Cover) / VESPERBELL ヨミ',{'vesperbell-yomi'}),
    ('vesperbell','Song (Cover) / VESPERBELL KASUKA',{'vesperbell-kasuka'}),
    ('vesperbell','Song cover / VESPERBELL ヨミ × カスカ',{'vesperbell-yomi','vesperbell-kasuka'}),
    ('vesperbell','【ヨミ】 Song Cover',{'vesperbell-yomi'}),
    ('kmnz','HIP (Cover) / KMNZ LITA & VESPERBELL ヨミ',{'kmnz-lita','vesperbell-yomi'}),
    ('other','Song cover / KMNZ TINA',set()),
    ('honk-the-horn','Song Cover - MOCO【HONK THE HORN】',{'moco'}),
    ('honk-the-horn','Song Cover - BAMBI【HONK THE HORN】',{'bambi'}),
    ('honk-the-horn','Song Cover【HONK THE HORN】',{'moco','bambi'}),
    ('honk-the-horn','Song Cover - BAMBIAN【HONK THE HORN】',{'moco','bambi'}),
    ('honk-the-horn','Song (Cover) / BAMBI',{'bambi'}),
    ('honk-the-horn','Song (Cover) / MOCO × BAMBI',{'moco','bambi'}),
    ('honk-the-horn','Song cover #MOCO #HTH',{'moco'}),
    ('honk-the-horn','Song cover / KMNZ LITA & HONK THE HORN',{'moco','bambi'}),
    ('nurojunk','Song (Cover) / NUROJUNK SAKUYA',{'sakuya'}),
    ('nurojunk','Song (Cover) / NUROJUNK カグラ',{'kagura'}),
    ('nurojunk','Song (Cover) / NUROJUNK',set()),
    ('honk-the-horn','Song (Cover) / NUROJUNK SAKUYA',{'moco','bambi'}),
])
def test_approved_member_display_policy(group,title,expected):
    assert members_for_title(group,title)==expected


def test_reviewed_duets_and_cross_group_collaborations_keep_publisher_scope(store):
    from app.repositories.shared_youtube import REVIEWED_COVERS
    db,engine=store
    members={};accounts={}
    for slug,names in [('honk-the-horn',['moco','bambi']),('nurojunk',['sakuya','kagura'])]:
        group=row(db,'artists',slug=slug,name_native=slug,entity_kind='group',show_in_catalog=False)
        channel=next(r['channel_id'] for r in RULES if r['group_slug']==slug)
        account=row(db,'external_accounts',platform='youtube',platform_id=channel,url='https://youtube.com/channel/'+channel)
        accounts[channel]=account
        row(db,'artist_external_accounts',artist_id=group,account_id=account,relationship='owner')
        for name in names:
            member=row(db,'artists',slug=name,name_native=name,entity_kind='solo',show_in_catalog=True)
            row(db,'artist_group_members',group_id=group,member_id=member);members[name]=member
    for external,(channel,_) in REVIEWED_COVERS.items():
        video=row(db,'videos',platform='youtube',platform_video_id=external,source_account_id=accounts[channel],title='Group cover',duration_seconds=240,availability='public')
        row(db,'covers',video_id=video)
    honk_channel='UCQXuGcIoseWY5HmW6-U7teg'
    for external,title in [('unnamed0001','New group cover / HONK THE HORN'),('solomoco001','New cover / MOCO')]:
        video=row(db,'videos',platform='youtube',platform_video_id=external,source_account_id=accounts[honk_channel],title=title,duration_seconds=240,availability='public')
        row(db,'covers',video_id=video)
    # A newly explicit solo name overrides the older reviewed duet default.
    db.execute("UPDATE videos SET title='New title Cover / BAMBI' WHERE platform_video_id='iZ0bNfLYfMI'")
    db.commit()
    with Session(engine) as session:
        for name,id in members.items():
            page=CatalogRead(session).covers(id,0,100)
            expected={external for external,(_,names) in REVIEWED_COVERS.items() if name in names}
            if name=='moco':
                expected.discard('iZ0bNfLYfMI')
                expected.update({'unnamed0001','solomoco001'})
            elif name=='bambi':expected.add('unnamed0001')
            assert {x['youtube_video_id'] for x in page['items']}==expected
            assert page['total']==len(expected)
        page=explore(session,kind='cover',agency='all',q='',order='latest',offset=0,limit=100)
        assert page['total']==8 and len({r['key'] for r in page['items']})==8


def test_shared_stats_and_covers_keep_group_ownership_and_distinct_global_rows(store):
    db,engine=store
    groups={}
    members={}
    for group in ['kmnz','vesperbell']:
        g=row(db,'artists',slug=group,name_native=group.upper(),entity_kind='group',show_in_catalog=False)
        groups[group]=g
        rules=[r for r in RULES if r['group_slug']==group]
        account=row(db,'external_accounts',platform='youtube',platform_id=rules[0]['channel_id'],url=f'https://youtube.com/@{group}')
        row(db,'artist_external_accounts',artist_id=g,account_id=account,relationship='owner')
        db.execute('INSERT INTO collection_states(external_account_id,provider_state) VALUES (%s,%s::jsonb)',
            (account,json.dumps({'youtube_channel_statistics':{'subscriber_count':123000,'created_at':'2020-01-01T00:00:00Z'}})))
        for rule in rules:
            a=row(db,'artists',slug=rule['member_slug'],name_native=rule['compact'],entity_kind='solo',show_in_catalog=True)
            row(db,'artist_group_members',group_id=g,member_id=a)
            members[rule['member_slug']]=a
        titles=(['Joint cover / KMNZ','Solo cover / KMNZ TINA','Duo cover / KMNZ TINA × NERO']
                if group=='kmnz' else ['Joint cover / VESPERBELL','Solo cover / VESPERBELL ヨミ'])
        for i,title in enumerate(titles):
            video=row(db,'videos',platform='youtube',platform_video_id=f'{group[:3]}{i:08}',source_account_id=account,title=title,duration_seconds=240)
            row(db,'covers',video_id=video)
    db.commit()
    with Session(engine) as session:
        service=CatalogRead(session)
        for slug,a in members.items():
            artist=service.artist(a)
            assert artist['youtube_subscriber_count']==123000
            assert artist['youtube_statistics_source']==slug.split('-')[0].upper()
            assert any(s['source_type']=='youtube' for s in artist['sources'])
        assert service.covers(members['kmnz-lita'],0,100)['total']==1
        assert service.covers(members['kmnz-tina'],0,100)['total']==3
        assert service.covers(members['kmnz-nero'],0,100)['total']==2
        assert service.covers(members['vesperbell-yomi'],0,100)['total']==2
        assert service.covers(members['vesperbell-kasuka'],0,100)['total']==1
        assert service.artist(groups['kmnz']) is None
        page=explore(session,kind='cover',agency='all',q='',order='high',offset=0,limit=100)
        assert page['total']==5 and len({r['key'] for r in page['items']})==5
        assert explore(session,kind='cover',agency='all',q='TINA',order='high',offset=0,limit=100)['total']==3
        assert explore(session,kind='cover',agency='all',q='KMNZ',order='high',offset=0,limit=100)['total']==3
        assert explore(session,kind='cover',agency='all',q='VESPERBELL',order='high',offset=0,limit=100)['total']==2
        assert all('KMNZ' in r['artist_name'] or 'VESPERBELL' in r['artist_name'] for r in page['items'])
    assert db.execute("SELECT count(*) FROM artist_external_accounts WHERE relationship='owner'").fetchone()[0]==2


def test_shared_channel_video_stays_global_without_assigning_unlisted_member_to_current_members(store):
    db,engine=store
    group=row(db,'artists',slug='kmnz',name_native='KMNZ',entity_kind='group',show_in_catalog=False)
    lita=row(db,'artists',slug='kmnz-lita',name_native='LITA',entity_kind='solo',show_in_catalog=True)
    row(db,'artist_group_members',group_id=group,member_id=lita)
    channel=next(r['channel_id'] for r in RULES if r['group_slug']=='kmnz')
    account=row(db,'external_accounts',platform='youtube',platform_id=channel,url='https://youtube.com/@KMNZOFFICIAL')
    row(db,'artist_external_accounts',artist_id=group,account_id=account,relationship='owner')
    video=row(db,'videos',platform='youtube',platform_video_id='sharedvid01',source_account_id=account,title='Song cover / KMNZ LIZ',duration_seconds=240)
    row(db,'covers',video_id=video);db.commit()
    with Session(engine) as session:
        page=explore(session,kind='cover',agency='all',q='KMNZ',order='high',offset=0,limit=24)
        assert page['total']==1 and page['items'][0]['artist_name']=='KMNZ'
        assert CatalogRead(session).covers(lita,0,24)['total']==0
