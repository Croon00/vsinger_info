from uuid import UUID
from typing import Literal
from fastapi import APIRouter, Query
from fastapi.responses import FileResponse, JSONResponse
from starlette.background import BackgroundTask
from ..schemas.contracts import *
from ..schemas.catalog import RESOURCES
from ..services.platforms import PlatformService


def router_for(review, remote):
    router = APIRouter(prefix="/api/admin")

    platforms = PlatformService(review)

    @router.get("/review-items", response_model=Page)
    def review_items(batch_id: UUID, q: str = Query("", max_length=200),
                     status: str = "", page: int = Query(1, ge=1),
                     page_size: int = Query(30, ge=1, le=100)):
        return platforms.review_page(str(batch_id), q, status, page, page_size)

    @router.get("/review-items/{key}/next-pending", response_model=Result)
    def next_review_item(key: UUID, q: str = Query("", max_length=200),
                         status: Literal["all", "pending"] = "all",
                         page_size: int = Query(30, ge=1, le=100)):
        return {"data": platforms.next_review(str(key), q, status, page_size)}

    @router.post("/platform-registrations/{key}/review", response_model=Result)
    def platform_review(key: UUID, body: PlatformReview):
        return {"data": platforms.review_group(str(key), body)}

    @router.post("/platform-registrations/from-catalog", response_model=Result)
    def platform_from_catalog(body: PlatformFromCatalog):
        return {"data": platforms.from_catalog(str(body.batch_id), body.account_id)}

    @router.get("/platform-registrations/{key}", response_model=Result)
    def platform_detail(key: UUID):
        return {"data": platforms.detail(str(key))}

    @router.post("/platform-registrations", response_model=Result)
    def platform_save(body: PlatformRegistration):
        return {"data": platforms.save(body)}

    @router.get("/metadata", response_model=MetadataView)
    def metadata():
        return {"resources": list(RESOURCES.values())}

    @router.get("/connection", response_model=ConnectionView)
    def connection():
        return remote.connection()

    @router.get("/batches", response_model=Result)
    def batches():
        items = review.batches()
        for batch in items:
            batch["review_counts"] = platforms.review_counts(batch["id"])
        return {"data": {"items": items}}

    @router.post("/batches", response_model=Result)
    def create_batch(body: BatchCreate):
        return {"data": review.create_batch(body.name)}

    @router.delete("/batches/{key}", response_model=Result)
    def delete_batch(key: UUID, revision: int = Query(..., gt=0)):
        return {"data": review.delete_batch(str(key), revision)}

    @router.get("/drafts", response_model=Page)
    def drafts(
        batch_id: UUID,
        q: str = Query("", max_length=200),
        status: str = "",
        kind: str = "",
        page: int = Query(1, ge=1),
        page_size: int = Query(30, ge=1, le=100),
    ):
        return review.page(str(batch_id), q, status, kind, page, page_size)

    @router.post("/drafts", response_model=Result)
    def create(body: DraftCreate):
        return {
            "data": review.create(
                str(body.batch_id), EntityInput(**body.model_dump(exclude={"batch_id"}))
            )
        }

    @router.get("/drafts/{key}", response_model=Result)
    def draft(key: UUID):
        return {"data": review.detail(str(key))}

    @router.get("/drafts/{key}/next-pending", response_model=Result)
    def next_pending(key: UUID, q: str = Query("", max_length=200),
                     status: Literal["all", "pending"] = "all",
                     page_size: int = Query(30, ge=1, le=100)):
        return {"data": review.next_pending(str(key), q, status, page_size)}

    @router.patch("/drafts/{key}", response_model=Result)
    def edit(key: UUID, body: DraftPatch):
        return {"data": review.edit(str(key), body.revision, body.data)}

    @router.post("/drafts/{key}/review", response_model=Result)
    def approve(key: UUID, body: ReviewRequest):
        return {"data": review.review(str(key), body.revision, body.action, body.note)}

    @router.post("/imports", response_model=Result)
    def upload(body: ImportRequest):
        return {
            "data": review.import_json(str(body.batch_id), body.filename, body.envelope)
        }

    @router.post("/batches/{key}/scan", response_model=Result)
    def scan(key: UUID):
        return {"data": review.scan(str(key))}

    @router.get("/batches/{key}/export")
    def export(key: UUID):
        return JSONResponse(
            review.export(str(key)),
            headers={
                "Content-Disposition": 'attachment; filename="catalog-review.json"'
            },
        )

    @router.post("/batches/{key}/preview", response_model=Result)
    def preview(key: UUID):
        return {"data": review.preview(str(key))}

    @router.post("/publish", response_model=Result)
    def publish(body: PublishRequest):
        return {
            "data": review.publish(
                str(body.manifest_id), body.manifest_hash, str(body.operation_id)
            )
        }

    @router.post("/publish/{operation}/recover", response_model=Result)
    def recover(operation: UUID):
        return {"data": review.recover(str(operation))}

    @router.get("/history", response_model=Result)
    def history():
        return {"data": {"items": review.history()}}

    @router.get("/catalog/history", response_model=Result)
    def remote_history():
        return {"data": {"items": remote.imports()}}

    @router.post("/catalog/save", response_model=Result)
    def manual(body: ManualSave):
        return {"data": remote.manual_save(body)}

    @router.get("/catalog/{kind}", response_model=Page)
    def catalog(
        kind: str,
        q: str = Query("", max_length=200),
        page: int = Query(1, ge=1),
        page_size: int = Query(30, ge=1, le=100),
    ):
        return remote.page(kind, q, page, page_size)

    @router.post("/catalog/{kind}/{key}/archive", response_model=Result)
    def archive(kind: str, key: int, body: ArchiveRequest):
        return {"data": remote.archive(kind, key, body)}

    @router.get("/catalog/{kind}/{key}", response_model=Result)
    def catalog_detail(kind: str, key: int):
        return {"data": remote.detail(kind, key)}

    @router.get("/backup")
    def backup():
        path = review.backup()
        return FileResponse(
            path,
            filename="catalog-review-backup.zip",
            background=BackgroundTask(path.unlink, missing_ok=True),
        )

    return router
