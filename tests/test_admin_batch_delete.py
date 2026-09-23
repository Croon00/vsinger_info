import pytest
from app.admin.db.local import LocalStore
from app.admin.db.remote import RemoteCatalog
from app.admin.services.review import ReviewService
from app.admin.schemas.contracts import EntityInput, ImportEnvelope
from app.admin.schemas.catalog import DomainError

@pytest.fixture
def review(tmp_path):
    return ReviewService(LocalStore(tmp_path/"workspace"),RemoteCatalog(""),tmp_path/"input")

def revision(review,key):
    return next(b["revision"] for b in review.batches() if b["id"]==key)

def test_delete_imported_batch_preserves_files_and_other_batch(review):
    envelope=ImportEnvelope(schema_version="1",entities=[
        EntityInput(client_ref="a",entity_type="artists",data={"slug":"a","name_native":"A","entity_kind":"solo"}),
        EntityInput(client_ref="alias",entity_type="artist_aliases",data={"artist_id":{"$ref":"a"},"alias":"Name"})])
    source=review.input_dir/"input.json"
    source.write_text(envelope.model_dump_json(),encoding="utf-8")
    first=review.create_batch("delete")
    second=review.create_batch("keep")
    review.scan(first["id"])
    review.import_json(second["id"],"upload.json",envelope)
    item=review.page(first["id"])["items"][0]
    review.review(item["id"],1,"approve")
    review.delete_batch(first["id"],revision(review,first["id"]))
    assert [b["id"] for b in review.batches()]==[second["id"]]
    assert len(review.page(second["id"])["items"])==2
    assert source.exists()
    assert list((review.local.workspace/"snapshots").glob("*.json"))
    with review.local.connect() as c:
        assert not c.execute("PRAGMA foreign_key_check").fetchall()
        assert c.execute("SELECT count(*) FROM review_events").fetchone()[0]==0
    replacement=review.create_batch("again")
    assert review.scan(replacement["id"])["files"][0]["imported"]==2

def test_stale_revision_cannot_delete(review):
    batch=review.create_batch("stale")
    review.create(batch["id"],EntityInput(client_ref="a",entity_type="songs",data={"title_native":"A"}))
    with pytest.raises(DomainError) as error:
        review.delete_batch(batch["id"],batch["revision"])
    assert error.value.status==409
    assert len(review.batches())==1

def test_unconfirmed_publication_cannot_delete(review):
    batch=review.create_batch("publishing")
    with review.local.connect(write=True) as c:
        review.local.insert(c,"publish_plans",batch_id=batch["id"],operation_id="operation",
            target_catalog_id="catalog",expected_schema_version="catalog-v1",manifest_payload="{}",
            manifest_hash="hash",status="publishing",frozen_at="now")
    with pytest.raises(DomainError) as error:
        review.delete_batch(batch["id"],revision(review,batch["id"]))
    assert error.value.status==409

def test_delete_published_local_records_does_not_call_remote(review):
    batch=review.create_batch("published")
    draft=review.create(batch["id"],EntityInput(client_ref="s",entity_type="songs",data={"title_native":"Song"}))
    with review.local.connect(write=True) as c:
        review.local.update(c,"import_batches",batch["id"],status="published")
        plan=review.local.insert(c,"publish_plans",batch_id=batch["id"],operation_id="op",
            target_catalog_id="catalog",expected_schema_version="catalog-v1",manifest_payload="{}",
            manifest_hash="hash",status="committed",frozen_at="now")
        review.local.insert(c,"publish_attempts",plan_id=plan,attempt_number=1,state="committed",started_at="now")
        review.local.insert(c,"remote_id_map",draft_id=draft["id"],target_catalog_id="catalog",
            entity_type="songs",entity_id=123,operation_id="op",mapped_at="now")
    review.delete_batch(batch["id"],revision(review,batch["id"]))
    with review.local.connect() as c:
        for table in ("publish_plans","publish_attempts","remote_id_map","draft_entities","import_batches"):
            assert c.execute("SELECT count(*) FROM "+table).fetchone()[0]==0

def test_next_pending_skips_reviewed_and_respects_search_and_pages(review):
    batch=review.create_batch("next")
    items=[]
    for n in range(33):
        items.append(review.create(batch["id"],EntityInput(client_ref=str(n),entity_type="songs",data={"title_native":f"Song {n}"})))
    for d in items[1:31]:
        review.review(d["id"],1,"hold","later")
    following=review.next_pending(items[0]["id"])
    assert following["item"]["id"]==items[31]["id"]
    assert following["page"]==2
    assert review.next_pending(items[0]["id"],status="pending")["page"]==1
    assert review.next_pending(items[0]["id"],q="Song 32")["item"]["id"]==items[32]["id"]
    assert review.next_pending(items[32]["id"])["item"] is None
