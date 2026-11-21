import asyncio
from unittest.mock import AsyncMock
from types import SimpleNamespace
import pytest
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.integrations.honk_youtube import CHANNEL, PLAYLISTS, collect_memberships
from app.integrations.youtube_catalog import YouTubeFailure
from app.repositories.shared_member_youtube import reconcile
from app.integrations.nurojunk_youtube import CHANNEL as NURO_CHANNEL, memberships as nuro_memberships
from app.services.catalog_read import CatalogRead
from test_catalog_migration import local_server, database, row
from test_new_catalog_read import store


def test_playlist_credits_require_exact_playlist_owner_and_publisher():
    items=[{'snippet':{'channelId':CHANNEL,'videoOwnerChannelId':CHANNEL},'contentDetails':{'videoId':'abcdefghijk'}},
           {'snippet':{'channelId':CHANNEL,'title':'Private video'},'contentDetails':{'videoId':'private0001'}},
           {'snippet':{'channelId':CHANNEL,'videoOwnerChannelId':'foreign'},'contentDetails':{'videoId':'foreign0001'}}]
    provider=SimpleNamespace(get=AsyncMock(return_value={'items':items}))
    result=asyncio.run(collect_memberships(provider))
    assert result['playlists']=={'moco':['abcdefghijk'],'bambi':['abcdefghijk']}
    assert [x.kwargs['playlistId'] for x in provider.get.call_args_list]==list(PLAYLISTS.values())


def test_truncated_member_playlist_does_not_silently_apply_partial_credits():
    provider=SimpleNamespace(get=AsyncMock(return_value={'items':[],'nextPageToken':'more'}))
    with pytest.raises(YouTubeFailure):asyncio.run(collect_memberships(provider))


def test_nuro_review_keeps_ambiguous_thumbnails_and_social_boilerplate_unassigned():
    samples=[SimpleNamespace(channel_id=NURO_CHANNEL,started_at=True,title='【歌枠】サクヤ、歌います！！【#NUROJUNK】',id='newhost0001'),
             SimpleNamespace(channel_id=NURO_CHANNEL,started_at=True,title='【歌枠】KAGURA Birthday GOODS 発売中',id='promotion01')]
    proof=nuro_memberships(samples)['playlists']
    assert 'newhost0001' in proof['sakuya'] and 'promotion01' not in proof['kagura']
    assert all('ITHQE7YrLz8' not in ids and 'V2JXCTh6ens' not in ids for ids in proof.values())


@pytest.mark.parametrize('slug,lead,other,channel', [('honk-the-horn','moco','bambi',CHANNEL),('nurojunk','sakuya','kagura',NURO_CHANNEL)])
def test_official_membership_updates_hosts_and_setlists_but_preserves_unrelated_rows(store,slug,lead,other,channel):
    db,engine=store
    group=row(db,'artists',slug=slug,name_native=slug,entity_kind='group',show_in_catalog=False)
    moco=row(db,'artists',slug=lead,name_native=lead,entity_kind='solo',show_in_catalog=True)
    bambi=row(db,'artists',slug=other,name_native=other,entity_kind='solo',show_in_catalog=True)
    for artist in [moco,bambi]:row(db,'artist_group_members',group_id=group,member_id=artist)
    account=row(db,'external_accounts',platform='youtube',platform_id=channel,url='https://youtube.com/channel/'+channel,collection_enabled=True)
    row(db,'artist_external_accounts',artist_id=group,account_id=account,relationship='owner')
    video=row(db,'videos',platform='youtube',platform_video_id='abcdefghijk',source_account_id=account,title='歌枠',availability='public')
    archive=row(db,'live_archives',video_id=video,primary_artist_id=group)
    row(db,'archive_artists',archive_id=archive,artist_id=group,role='host')
    performance=row(db,'performances',archive_id=archive,ordinal=1,start_seconds=30,raw_title='Song')
    row(db,'performance_artists',performance_id=performance,artist_id=group,role='lead')
    wrong_video=row(db,'videos',platform='youtube',platform_video_id='wrongvideo1',title='Original artist MV',availability='public')
    row(db,'live_archives',video_id=wrong_video,primary_artist_id=moco)
    title='Song Cover - BAMBI【HONK THE HORN】' if slug=='honk-the-horn' else 'Song (Cover) / NUROJUNK KAGURA'
    cover_video=row(db,'videos',platform='youtube',platform_video_id='covervideo1',source_account_id=account,title=title,availability='public',duration_seconds=240)
    row(db,'covers',video_id=cover_video)
    db.commit()
    proof={'channel_id':channel,'playlists':{lead:['abcdefghijk'],other:[]}}
    with Session(engine) as session,session.begin():
        result=reconcile(session,account,proof)
        assert result['changed']==3
        assert reconcile(session,account,proof)=={'changed':0}
        read=CatalogRead(session)
        assert read.lives(moco,0,24)['total']==1
        assert read.lives(bambi,0,24)['total']==0
        assert read.covers(moco,0,24)['total']==0
        assert read.covers(bambi,0,24)['total']==1
        assert session.execute(text('SELECT primary_artist_id FROM live_archives WHERE id=:id'),{'id':archive}).scalar_one()==moco
        assert session.execute(text('SELECT count(*) FROM performance_artists WHERE performance_id=:id'),{'id':performance}).scalar_one()==2
        assert session.execute(text('SELECT count(*) FROM catalog_changes WHERE import_id=:id'),{'id':result['receipt']}).scalar_one()==3
