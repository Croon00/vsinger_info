
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_catalog_migration import local_server, database, apply, row
from app.services.catalog_read import CatalogRead
from app.schemas.read_models import Page, SearchRead
from app.db.catalog_session import get_catalog_session
from app.api.routers.read_api import router
from app.core.config import settings

@pytest.fixture
def store(database):
    apply(database)
    info = database.info
    engine = create_engine(f"postgresql+psycopg://catalog_test@127.0.0.1:{info.port}/{info.dbname}")
    yield database, engine
    engine.dispose()

def seed(db):
    a = row(db, "artists", entity_kind="solo", slug="singer", name_native="Singer", name_ko="가창자", show_in_catalog=True, birthday_month=9, birthday_day=20)
    other = row(db, "artists", entity_kind="solo", slug="guest", name_native="Guest", show_in_catalog=True)
    original = row(db, "artists", entity_kind="solo", slug="original", name_native="Original", name_ko="원곡자", show_in_catalog=False)
    row(db, "artist_aliases", artist_id=original, alias="Nickname", normalized_alias="nickname")
    acc = row(db, "external_accounts", platform="youtube", url="https://youtube.com/@singer", collection_enabled=False)
    row(db, "artist_external_accounts", artist_id=a, account_id=acc, relationship="owner")
    song = row(db, "songs", title_native="Title", title_ko="제목", title_latin="Romanized")
    row(db, "song_artists", song_id=song, artist_id=original)
    video = row(db, "videos", platform="youtube", platform_video_id="abcdefghijk", title="Archive", published_at="2026-01-10T20:00:00+09:00")
    archive = row(db, "live_archives", video_id=video)
    for artist in [a, other]:
        row(db, "archive_artists", archive_id=archive, artist_id=artist, role="host" if artist==a else "guest")
    db.execute("UPDATE live_archives SET primary_artist_id=%s WHERE id=%s",(a,archive))
    for n,artist in enumerate([a,other],1):
        perf = row(db, "performances", archive_id=archive, ordinal=n, song_id=song, start_seconds=n*30, raw_title="raw")
        row(db, "performance_artists", performance_id=perf, artist_id=artist, role="lead")
    concert = row(db,"concerts",title="Concert",status="scheduled",event_format="onsite",event_date="2026-09-20",time_precision="date",city="Tokyo",venue="Hall")
    for artist in [a,other]:
        row(db,"concert_artists",concert_id=concert,artist_id=artist)
    row(db,"concert_ticket_windows",concert_id=concert,label="Ticket",url="https://example.com/ticket",price_text="100")
    album = row(db,"albums",title_native="Album",album_type="ep",release_year=2026,release_month=9)
    row(db,"album_artists",album_id=album,artist_id=a)
    recording = row(db,"recordings",song_id=song,title_native="Title",title_ko="제목")
    row(db,"recording_artists",recording_id=recording,artist_id=a,role="primary")
    row(db,"album_tracks",album_id=album,recording_id=recording,disc_number=1,track_number=1)
    row(db,"recording_lyrics",recording_id=recording,original_lyrics="Stored lyrics")
    db.commit()
    return a,other,original,archive,concert,album,recording

def test_empty_catalog_and_missing_resources(store, monkeypatch):
    db,engine = store
    app = FastAPI()
    app.include_router(router,prefix="/api")
    monkeypatch.setattr(settings,"api_key","test")
    def session():
        with Session(engine) as s:
            s.execute(text("SET TRANSACTION READ ONLY"))
            yield s
    app.dependency_overrides[get_catalog_session] = session
    with TestClient(app) as client:
        assert client.get("/api/artists").status_code==401
        client.headers["X-API-Key"]="test"
        assert client.get("/api/artists").json()==[]
        for path in ["/search?q=test","/concerts"]:
            res=client.get("/api"+path)
            assert res.status_code==200, res.text
            assert res.json()["total"]==0
        for path in ["/artists/1","/lives/1","/albums/1","/recordings/1/lyrics"]:
            assert client.get("/api"+path).status_code==404

