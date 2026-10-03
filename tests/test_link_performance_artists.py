"""Explicit singer credits on disposable local PostgreSQL; no external calls."""
import importlib.util
import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.core.config import settings
from scripts.link_performance_artists import Manifest, apply_bucket
from test_catalog_migration import local_server, database, apply as apply_schema, row, artist  # noqa: F401

ROOT=Path(__file__).resolve().parents[1]


def setup(database,monkeypatch):
    schema=apply_schema(database)
    monkeypatch.setattr(settings,'new_database_instance_id',schema['catalog_instance_id'])
    singer=artist(database,'singer',show_in_catalog=True)
    guest=artist(database,'guest',show_in_catalog=True)
    channel='UC'+'a'*22
    account=row(database,'external_accounts',platform='youtube',platform_id=channel,url='https://www.youtube.com/channel/'+channel)
    row(database,'artist_external_accounts',artist_id=singer,account_id=account,relationship='owner')
    title='【歌枠】Test artist'
    video=row(database,'videos',platform='youtube',platform_video_id='aaaaaaaaaaa',source_account_id=account,title=title,availability='public')
    arc=row(database,'live_archives',video_id=video,primary_artist_id=singer,setlist_state='partial')
    row(database,'archive_artists',archive_id=arc,artist_id=singer,role='host')
    source='00:05 Song / Original'
    url='https://www.youtube.com/watch?v=aaaaaaaaaaa&lc=comment'
    doc=row(database,'source_documents',source_kind='youtube_comment',source_url=url,content_text=source,content_hash='a'*64)
    perf=row(database,'performances',archive_id=arc,ordinal=1,start_seconds=5,raw_title='Song / Original',source_document_id=doc)
    arc_version=database.execute('SELECT version FROM live_archives WHERE id=%s',(arc,)).fetchone()[0]
    manifest=Manifest.model_validate({'policy':'fixture-source-attribution','catalog_instance_id':schema['catalog_instance_id'],
        'snapshot_at':'2026-10-04T00:00:00+09:00','links':[{'performance_id':perf,'performance_version':1,'archive_id':arc,'archive_version':arc_version,
        'video_id':video,'video_version':1,'source_account_id':account,'channel_id':channel,'source_document_id':doc,'source_hash':'a'*64,
        'artists':[{'artist_id':singer,'role':'lead','position':0}],
        'evidence':{'basis':'publisher_title_names_singer','song_basis':'setlist_title_and_original_credit','review_status':'contextual',
        'source_url':url,'video_title':title,'source_line':source}}]})
    database.commit()
    engine=create_engine(f'postgresql+psycopg://{database.info.user}@127.0.0.1:{database.info.port}/{database.info.dbname}',poolclass=NullPool)
    return manifest,engine,guest


def test_dry_run_apply_and_retry_preserve_source_and_audit(database,monkeypatch):
    manifest,engine,_=setup(database,monkeypatch)
    with Session(engine) as s:
        s.execute(text('SET TRANSACTION READ ONLY'))
        result=apply_bucket(s,manifest,manifest.links,write=False)
        assert result['planned_links']==1
        assert s.execute(text('SELECT count(*) FROM performance_artists')).scalar()==0
        assert s.execute(text('SELECT count(*) FROM catalog_imports')).scalar()==0
    with Session(engine) as s,s.begin():
        result=apply_bucket(s,manifest,manifest.links,write=True)
        assert result['inserted']==1
    with Session(engine) as s,s.begin():
        assert apply_bucket(s,manifest,manifest.links,write=True)['status']=='already_committed'
        assert s.execute(text('SELECT count(*) FROM performance_artists')).scalar()==1
        audit=s.execute(text('SELECT after_data,provenance FROM catalog_changes')).one()
        assert audit.provenance['source_document_id']==manifest.links[0].source_document_id
        assert audit.provenance['review_status']=='contextual'
        assert s.execute(text('SELECT raw_title FROM performances')).scalar()=='Song / Original'
        assert s.execute(text('SELECT content_text FROM source_documents')).scalar()=='00:05 Song / Original'
    engine.dispose()


def test_existing_guest_is_not_overwritten_and_changed_row_is_skipped(database,monkeypatch):
    manifest,engine,guest=setup(database,monkeypatch)
    entry=manifest.links[0]
    row(database,'performance_artists',performance_id=entry.performance_id,artist_id=guest,role='lead')
    other=row(database,'performances',archive_id=entry.archive_id,ordinal=2,start_seconds=6,raw_title='Another song',source_document_id=entry.source_document_id)
    # A reviewed row changed between planning and apply.
    database.execute('UPDATE performances SET raw_title=%s WHERE id=%s',('Corrected song',other))
    database.commit()
    stale=entry.model_copy(update={'performance_id':other})
    with Session(engine) as s,s.begin():
        result=apply_bucket(s,manifest,[entry,stale],write=True)
        assert result['inserted']==0
        assert result['skipped']=={'existing_credit':1,'changed_or_invalid_evidence':1}
        assert s.execute(text('SELECT artist_id FROM performance_artists')).scalar()==guest
        assert s.execute(text('SELECT count(*) FROM catalog_changes')).scalar()==0
    engine.dispose()


def test_changed_source_and_owner_are_rejected(database,monkeypatch):
    manifest,engine,guest=setup(database,monkeypatch)
    entry=manifest.links[0]
    # Source documents are append-only. A wrong snapshot hash must still be refused.
    entry=entry.model_copy(update={'source_hash':'b'*64})
    row(database,'artist_external_accounts',artist_id=guest,account_id=entry.source_account_id,relationship='owner')
    database.commit()
    with Session(engine) as s,s.begin():
        result=apply_bucket(s,manifest,[entry],write=True)
        assert result['inserted']==0
        assert result['conflicts']==[entry.performance_id]
        assert s.execute(text('SELECT count(*) FROM performance_artists')).scalar()==0
    engine.dispose()


def test_audit_failure_rolls_back_credit_and_receipt(database,monkeypatch):
    manifest,engine,_=setup(database,monkeypatch)
    database.execute("""CREATE FUNCTION reject_singer_audit() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'injected audit failure'; END $$""")
    database.execute('CREATE TRIGGER reject_singer_audit BEFORE INSERT ON catalog_changes FOR EACH ROW EXECUTE FUNCTION reject_singer_audit()')
    database.commit()
    with pytest.raises(Exception):
        with Session(engine) as s,s.begin():
            apply_bucket(s,manifest,manifest.links,write=True)
    with Session(engine) as s:
        assert s.execute(text('SELECT count(*) FROM performance_artists')).scalar()==0
        assert s.execute(text('SELECT count(*) FROM catalog_imports')).scalar()==0
    engine.dispose()


def test_explicit_duet_adds_both_singers_without_host_inference(database,monkeypatch):
    manifest,engine,guest=setup(database,monkeypatch)
    entry=manifest.links[0]
    from scripts.link_performance_artists import Credit
    duet=entry.model_copy(update={'artists':entry.artists+[Credit(artist_id=guest,role='guest',position=1)],
                                  'evidence':entry.evidence.model_copy(update={'review_status':'source_row_verified','basis':'comment_explicit_per_song_credit'})})
    with Session(engine) as s,s.begin():
        assert apply_bucket(s,manifest,[duet],write=True)['inserted']==2
        assert s.execute(text('SELECT count(*) FROM catalog_changes')).scalar()==2
    engine.dispose()
