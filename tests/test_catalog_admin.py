"""Admin tests run ONLY on isolated local PostgreSQL and temporary SQLite."""

import asyncio
import json
import uuid
import zipfile
import httpx
import pytest
from sqlalchemy import text
from test_catalog_migration import local_server, database, apply
from app.admin.config import AdminSettings
from app.admin.db.local import LocalStore
from app.admin.db.remote import RemoteCatalog
from app.admin.services.review import ReviewService
from app.admin.schemas.catalog import DomainError, validate
from app.admin.schemas.contracts import (
    EntityInput,
    ImportEnvelope,
    ManualSave,
    ArchiveRequest,
)
from app.admin.main import create_app


@pytest.fixture
def remote(database):
    apply(database)
    info = database.info
    catalog = RemoteCatalog(
        f"postgresql://catalog_test@127.0.0.1:{info.port}/{info.dbname}"
    )
    yield catalog
    catalog.engine.dispose()


@pytest.fixture
def review(tmp_path, remote):
    return ReviewService(LocalStore(tmp_path / "workspace"), remote, tmp_path / "input")


def entity(ref="artist:a", kind="artists", data=None, **extra):
    return EntityInput(
        client_ref=ref,
        entity_type=kind,
        data=data or {"slug": "test-a", "name_native": "Test", "entity_kind": "solo"},
        **extra,
    )


def initial(review):
    batch = review.create_batch("Initial test")
    draft = review.create(batch["id"], entity())
    review.review(draft["id"], draft["revision"], "approve")
    plan = review.preview(batch["id"])
    result = review.publish(
        plan["manifest_id"], plan["manifest_hash"], plan["operation_id"]
    )
    return batch, draft, plan, result


def count(remote, table):
    with remote.session() as s:
        return s.execute(text("SELECT count(*) FROM " + table)).scalar_one()


def test_review_is_local_until_explicit_publish(review, remote):
    batch = review.create_batch("Initial")
    draft = review.create(batch["id"], entity())
    with pytest.raises(DomainError):
        review.preview(batch["id"])
    assert count(remote, "artists") == 0
    review.review(draft["id"], 1, "approve")
    plan = review.preview(batch["id"])
    assert count(remote, "artists") == 0
    first = review.publish(
        plan["manifest_id"], plan["manifest_hash"], plan["operation_id"]
    )
    second = review.publish(
        plan["manifest_id"], plan["manifest_hash"], plan["operation_id"]
    )
    assert first["committed"] and second["committed"]
    assert count(remote, "artists") == 1 and count(remote, "catalog_imports") == 1
    assert remote.connection()["initialized"]


def test_edit_invalidates_dependants_and_revision_conflicts(review):
    batch = review.create_batch("relations")
    a = review.create(batch["id"], entity())
    b = review.create(
        batch["id"],
        entity(
            "alias:a",
            "artist_aliases",
            {"artist_id": {"$ref": "artist:a"}, "alias": "Another"},
        ),
    )
    for d in (a, b):
        review.review(d["id"], 1, "approve")
    review.edit(
        a["id"], 1, {"slug": "test-a", "name_native": "Changed", "entity_kind": "solo"}
    )
    assert review.detail(b["id"])["status"] == "pending"
    with pytest.raises(DomainError):
        review.edit(a["id"], 1, {})
    with pytest.raises(DomainError):
        review.preview(batch["id"])


def test_import_snapshot_dedup_export_backup(review):
    batch = review.create_batch("file")
    envelope = ImportEnvelope(schema_version="1", entities=[entity()])
    assert review.import_json(batch["id"], "one.json", envelope)["imported"] == 1
    assert review.import_json(batch["id"], "one.json", envelope)["duplicate"]
    with pytest.raises(DomainError):
        review.import_json(batch["id"], "../one.json", envelope)
    assert review.export(batch["id"])["entities"][0]["data"]["name_native"] == "Test"
    with zipfile.ZipFile(review.backup()) as z:
        assert "review.sqlite3" in z.namelist()
        assert len([p for p in z.namelist() if p.startswith("snapshots/")]) == 1