def test_normalized_catalog_reads_and_attribution(store):
    db,engine = store
    a,guest,original,archive,concert,album,recording = seed(db)
    with Session(engine) as session:
        session.execute(text("SET TRANSACTION READ ONLY"))
        service=CatalogRead(session)
        assert len(service.artists())==2
        assert service.artist(a)["display_name"]=="가창자"
        assert service.artist(a)["birthday"]=="09-20"
        assert service.artist(a)["sources"][0]["value"]=="https://youtube.com/@singer"
        assert service.artist(original) is None
        summary=service.lives(guest,0,12)["items"][0]
        assert summary["artist_id"]==guest
        assert summary["performance_count"]==2
        assert "performances" not in summary
        assert len(service.live(archive)["performances"])==2
        for query in ["제목","Nickname","Romanized"]:
            result=service.search(query,0,1)
            assert result["total"]==2
            assert result["items"][0]["original_artist"]=="Original"
            assert result["items"][0]["song_title_ko"]=="제목"
        assert service.search("가창자",0,50)["total"]==2
        assert service.search("Guest",0,50)["total"]==1
        assert service.search("%",0,50)["total"]==0
        assert service.search("Title",99,1)["total"]==2
        for artist in [a,guest]:
            stats=service.statistics(artist)
            assert stats["archives"]==1 and stats["performances"]==1
            assert stats["uniqueSongs"]==1 and stats["uniqueArtists"]==1
            assert stats["songs"][0]["titleKo"]=="제목"
            assert stats["songs"][0]["artistKo"]=="원곡자"
            assert stats["artists"][0]["nameKo"]=="원곡자"
            assert stats["activity"]==[{"month":"2026-01","count":1}]
        events=service.concerts(0,100,guest,"2026-09-01","2026-10-01")
        assert events["items"][0]["artist_id"]==guest
        assert events["items"][0]["starts_at"]=="2026-09-20"
        assert set(events["items"][0]["artist_ids"])=={a,guest}
        assert service.concert(concert)["city"]=="Tokyo"
        assert service.albums(a)[0]["id"]==str(album)
        assert service.albums(a)[0]["is_primary"] is True
        assert service.album(album)["is_primary"] is None
        assert service.album(album)["release_date"]=="2026-09"
        assert service.album(album)["tracks"][0]["recording_id"]==recording
        assert service.album(album)["tracks"][0]["has_lyrics"] is True
        assert service.lyrics(recording)["original_lyrics"]=="Stored lyrics"

def test_unmatched_raw_original_artist_is_searchable_by_registered_names(store):
    db,engine=store
    original=row(db,"artists",entity_kind="group",slug="yorushika",name_native="ヨルシカ",
                 name_ko="요루시카",name_latin="Yorushika",show_in_catalog=False)
    row(db,"artist_aliases",artist_id=original,alias="Yoru",normalized_alias="yoru")
    video=row(db,"videos",platform="youtube",platform_video_id="rawartist01",title="Archive",
              published_at="2026-01-10T20:00:00+09:00")
    archive=row(db,"live_archives",video_id=video)
    performance=row(db,"performances",archive_id=archive,ordinal=1,raw_title="晴る",
                    raw_artist="ヨルシカ",start_seconds=30)
    alias_performance=row(db,"performances",archive_id=archive,ordinal=2,raw_title="別の曲",
                          raw_artist="Yoru",start_seconds=90)
    db.commit()
    with Session(engine) as session:
        session.execute(text("SET TRANSACTION READ ONLY"))
        service=CatalogRead(session)
        for query in ("요루시카","Yorushika","Yoru"):
            result=service.search(query,0,50)
            assert result["total"]==2
            assert result["items"][0]["id"]==performance
            assert result["items"][0]["song_id"] is None
            assert result["items"][0]["original_artist"]=="ヨルシカ"
            Page[SearchRead].model_validate(result)
        second=service.search("요루시카",1,1)
        assert second["total"]==2
        assert second["items"][0]["id"]==alias_performance
        assert service.search("unrelated",0,50)["total"]==0

def test_archived_private_and_undated_data(store):
    db,engine=store
    a,guest,original,archive,concert,album,recording=seed(db)
    db.execute("UPDATE videos SET availability='private'")
    db.execute("UPDATE albums SET archived_at=now()")
    db.execute("UPDATE concerts SET event_date=NULL,time_precision='unknown'")
    db.commit()
    with Session(engine) as s:
        service=CatalogRead(s)
        assert service.live(archive) is None
        assert service.search("Title",0,50)["total"]==0
        assert service.statistics(a)["archives"]==0
        assert service.album(album) is None
        assert service.concert(concert)["starts_at"]==""
        assert service.concerts(0,100,None,"2026-09-01","2026-10-01")["total"]==0


def seed_song_aliases(db, song_id):
    for alias in ("요나가우타", "요나가우타(읽기)", "영원한 밤의 노래", "Yonagauta"):
        row(db, "song_aliases", song_id=song_id, alias=alias, normalized_alias=alias.casefold(),
            locale="ko" if alias != "Yonagauta" else "en", source="manual")
    db.commit()


