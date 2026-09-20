import pytest
from app.admin.db.local import LocalStore
from app.admin.db.remote import RemoteCatalog
from app.admin.services.review import ReviewService
from app.admin.services.platforms import PlatformService
from app.admin.schemas.contracts import EntityInput, PlatformRegistration
from app.admin.schemas.catalog import DomainError

@pytest.fixture
def setup(tmp_path):
    review = ReviewService(LocalStore(tmp_path / "workspace"), RemoteCatalog(""), tmp_path / "input")
    batch = review.create_batch("platform")
    review.create(batch["id"], EntityInput(client_ref="artist", entity_type="artists", data={"slug":"artist", "name_native":"Artist", "entity_kind":"solo"}))
    return review, PlatformService(review), batch["id"]

def request(batch, **kwargs):
    return PlatformRegistration.model_validate({
        "batch_id":batch,
        "account":{"client_ref":"account", "data":{"platform":"youtube", "url":"https://youtube.com/@artist", "collection_enabled":False}},
        "artists":[{"client_ref":"link", "data":{"artist_id":{"$ref":"artist"}, "relationship":"owner", "is_primary":True, "position":0}}],
        **kwargs,
    })

def edit_request(batch, group):
    def adapt(row):
        return {"id":row["id"], "revision":row["revision"], "client_ref":row["client_ref"], "data":row["current_payload"]}
    return request(batch, account=adapt(group["account"]), artists=[adapt(x) for x in group["artists"]])

def test_group_create_review_edit_invalidate(setup):
    review, service, batch = setup
    group = service.save(request(batch))
    assert group["artists"][0]["current_payload"]["account_id"] == {"$ref":"account"}
    for row in [group["account"], *group["artists"]]:
        review.review(row["id"], row["revision"], "approve")
    body = edit_request(batch, group)
    body.account.data["handle"] = "@changed"
    updated = service.save(body)
    assert updated["account"]["revision"] == 2
    assert updated["artists"][0]["status"] == "pending"
    assert service.detail(group["account"]["id"])["account"]["current_payload"]["handle"] == "@changed"

def test_invalid_link_rolls_back_account_and_revision(setup):
    review, service, batch = setup
    original = review.batches()[0]["revision"]
    body = request(batch)
    body.artists[0].data["relationship"] = "invalid"
    with pytest.raises(DomainError):
        service.save(body)
    assert review.page(batch, kind="external_accounts")["total"] == 0
    assert review.batches()[0]["revision"] == original

def test_duplicate_and_stale_link_rollback(setup):
    review, service, batch = setup
    body = request(batch)
    body.artists.append(body.artists[0].model_copy(deep=True))
    body.artists[-1].client_ref = "duplicate"
    with pytest.raises(DomainError, match="중복"):
        service.save(body)
    group = service.save(request(batch))
    body = edit_request(batch, group)
    body.account.data["handle"] = "@must-not-save"
    body.artists[0].revision = 99
    with pytest.raises(DomainError):
        service.save(body)
    assert service.detail(group["account"]["id"])["account"]["revision"] == 1

def test_existing_import_and_missing_link_guard(setup):
    review, service, batch = setup
    account = review.create(batch, EntityInput(client_ref="imported", entity_type="external_accounts", data={"platform":"x","url":"https://x.com/artist","collection_enabled":False}))
    review.create(batch, EntityInput(client_ref="imported-link", entity_type="artist_external_accounts", data={"account_id":{"$ref":"imported"},"artist_id":{"$ref":"artist"},"relationship":"owner","is_primary":False,"position":0}))
    group = service.detail(account["id"])
    assert len(group["artists"]) == 1
    body = edit_request(batch, group)
    body.artists = []
    with pytest.raises(DomainError, match="연결 목록"):
        service.save(body)

def test_existing_catalog_staging_is_local_and_repeatable(setup):
    review, service, batch = setup
    review.remote.platform_registration = lambda key: {
        "account":{"id":4,"_version":2,"platform":"youtube","platform_id":"channel","handle":"@artist","url":"https://youtube.com/@artist","collection_enabled":False},
        "artists":[{"id":8,"_version":3,"artist_id":2,"account_id":4,"relationship":"owner","is_primary":True,"label":None,"position":0}],
    }
    group = service.from_catalog(batch, 4)
    again = service.from_catalog(batch, 4)
    assert group["account"]["id"] == again["account"]["id"]
    assert group["account"]["target_id"] == 4
    assert group["artists"][0]["expected_version"] == 3
    assert group["artists"][0]["current_payload"]["account_id"] == {"$ref":"platform-account:4"}

def test_grouped_page_filter_search_and_pagination(setup):
    review, service, batch = setup
    group = service.save(request(batch))
    page = service.review_page(batch)
    assert page["total"] == 2  # Artist plus one logical registration, not three rows.
    assert service.review_counts(batch) == {"pending": 2}
    account = next(row for row in page["items"] if row.get("review_group"))
    assert account["member_count"] == 2
    artist_id = next(row["id"] for row in page["items"] if row["entity_type"] == "artists")
    assert service.next_review(artist_id)["item"]["review_group"] == "platform"
    assert service.review_page(batch, q="owner")["items"][0]["id"] == group["account"]["id"]
    assert service.review_page(batch, page=2, page_size=1)["items"][0]["id"] == group["account"]["id"]
    review.review(group["account"]["id"], 1, "approve")
    assert service.review_page(batch, status="pending")["total"] == 2
    assert service.review_page(batch, status="approved")["total"] == 0

def test_group_approval_atomic_and_next_skips_member(setup):
    from app.admin.schemas.contracts import PlatformReview
    review, service, batch = setup
    group = service.save(request(batch))
    members = [group["account"], *group["artists"]]
    body = PlatformReview(items=[{"id":r["id"],"revision":r["revision"]} for r in members], action="approve")
    link = group["artists"][0]
    review.edit(link["id"], 1, {**link["current_payload"], "relationship":"invalid"})
    body.items[1].revision = 2
    with pytest.raises(DomainError):
        service.review_group(group["account"]["id"], body)
    assert review.detail(group["account"]["id"])["status"] == "pending"
    review.edit(link["id"], 2, link["current_payload"])
    body.items[1].revision = 3
    service.review_group(group["account"]["id"], body)
    assert service.review_page(batch, status="approved")["total"] == 1
    last = review.create(batch, EntityInput(client_ref="last", entity_type="songs", data={"title_native":"Last"}))
    result = service.next_review(group["account"]["id"], page_size=1)
    assert result["item"]["id"] == last["id"]
    assert result["page"] == 3

def test_unresolved_link_is_not_hidden(setup):
    review, service, batch = setup
    orphan = review.create(batch, EntityInput(client_ref="unresolved", entity_type="artist_external_accounts",
        data={"account_id":{"$ref":"missing"}, "artist_id":{"$ref":"artist"}, "relationship":"owner", "is_primary":False, "position":0}))
    assert orphan["id"] in [row["id"] for row in service.review_page(batch)["items"]]