def test_all_or_nothing_and_initial_guard(review, remote):
    state = remote.connection()
    req = ManualSave(
        operation_id=uuid.uuid4(), catalog_id=state["catalog_id"], entity=entity()
    )
    with pytest.raises(DomainError):
        remote.manual_save(req)
    batch = review.create_batch("duplicate")
    for ref in ("a", "b"):
        d = review.create(batch["id"], entity(ref))
        review.review(d["id"], 1, "approve")
    plan = review.preview(batch["id"])
    with pytest.raises(DomainError):
        review.publish(plan["manifest_id"], plan["manifest_hash"], plan["operation_id"])
    assert count(remote, "artists") == 0 and count(remote, "catalog_imports") == 0
    assert not remote.connection()["initialized"]


def test_unknown_commit_recovery(review, remote, monkeypatch):
    actual = remote.publish

    def lose_response(*args):
        actual(*args)
        raise DomainError("response lost", 503)

    batch = review.create_batch("recovery")
    d = review.create(batch["id"], entity())
    review.review(d["id"], 1, "approve")
    plan = review.preview(batch["id"])
    monkeypatch.setattr(remote, "publish", lose_response)
    with pytest.raises(DomainError):
        review.publish(plan["manifest_id"], plan["manifest_hash"], plan["operation_id"])
    with pytest.raises(DomainError):
        review.edit(d["id"], 1, {})
    assert review.recover(plan["operation_id"])["committed"]
    assert review.detail(d["id"])["status"] == "published"
    assert count(remote, "artists") == 1


def test_manual_update_conflict_archive_and_retry(review, remote):
    _, _, _, result = initial(review)
    row = remote.detail("artists", result["receipt"]["result_mapping"][0]["entity_id"])
    req = ManualSave(
        operation_id=uuid.uuid4(),
        catalog_id=remote.connection()["catalog_id"],
        entity=entity(
            "edit",
            operation="update",
            target_id=row["id"],
            expected_version=row["_version"],
            data={"name_native": "Updated"},
        ),
    )
    first = remote.manual_save(req)
    second = remote.manual_save(req)
    assert first["id"] == second["id"]
    assert remote.detail("artists", row["id"])["name_native"] == "Updated"
    req.operation_id = uuid.uuid4()
    with pytest.raises(DomainError):
        remote.manual_save(req)
    row = remote.detail("artists", row["id"])
    request = ArchiveRequest(
        operation_id=uuid.uuid4(),
        catalog_id=remote.connection()["catalog_id"],
        expected_version=row["_version"],
        archived=True,
    )
    a = remote.archive("artists", row["id"], request)
    assert remote.archive("artists", row["id"], request)["id"] == a["id"]
    assert remote.detail("artists", row["id"])["archived_at"]


def test_validation_rejects_bad_dates_and_fields():
    for kind, data in [
        (
            "artists",
            {
                "slug": "a",
                "name_native": "A",
                "entity_kind": "solo",
                "birthday_month": 2,
                "birthday_day": 30,
            },
        ),
        ("artists", {"slug": "a", "name_native": "A", "entity_kind": "solo", "id": 7}),
        (
            "albums",
            {
                "title_native": "A",
                "album_type": "album",
                "release_year": 2026,
                "release_month": 0,
            },
        ),
        ("videos", {"platform": "youtube", "platform_video_id": "bad", "title": "A"}),
    ]:
        with pytest.raises(DomainError):
            validate(kind, data)


