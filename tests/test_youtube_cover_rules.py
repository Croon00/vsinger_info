import pytest
import asyncio
import httpx
from datetime import UTC,datetime,timedelta
from app.integrations.youtube_catalog import Video, purpose, YouTubeClient
from app.integrations.youtube_cover_rules import is_cover_title


@pytest.mark.parametrize('title,expected', [
    ('【歌ってみた】ねむるまち - くじら covered by 明透【神椿】', True),
    ('この世界を愛したい cover.鹿乃', True),
    ('Song / Covered by Singer', True),
    ('曲名【カバー】', True),
    ('노래 커버', True),
    ('花譜 #36「不可解」【オリジナルMV「不可解」Live Ver.】', False),
    ('ヰ世界情緒 #10 「シリウスの心臓」【Official Music Video】', False),
    ('【音楽的同位体可不】フォニイ / 花譜 feat. 可不(KAFU)', False),
    ('Original song / 歌唱：Singer', False),
    ('Uncovered / Official MV', False),
    ('Song / self-cover', False),
    ('セルフカバー 歌ってみた', False),
])
def test_cover_requires_explicit_title_evidence(title, expected):
    assert is_cover_title(title) is expected
    video=Video(id='abcdefghijk',channel_id='UC'+'a'*22,title=title,
        description='歌唱 / Singer\nMy covers: https://youtube.com/playlist\n#cover #歌ってみた')
    assert purpose(video)==('cover' if expected else None)


def test_description_promotion_and_generic_vocal_credit_are_not_covers():
    for description in ['歌唱：花譜', 'cover', '#歌ってみた', 'Listen to my covers playlist']:
        video=Video(id='abcdefghijk',channel_id='UC'+'a'*22,title='Original MV',description=description)
        assert purpose(video) is None


def test_completed_cover_premiere_is_collected_but_active_and_singing_streams_are_not_covers():
    started=datetime(2022,8,4,11,0,13,tzinfo=UTC)
    video=Video(id='QOCmDcgPtYw',channel_id='UCPd0Z22gF43dUidPYEQO5-w',
        title='-ERROR - niki (Cover) / VESPERBELL ヨミ × HACHI',
        started_at=started,ended_at=started+timedelta(seconds=348),scheduled=True,duration_seconds=236)
    assert purpose(video)=='cover'
    assert purpose(video.model_copy(update={'ended_at':None})) is None
    assert purpose(video.model_copy(update={'title':'歌枠 cover singing'}))=='archive'
    assert purpose(video.model_copy(update={'title':'Cover songs live stream'})) is None
    assert purpose(video.model_copy(update={'title':'【3D】カバー同時視聴 #KMNZNERO'})) is None


def test_completed_premiere_schedule_is_not_still_upcoming():
    item=dict(id='QOCmDcgPtYw',snippet=dict(channelId='UCPd0Z22gF43dUidPYEQO5-w',title='-ERROR (Cover)',liveBroadcastContent='none'),
        liveStreamingDetails=dict(scheduledStartTime='2022-08-04T11:00:00Z',actualStartTime='2022-08-04T11:00:13Z',actualEndTime='2022-08-04T11:06:01Z'),
        contentDetails={'duration':'PT3M56S'})
    provider=YouTubeClient('fixture',interval=0,transport=httpx.MockTransport(lambda request:httpx.Response(200,json={'items':[item]})))
    video=asyncio.run(provider.videos(['QOCmDcgPtYw']))[0]
    assert not video.scheduled and purpose(video)=='cover'