def test_song_alias_search_is_partial_deduplicated_paged_and_id_based(store, monkeypatch):
    db, engine = store
    singer, _, _, archive, _, _, _ = seed(db)
    song_id = db.execute('SELECT song_id FROM performances WHERE archive_id=%s ORDER BY ordinal LIMIT 1', (archive,)).fetchone()[0]
    seed_song_aliases(db, song_id)
    # Equal titles do not transfer aliases to unlinked or distinct songs.
    other_song = row(db, "songs", title_native="Title")
    for ordinal, linked_song in ((3, None), (4, other_song)):
        perf = row(db, "performances", archive_id=archive, ordinal=ordinal, song_id=linked_song,
                   raw_title="Title", raw_artist="Original", start_seconds=ordinal*30)
        row(db, "performance_artists", performance_id=perf, artist_id=singer, role="lead")
    db.commit()
    with Session(engine) as session:
        session.execute(text("SET TRANSACTION READ ONLY"))
        service = CatalogRead(session)
        for query in ("요나가우타", "나가", "영원한 밤의 노래", "밤의", "yonagauta"):
            first = service.search(query, 0, 1)
            second = service.search(query, 1, 1)
            beyond = service.search(query, 99, 1)
            assert first['total'] == second['total'] == beyond['total'] == 2
            assert first['items'][0]['ordinal'] == 1 and second['items'][0]['ordinal'] == 2
            assert first['items'][0]['id'] != second['items'][0]['id']
            assert first['items'][0]['song_id'] == song_id
            assert first['items'][0]['song_title'] == 'Title'
            assert beyond['items'] == []
            Page[SearchRead].model_validate(first)
        assert service.search('Title', 0, 50)['total'] == 4

    app = FastAPI()
    app.include_router(router, prefix='/api')
    monkeypatch.setattr(settings, 'api_key', 'test')
    def readonly_session():
        with Session(engine) as session:
            session.execute(text('SET TRANSACTION READ ONLY'))
            yield session
    app.dependency_overrides[get_catalog_session] = readonly_session
    with TestClient(app, headers={'X-API-Key': 'test'}) as client:
        response = client.get('/api/search', params={'q': '나가', 'limit': 1})
        assert response.status_code == 200
        assert response.json()['total'] == 2
        assert 'queries;desc="1"' in response.headers['Server-Timing']
        stats = client.get(f'/api/artists/{singer}/statistics').json()
        matched = [s for s in stats['songs'] if '요나가우타' in s['searchText']]
        assert len(matched) == 1 and matched[0]['key'] == f'song:{song_id}'
        assert stats['performances'] == 3 and stats['uniqueSongs'] == 3


@pytest.mark.parametrize('hidden', ['private', 'deleted', 'archive', 'performance', 'song'])
def test_song_alias_search_respects_visibility_and_archived_song_fallback(store, hidden):
    db, engine = store
    singer, _, _, archive, _, _, _ = seed(db)
    song_id = db.execute('SELECT song_id FROM performances WHERE archive_id=%s LIMIT 1', (archive,)).fetchone()[0]
    seed_song_aliases(db, song_id)
    if hidden in ('private', 'deleted'):
        db.execute('UPDATE videos SET availability=%s', (hidden,))
    elif hidden == 'archive':
        db.execute('UPDATE live_archives SET archived_at=now()')
    elif hidden == 'performance':
        db.execute('UPDATE performances SET archived_at=now()')
    else:
        db.execute('UPDATE songs SET archived_at=now()')
    db.commit()
    with Session(engine) as session:
        session.execute(text('SET TRANSACTION READ ONLY'))
        service = CatalogRead(session)
        assert service.search('요나가우타', 0, 50)['total'] == 0
        songs = service.statistics(singer)['songs']
        assert all('요나가우타' not in song['searchText'] for song in songs)


def test_statistics_adds_aliases_without_changing_counts_or_rank(store):
    db, engine = store
    singer, guest, _, archive, _, _, _ = seed(db)
    song_id = db.execute('SELECT song_id FROM performances WHERE archive_id=%s LIMIT 1', (archive,)).fetchone()[0]
    with Session(engine) as session:
        before = CatalogRead(session).statistics(singer)
    seed_song_aliases(db, song_id)
    with Session(engine) as session:
        session.execute(text('SET TRANSACTION READ ONLY'))
        service = CatalogRead(session)
        after = service.statistics(singer)
        assert service.query_count == 2
        for alias in ('요나가우타', '영원한 밤의 노래', 'Yonagauta'):
            assert alias in after['songs'][0]['searchText']
            assert after['songs'][0]['searchText'].count(alias) == (2 if alias == '요나가우타' else 1)
        after['songs'][0]['searchText'] = before['songs'][0]['searchText']
        assert after == before
        assert '요나가우타' in service.statistics(guest)['songs'][0]['searchText']


def test_song_alias_search_escapes_like_metacharacters(store):
    db, engine = store
    _, _, _, archive, _, _, _ = seed(db)
    song_id = db.execute('SELECT song_id FROM performances WHERE archive_id=%s LIMIT 1', (archive,)).fetchone()[0]
    alias = '100%_literal\\alias'
    row(db, 'song_aliases', song_id=song_id, alias=alias, normalized_alias=alias, source='manual')
    db.commit()
    with Session(engine) as session:
        session.execute(text('SET TRANSACTION READ ONLY'))
        service = CatalogRead(session)
        for query in (alias, '%', '_', '\\'):
            assert service.search(query, 0, 50)['total'] == 2
        assert service.search('100xxx', 0, 50)['total'] == 0