def test_local_api_security_and_session(tmp_path):
    settings = AdminSettings(
        workspace=tmp_path / "work",
        input_dir=tmp_path / "input",
        dist=tmp_path / "dist",
    )
    app = create_app(settings)

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 1234)),
            base_url="http://127.0.0.1:8010",
        ) as c:
            assert (await c.get("/api/admin/metadata")).status_code == 401
            response = await c.get("/api/admin/session")
            assert (
                response.status_code == 200
                and "HttpOnly" in response.headers["set-cookie"]
            )
            csrf = response.json()["csrf"]
            assert (await c.get("/api/admin/metadata")).status_code == 200
            assert (
                await c.post("/api/admin/batches", json={"name": "A"})
            ).status_code == 403
            assert (
                await c.post(
                    "/api/admin/batches",
                    json={"name": "A"},
                    headers={"Origin": "https://evil.example", "X-CSRF-Token": csrf},
                )
            ).status_code == 403
            assert (
                await c.get("/api/admin/session", headers={"Host": "evil.example"})
            ).status_code == 403
            good = {"Origin": "http://127.0.0.1:8010", "X-CSRF-Token": csrf}
            r = await c.post(
                "/api/admin/batches", json={"name": "Local batch"}, headers=good
            )
            assert r.status_code == 200, r.text
            assert (await c.get("/api/admin/connection")).json()["connected"] is False
            assert (
                await c.post(
                    "/api/admin/imports",
                    json={"sql": "DROP TABLE artists"},
                    headers=good,
                )
            ).status_code == 422

    asyncio.run(run())


def test_all_28_resource_types_and_linked_search(review, remote):
    ref = lambda name: {"$ref": name}
    data = {
        "agencies": {"name_native": "Agency"},
        "artists": {
            "slug": "artist",
            "name_native": "Artist",
            "entity_kind": "solo",
            "agency_id": ref("agencies"),
        },
        "external_accounts": {
            "platform": "youtube",
            "platform_id": "UCtest",
            "url": "https://www.youtube.com/@test",
        },
        "artist_aliases": {"artist_id": ref("artists"), "alias": "Alias"},
        "artist_external_accounts": {
            "artist_id": ref("artists"),
            "account_id": ref("external_accounts"),
            "relationship": "owner",
            "is_primary": True,
        },
        "songs": {"title_native": "Song", "title_latin": "Song", "language_code": "en"},
        "song_artists": {"song_id": ref("songs"), "artist_id": ref("artists")},
        "karaoke_numbers": {
            "song_id": ref("songs"),
            "provider": "tj",
            "number": "00123",
        },
        "videos": {
            "platform": "youtube",
            "platform_video_id": "EXAMPLE0001",
            "title": "Video",
            "duration_seconds": 120,
            "source_account_id": ref("external_accounts"),
        },
        "live_archives": {
            "video_id": ref("videos"),
            "primary_artist_id": ref("artists"),
        },
        "archive_artists": {
            "archive_id": ref("live_archives"),
            "artist_id": ref("artists"),
            "role": "host",
        },
        "source_documents": {
            "source_kind": "manual_note",
            "content_text": "Synthetic fixture only",
            "captured_at": "2026-09-19T12:00:00+09:00",
        },
        "archive_sources": {
            "archive_id": ref("live_archives"),
            "document_id": ref("source_documents"),
            "role": "setlist_evidence",
        },
        "performances": {
            "archive_id": ref("live_archives"),
            "song_id": ref("songs"),
            "ordinal": 1,
            "raw_title": "Song",
            "start_seconds": 0,
            "end_seconds": 90,
            "source_document_id": ref("source_documents"),
        },
        "performance_artists": {
            "performance_id": ref("performances"),
            "artist_id": ref("artists"),
            "role": "lead",
        },
        "concerts": {
            "title": "Concert",
            "status": "scheduled",
            "event_format": "onsite",
            "time_precision": "datetime",
            "event_date": "2026-09-20",
            "starts_at": "2026-09-20T19:00:00+09:00",
            "timezone_name": "Asia/Seoul",
            "city": "City",
            "venue": "Venue",
        },
        "concert_artists": {"concert_id": ref("concerts"), "artist_id": ref("artists")},
        "concert_ticket_windows": {
            "concert_id": ref("concerts"),
            "label": "General",
            "url": "https://example.com/ticket",
        },
        "albums": {
            "title_native": "Album",
            "album_type": "album",
            "release_year": 2026,
        },
        "album_artists": {"album_id": ref("albums"), "artist_id": ref("artists")},
        "recordings": {
            "song_id": ref("songs"),
            "title_native": "Recording",
            "duration_ms": 90000,
        },
        "recording_artists": {
            "recording_id": ref("recordings"),
            "artist_id": ref("artists"),
            "role": "primary",
        },
        "recording_external_ids": {
            "recording_id": ref("recordings"),
            "platform": "spotify",
            "external_id": "abc",
        },
        "album_tracks": {
            "album_id": ref("albums"),
            "recording_id": ref("recordings"),
            "disc_number": 1,
            "track_number": 1,
        },
        "recording_lyrics": {
            "recording_id": ref("recordings"),
            "original_lyrics": "Synthetic text",
        },
        "covers": {"video_id": ref("videos"), "song_id": ref("songs")},
        "cover_artists": {
            "cover_id": ref("covers"),
            "artist_id": ref("artists"),
            "role": "vocal",
        },
        "group": {"slug": "group", "name_native": "Group", "entity_kind": "group"},
        "artist_group_members": {"group_id": ref("group"), "member_id": ref("artists")},
    }
    batch = review.create_batch("All resources")
    for name, payload in data.items():
        review.create(
            batch["id"], entity(name, "artists" if name == "group" else name, payload)
        )
    for row in review.page(batch["id"], page_size=100)["items"]:
        review.review(row["id"], 1, "approve")
    plan = review.preview(batch["id"])
    result = review.publish(
        plan["manifest_id"], plan["manifest_hash"], plan["operation_id"]
    )
    assert result["committed"]
    from app.admin.schemas.catalog import RESOURCES

    for name in RESOURCES:
        page = remote.page(name)
        assert page["total"] >= 1 and page["items"][0]["_label"]
        assert remote.page(name, q="not-existing-unique-test")["total"] == 0
    assert remote.page("song_artists", q="Song")["total"] == 1
    item = remote.page("performances")["items"][0]
    current = remote.detail("performances", item["id"])
    request = ManualSave(
        operation_id=uuid.uuid4(),
        catalog_id=remote.connection()["catalog_id"],
        entity=entity(
            "too-long",
            "performances",
            {"end_seconds": 150},
            operation="update",
            target_id=item["id"],
            expected_version=current["_version"],
        ),
    )
    with pytest.raises(DomainError):
        remote.manual_save(request)


