from __future__ import annotations
from typing import Any, Literal, Annotated
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Ref(Contract):
    ref: str = Field(alias="$ref", min_length=1, max_length=200)


class EntityInput(Contract):
    client_ref: str = Field(min_length=1, max_length=200)
    entity_type: str
    operation: Literal["create", "update"] = "create"
    data: dict[str, Any]
    target_id: int | None = Field(default=None, gt=0)
    expected_version: int | None = Field(default=None, gt=0)
    provenance: dict[str, Any] = Field(default_factory=dict)


class ImportEnvelope(Contract):
    schema_version: Literal["1"]
    entities: list[EntityInput] = Field(min_length=1, max_length=1000)


class ImportRequest(Contract):
    batch_id: UUID
    filename: str = Field(min_length=1, max_length=120)
    envelope: ImportEnvelope


class BatchCreate(Contract):
    name: str = Field(min_length=1, max_length=120)


class DraftCreate(EntityInput):
    batch_id: UUID


class DraftPatch(Contract):
    revision: int = Field(gt=0)
    data: dict[str, Any]


class ReviewRequest(Contract):
    revision: int = Field(gt=0)
    action: Literal["approve", "hold", "exclude", "reopen"]
    note: str | None = Field(default=None, max_length=4000)


class PublishRequest(Contract):
    manifest_id: UUID
    manifest_hash: str = Field(pattern="^[0-9a-f]{64}$")
    operation_id: UUID


class ManualSave(Contract):
    operation_id: UUID
    catalog_id: UUID
    entity: EntityInput


class Page(Contract):
    items: list[dict[str, Any]]
    total: int
    page: int
    page_size: int


class SessionView(Contract):
    csrf: str


class ConnectionView(Contract):
    connected: bool
    label: str = "Neon · 새 음악 카탈로그"
    catalog_id: str | None = None
    schema_version: str | None = None
    initialized: bool = False
    message: str | None = None


class Result(Contract):
    data: dict[str, Any]


class MetadataView(Contract):
    resources: list[dict[str, Any]]


class ErrorView(Contract):
    detail: str


class ArchiveRequest(Contract):
    operation_id: UUID
    catalog_id: UUID
    expected_version: int = Field(gt=0)
    archived: bool
