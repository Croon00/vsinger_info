
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_catalog_migration import local_server, database, apply, row
from app.services.catalog_read import CatalogRead
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
        assert client.get("/api/v2/artists").status_code==401
        client.headers["X-API-Key"]="test"
        assert client.get("/api/v2/artists").json()==[]
        for path in ["/search?q=test","/concerts"]:
            res=client.get("/api/v2"+path)
            assert res.status_code==200, res.text
            assert res.json()["total"]==0
        for path in ["/artists/1","/lives/1","/albums/1","/recordings/1/lyrics"]:
            assert client.get("/api/v2"+path).status_code==404

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
        assert service.lives(guest,0,12)["items"][0]["artist_id"]==guest
        assert len(service.live(archive)["performances"])==2
        for query in ["제목","Nickname","Romanized"]:
            result=service.search(query,0,1)
            assert result["total"]==2
            assert result["items"][0]["original_artist"]=="Original"
            assert result["items"][0]["song_title_ko"]=="제목"
        assert service.search("%",0,50)["total"]==0
        assert service.search("Title",99,1)["total"]==2
        for artist in [a,guest]:
            stats=service.statistics(artist)
            assert stats["archives"]==1 and stats["performances"]==1
            assert stats["uniqueSongs"]==1 and stats["uniqueArtists"]==1
            assert stats["activity"]==[{"month":"2026-01","count":1}]
        events=service.concerts(0,100,guest,"2026-09-01","2026-10-01")
        assert events["items"][0]["artist_id"]==guest
        assert events["items"][0]["starts_at"]=="2026-09-20"
        assert set(events["items"][0]["artist_ids"])=={a,guest}
        assert service.concert(concert)["city"]=="Tokyo"
        assert service.albums(a)[0]["id"]==str(album)
        assert service.album(album)["release_date"]=="2026-09"
        assert service.album(album)["tracks"][0]["recording_id"]==recording
        assert service.album(album)["tracks"][0]["has_lyrics"] is True
        assert service.lyrics(recording)["original_lyrics"]=="Stored lyrics"

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