def test_excluded_reference_and_stale_preview(review, remote):
    batch = review.create_batch("invalidated preview")
    a = review.create(batch["id"], entity())
    b = review.create(
        batch["id"],
        entity(
            "alias",
            "artist_aliases",
            {"artist_id": {"$ref": "artist:a"}, "alias": "alias"},
        ),
    )
    review.review(a["id"], 1, "approve")
    review.review(b["id"], 1, "approve")
    plan = review.preview(batch["id"])
    review.review(a["id"], 1, "exclude", "not verified")
    assert review.detail(b["id"])["status"] == "pending"
    with pytest.raises(DomainError):
        review.review(b["id"], 1, "approve")
    with pytest.raises(DomainError):
        review.publish(plan["manifest_id"], plan["manifest_hash"], plan["operation_id"])
    assert count(remote, "artists") == 0


def test_snapshot_rejects_remote_change(review, remote):
    _, _, _, result = initial(review)
    key = result["receipt"]["result_mapping"][0]["entity_id"]
    row = remote.detail("artists", key)
    batch = review.create_batch("update")
    d = review.create(
        batch["id"],
        entity(
            "edit",
            data={"name_native": "Review"},
            operation="update",
            target_id=key,
            expected_version=row["_version"],
        ),
    )
    review.review(d["id"], 1, "approve")
    plan = review.preview(batch["id"])
    remote.manual_save(
        ManualSave(
            operation_id=uuid.uuid4(),
            catalog_id=remote.connection()["catalog_id"],
            entity=entity(
                "other",
                data={"name_native": "Other"},
                operation="update",
                target_id=key,
                expected_version=row["_version"],
            ),
        )
    )
    with pytest.raises(DomainError):
        review.publish(plan["manifest_id"], plan["manifest_hash"], plan["operation_id"])
    assert remote.detail("artists", key)["name_native"] == "Other"
