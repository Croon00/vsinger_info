import pytest
from app.services.recording_youtube_match import choose,title_matches


@pytest.mark.parametrize('title,video,expected',[
    ('イニミニまいご','【MV】イニミニまいご / Artist',True),
    ('Song','Artist - Song (Official Music Video)',True),
    ('Song','【歌ってみた】「Song」 / Artist',True),
    ('Song','Songs / Artist',False),
    ('AI','Kai / Artist',False),
    ('Song - Instrumental','Song / Artist',False),
    ('Song','Song - Instrumental / Artist',False),
    ('Song','Song (Acoustic ver.) / Artist',False),
    ('Song','Song (Remix) / Artist',False),
    ('Song','Song (Short ver.) / Artist',False),
    ('Song','Song (Piano ver.) / Artist',False),
    ('Song','【弾き語り】Song / Artist',False),
    ('Song','Other Song / Artist',False),
    ('Song feat.Guest','Song / Artist feat.Guest (Official)',True),
    ('Song feat.Guest','Song / Artist',False),
    ('Song feat.Guest','Song / Artist feat.Other',False),
    ('Song feat.Guest,Another','Song / Artist feat.Guest & Another',True),
    ('Song feat.Guest (Rearrange ver.)','Song / Artist feat.Guest',False),
])
def test_title_and_versions(title,video,expected):
    assert title_matches(title,video,['Artist']) is expected


def sample(**overrides):
    return dict(dict(id='abcdefghijk',channel_id='owned',title='Song',duration_seconds=180,
                availability='public'),**overrides)


def recording():
    return dict(title_native='Song',channels={'owned':1},aliases=['Artist'],duration_ms=180000)


def test_identity_duration_availability_and_live_are_required():
    for key,value in [('channel_id','other'),('duration_seconds',60),('availability','private'),
                      ('started_at','2026-10-11'),('scheduled',True)]:
        video=sample();video[key]=value
        assert choose(recording(),[video])['status']=='unresolved'
    assert choose(recording(),[sample()])['status']=='matched'


def test_unique_mv_wins_over_audio_but_two_mvs_wait():
    mv=sample();mv.update(id='mv123456789',title='Song Official Music Video')
    assert choose(recording(),[sample(),mv])['video']['id']==mv['id']
    other=dict(mv,id='mv987654321')
    assert choose(recording(),[mv,other])['reason']=='multiple_verified_candidates'


def test_stream_or_reaction_with_quoted_song_is_not_a_song_upload():
    for suffix in ['歌枠','切り抜き','reaction','XFD','teaser']:
        assert choose(recording(),[sample(title='"Song" '+suffix)])['status']=='unresolved'


def test_completed_mv_premiere_is_not_an_ongoing_broadcast():
    video=sample(title='Song Official Music Video',started_at='2026-10-11',ended_at='2026-10-11',scheduled=True)
    assert choose(recording(),[video])['status']=='matched'
    video['title']='Song'
    assert choose(recording(),[video])['status']=='unresolved'


def test_live_album_does_not_link_to_a_studio_mv_with_the_same_title():
    track=recording();track['albums']=['Live Album 2026']
    assert choose(track,[sample()])['reason']=='live_release_requires_version_review'


@pytest.mark.parametrize('title',['Song / Artist (Original)','Artist「Song」【オリジナルMV】'])
def test_completed_original_song_premiere_with_japanese_mv_label(title):
    video=sample(title=title,started_at='2026-10-11',ended_at='2026-10-11',scheduled=True)
    assert choose(recording(),[video])['status']=='matched'
