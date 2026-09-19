from __future__ import annotations
from pathlib import Path
import hashlib
import json
import sqlite3
import zipfile
import tempfile

from ..db.local import LocalStore, now, uid, pack, unpack
from ..schemas.catalog import RESOURCES, DomainError, canonical, digest, validate
from ..schemas.contracts import EntityInput, ImportEnvelope
from pydantic import ValidationError


class ReviewService:
    def __init__(self, local, remote, input_dir):
        self.local = local
        self.remote = remote
        self.input_dir = input_dir
        input_dir.mkdir(parents=True, exist_ok=True)

    def batch(self, c, key):
        row = c.execute("SELECT * FROM import_batches WHERE id=?", (key,)).fetchone()
        if not row:
            raise DomainError("검수 묶음을 찾을 수 없습니다.", 404)
        return dict(row)

    def create_batch(self, name):
        state = self.remote.connection()
        with self.local.connect(write=True) as c:
            key = self.local.insert(
                c,
                "import_batches",
                name=name,
                batch_kind="incremental" if state.get("initialized") else "initial",
                status="reviewing",
                target_catalog_id=state.get("catalog_id"),
                revision=1,
            )
            return self.batch(c, key)

    def batches(self):
        with self.local.connect() as c:
            rows = [
                dict(r)
                for r in c.execute(
                    "SELECT * FROM import_batches ORDER BY created_at DESC"
                )
            ]
            for r in rows:
                r["counts"] = {
                    x["status"]: x["n"]
                    for x in c.execute(
                        "SELECT status,count(*) n FROM draft_entities WHERE batch_id=? GROUP BY status",
                        (r["id"],),
                    )
                }
            return rows

    def delete_batch(self, key, revision):
        with self.local.connect(write=True) as c:
            batch = self.batch(c, key)
            if batch["revision"] != revision:
                raise DomainError("다른 창에서 묶음이 변경되었습니다. 목록을 새로고침한 뒤 다시 삭제하세요.", 409)
            if c.execute("SELECT 1 FROM publish_plans WHERE batch_id=? AND status='publishing'", (key,)).fetchone():
                raise DomainError("반영 중이거나 결과 확인이 필요한 묶음입니다. 반영 이력에서 결과를 먼저 확인하세요.", 409)
            drafts = "SELECT id FROM draft_entities WHERE batch_id=?"
            plans = "SELECT id FROM publish_plans WHERE batch_id=?"
            c.execute("DELETE FROM publish_attempts WHERE plan_id IN (" + plans + ")", (key,))
            c.execute("DELETE FROM publish_plans WHERE batch_id=?", (key,))
            c.execute("DELETE FROM validation_issues WHERE batch_id=?", (key,))
            c.execute("DELETE FROM draft_relations WHERE source_draft_id IN (" + drafts + ")", (key,))
            for table in ("review_events", "remote_id_map"):
                c.execute("DELETE FROM " + table + " WHERE draft_id IN (" + drafts + ")", (key,))
            c.execute("DELETE FROM draft_entities WHERE batch_id=?", (key,))
            c.execute("DELETE FROM input_files WHERE batch_id=?", (key,))
            c.execute("DELETE FROM import_batches WHERE id=?", (key,))
        # Source files/snapshots may be shared across batches; never remove them here.
        return {"deleted": True, "batch_id": key}

    def ensure_editable(self, c, batch_id):
        batch = self.batch(c, batch_id)
        if batch["status"] in {"published", "cancelled"}:
            raise DomainError("완료된 묶음은 수정할 수 없습니다.", 409)
        if c.execute(
            "SELECT 1 FROM publish_plans WHERE batch_id=? AND status='publishing'",
            (batch_id,),
        ).fetchone():
            raise DomainError(
                "반영 중이거나 결과 확인이 필요합니다. 먼저 반영 결과를 확인하세요.",
                409,
            )
        c.execute(
            "UPDATE publish_plans SET status='invalidated',updated_at=? WHERE batch_id=? AND status='ready'",
            (now(), batch_id),
        )
        self.local.update(
            c,
            "import_batches",
            batch_id,
            status="reviewing",
            revision=batch["revision"] + 1,
        )

    def draft(self, c, key):
        row = c.execute("SELECT * FROM draft_entities WHERE id=?", (key,)).fetchone()
        if not row:
            raise DomainError("검수 항목을 찾을 수 없습니다.", 404)
        result = dict(row)
        for field in ("current_payload", "original_payload", "provenance"):
            result[field] = unpack(result[field], {})
        return result

    def detail(self, key):
        with self.local.connect() as c:
            result = self.draft(c, key)
            result["events"] = [
                dict(r)
                for r in c.execute(
                    "SELECT * FROM review_events WHERE draft_id=? ORDER BY created_at DESC LIMIT 40",
                    (key,),
                )
            ]
            result["issues"] = [
                dict(r)
                for r in c.execute(
                    "SELECT * FROM validation_issues WHERE draft_id=? AND status='open'",
                    (key,),
                )
            ]
            return result

    def page(self, batch_id, q="", status="", kind="", page=1, page_size=50):
        clauses = ["batch_id=?"]
        params = [batch_id]
        if status:
            clauses.append("status=?")
            params.append(status)
        if kind:
            clauses.append("entity_type=?")
            params.append(kind)
        if q:
            clauses.append("(client_ref LIKE ? OR current_payload LIKE ?)")
            params.extend(["%" + q + "%"] * 2)
        where = " AND ".join(clauses)
        with self.local.connect() as c:
            total = c.execute(
                "SELECT count(*) FROM draft_entities WHERE " + where, params
            ).fetchone()[0]
            rows = [
                dict(r)
                for r in c.execute(
                    "SELECT * FROM draft_entities WHERE "
                    + where
                    + " ORDER BY created_at,id LIMIT ? OFFSET ?",
                    [*params, page_size, (page - 1) * page_size],
                )
            ]
            for r in rows:
                r["current_payload"] = unpack(r["current_payload"])
                r.pop("original_payload")
                r.pop("provenance")
            return {"items": rows, "total": total, "page": page, "page_size": page_size}

    def next_pending(self, key, q="", status="all", page_size=30):
        with self.local.connect() as c:
            current = self.draft(c, key)
            params = [current["batch_id"]]
            scope = "batch_id=?"
            if q:
                scope += " AND (client_ref LIKE ? OR current_payload LIKE ?)"
                params.extend(["%" + q + "%"] * 2)
            row = c.execute(
                "SELECT id,created_at FROM draft_entities WHERE " + scope +
                " AND status='pending' AND (created_at,id)>(?,?) ORDER BY created_at,id LIMIT 1",
                [*params, current["created_at"], key],
            ).fetchone()
            if not row:
                return {"item": None}
            if status == "pending":
                scope += " AND status='pending'"
            preceding = c.execute(
                "SELECT count(*) FROM draft_entities WHERE " + scope +
                " AND (created_at,id)<(?,?)", [*params,row["created_at"],row["id"]],
            ).fetchone()[0]
            result = self.draft(c, row["id"])
        return {"item": self.detail(result["id"]), "page": preceding // page_size + 1}

    def _log(self, c, key, action, revision, note=None, hash_value=None, change=None):
        self.local.insert(
            c,
            "review_events",
            draft_id=key,
            action=action,
            actor_label="local_operator",
            revision=revision,
            payload_hash=hash_value,
            change_data=pack(change or {}),
            note=note,
        )

    def _relations(self, c, draft):
        c.execute("DELETE FROM draft_relations WHERE source_draft_id=?", (draft["id"],))
        data = draft["current_payload"]
        batch = self.batch(c, draft["batch_id"])
        for f in RESOURCES[draft["entity_type"]]["fields"]:
            target = f.get("reference")
            value = data.get(f["name"])
            if not target or value is None:
                continue
            local_id = None
            catalog = None
            remote_id = None
            unresolved = None
            if isinstance(value, dict) and "$ref" in value:
                other = c.execute(
                    "SELECT id FROM draft_entities WHERE batch_id=? AND client_ref=? AND entity_type=?",
                    (draft["batch_id"], value["$ref"], target),
                ).fetchone()
                if other:
                    local_id = other["id"]
                else:
                    unresolved = value["$ref"]
            elif isinstance(value, int):
                catalog = batch["target_catalog_id"]
                remote_id = value
            else:
                continue
            self.local.insert(
                c,
                "draft_relations",
                source_draft_id=draft["id"],
                field_path="/" + f["name"],
                target_type=target,
                target_draft_id=local_id,
                target_catalog_id=catalog,
                target_entity_id=remote_id,
                unresolved_ref=unresolved,
                is_required=int(not f["nullable"]),
                source_revision=draft["revision"],
            )

    def _invalidate(self, c, batch_id, key):
        # Transitive dependants (also covers references discovered after a file import).
        queue = [key]
        seen = {key}
        while queue:
            current = queue.pop()
            ref = c.execute(
                "SELECT client_ref FROM draft_entities WHERE id=?", (current,)
            ).fetchone()[0]
            for row in c.execute(
                "SELECT id,current_payload FROM draft_entities WHERE batch_id=?",
                (batch_id,),
            ).fetchall():
                if row["id"] in seen:
                    continue
                if any(
                    isinstance(v, dict) and v.get("$ref") == ref
                    for v in unpack(row["current_payload"]).values()
                ):
                    seen.add(row["id"])
                    queue.append(row["id"])
        for item in seen:
            d = self.draft(c, item)
            if d["status"] == "approved":
                self.local.update(
                    c,
                    "draft_entities",
                    item,
                    status="pending",
                    approved_revision=None,
                    approved_hash=None,
                    approved_at=None,
                )
                self._log(
                    c,
                    item,
                    "invalidate_approval",
                    d["revision"],
                    "내용 또는 연결 대상 변경",
                )
        return seen

    def _create(self, c, batch_id, entity, file_id=None):
        if entity.entity_type not in RESOURCES:
            raise DomainError("지원하지 않는 자료 종류입니다.")
        if entity.operation == "update":
            if not entity.target_id or not entity.expected_version:
                raise DomainError("수정은 대상 ID와 기준 버전이 필요합니다.")
        elif entity.target_id or entity.expected_version:
            raise DomainError("신규 등록에 기존 ID를 지정할 수 없습니다.")
        # Preserve imperfect inputs for editing; errors block approval, never silently coerce on import.
        if c.execute(
            "SELECT 1 FROM draft_entities WHERE batch_id=? AND client_ref=?",
            (batch_id, entity.client_ref),
        ).fetchone():
            raise DomainError(
                "같은 client_ref가 있습니다. 기존 항목을 편집하거나 다른 이름을 사용하세요.",
                409,
            )
        if any(
            k in entity.provenance
            for k in ("legacy", "legacy_id", "legacy_table", "password", "database_url")
        ):
            raise DomainError("기존 DB ID 대응 또는 비밀값은 출처에 포함하지 마세요.")
        key = self.local.insert(
            c,
            "draft_entities",
            batch_id=batch_id,
            input_file_id=file_id,
            client_ref=entity.client_ref,
            entity_type=entity.entity_type,
            operation=entity.operation,
            target_id=entity.target_id,
            expected_version=entity.expected_version,
            original_payload=pack(entity.data),
            current_payload=pack(entity.data),
            provenance=pack(entity.provenance),
            revision=1,
            status="pending",
            ai_confidence=None,
        )
        self._relations(c, self.draft(c, key))
        return key

    def create(self, batch_id, entity):
        with self.local.connect(write=True) as c:
            self.ensure_editable(c, batch_id)
            key = self._create(c, batch_id, entity)
        return self.detail(key)

    def edit(self, key, revision, data):
        with self.local.connect(write=True) as c:
            d = self.draft(c, key)
            if d["revision"] != revision:
                raise DomainError(
                    "다른 창에서 수정된 항목입니다. 다시 불러오세요.", 409
                )
            self.ensure_editable(c, d["batch_id"])
            self._invalidate(c, d["batch_id"], key)
            self.local.update(
                c,
                "draft_entities",
                key,
                current_payload=pack(data),
                revision=revision + 1,
                status="editing",
                approved_revision=None,
                approved_hash=None,
                approved_at=None,
            )
            c.execute(
                "UPDATE validation_issues SET status='superseded',updated_at=? WHERE draft_id=?",
                (now(), key),
            )
            self._relations(c, self.draft(c, key))
            self._log(
                c,
                key,
                "edit",
                revision + 1,
                change={"before": d["current_payload"], "after": data},
            )
        return self.detail(key)

    def review(self, key, revision, action, note=None):
        error = None
        with self.local.connect(write=True) as c:
            d = self.draft(c, key)
            if d["revision"] != revision:
                raise DomainError("검수 항목이 변경되었습니다.", 409)
            self.ensure_editable(c, d["batch_id"])
            if action in {"hold", "exclude"} and not (note or "").strip():
                raise DomainError("보류·제외 사유를 입력하세요.")
            state = {
                "approve": "approved",
                "hold": "held",
                "exclude": "excluded",
                "reopen": "pending",
            }[action]
            if action == "approve":
                try:
                    validate(
                        d["entity_type"],
                        d["current_payload"],
                        partial=d["operation"] == "update",
                    )
                    for f in RESOURCES[d["entity_type"]]["fields"]:
                        val = d["current_payload"].get(f["name"])
                        if isinstance(val, dict) and "$ref" in val:
                            target = c.execute(
                                "SELECT entity_type,status FROM draft_entities WHERE batch_id=? AND client_ref=?",
                                (d["batch_id"], val["$ref"]),
                            ).fetchone()
                            if (
                                not target
                                or target["entity_type"] != f.get("reference")
                                or target["status"] == "excluded"
                            ):
                                raise DomainError(
                                    f["name"] + ": 연결할 초안이 없거나 제외되었습니다."
                                )
                except DomainError as exc:
                    error = exc
                    state = "blocked"
                    self.local.insert(
                        c,
                        "validation_issues",
                        batch_id=d["batch_id"],
                        draft_id=key,
                        checked_revision=revision,
                        severity="error",
                        code="VALIDATION",
                        message=str(exc),
                        status="open",
                    )
            if action != "approve":
                self._invalidate(c, d["batch_id"], key)
            hash_value = digest(d["current_payload"]) if state == "approved" else None
            self.local.update(
                c,
                "draft_entities",
                key,
                status=state,
                review_note=note,
                approved_revision=revision if hash_value else None,
                approved_hash=hash_value,
                approved_at=now() if hash_value else None,
            )
            if hash_value:
                c.execute(
                    "UPDATE validation_issues SET status='resolved',resolved_at=?,updated_at=? WHERE draft_id=?",
                    (now(), now(), key),
                )
            self._log(
                c, key, action if not error else "hold", revision, note, hash_value
            )
        if error:
            raise error
        return self.detail(key)

    def import_json(self, batch_id, filename, envelope, raw=None):
        if (
            Path(filename).name != filename
            or "/" in filename
            or "\\" in filename
            or not filename.lower().endswith(".json")
        ):
            raise DomainError("JSON 파일 이름을 확인하세요.")
        content = raw or canonical(envelope.model_dump()).encode("utf-8")
        if len(content) > 10 * 1024 * 1024:
            raise DomainError("파일당 최대 10MiB입니다.")
        file_hash = hashlib.sha256(content).hexdigest()
        snapshot = self.local.workspace / "snapshots" / (file_hash + ".json")
        with self.local.connect(write=True) as c:
            existing = c.execute(
                "SELECT id FROM input_files WHERE batch_id=? AND file_hash=?",
                (batch_id, file_hash),
            ).fetchone()
            if existing:
                return {"duplicate": True, "imported": 0}
            self.ensure_editable(c, batch_id)
            # Exclusive, immutable content-addressed snapshot.
            if not snapshot.exists():
                with snapshot.open("xb") as f:
                    f.write(content)
            file_id = self.local.insert(
                c,
                "input_files",
                batch_id=batch_id,
                relative_path=filename,
                file_hash=file_hash,
                byte_size=len(content),
                schema_version="1",
                snapshot_path="snapshots/" + snapshot.name,
                parse_status="valid",
                imported_at=now(),
            )
            for entity in envelope.entities:
                self._create(c, batch_id, entity, file_id)
            for row in c.execute(
                "SELECT id FROM draft_entities WHERE batch_id=?", (batch_id,)
            ).fetchall():
                self._relations(c, self.draft(c, row["id"]))
        return {"duplicate": False, "imported": len(envelope.entities)}

    def scan(self, batch_id):
        results = []
        base = self.input_dir.resolve()
        files = list(self.input_dir.glob("*.json"))
        if len(files) > 100:
            raise DomainError("한 번에 최대 100개 파일을 읽습니다.")
        for p in files:
            try:
                if p.is_symlink() or not p.resolve().is_relative_to(base):
                    raise DomainError("허용 폴더 밖 파일입니다.")
                with p.open("rb") as f:
                    raw = f.read(10 * 1024 * 1024 + 1)
                if len(raw) > 10 * 1024 * 1024:
                    raise DomainError("파일 크기 제한 초과")
                envelope = ImportEnvelope.model_validate_json(raw)
                result = self.import_json(batch_id, p.name, envelope, raw)
                results.append({"file": p.name, **result})
            except (ValueError, DomainError, OSError) as exc:
                results.append(
                    {
                        "file": p.name,
                        "error": (
                            str(exc)
                            if isinstance(exc, DomainError)
                            else "JSON 형식 또는 파일 접근을 확인하세요."
                        ),
                    }
                )
        return {"files": results}

    def _entries(self, c, batch_id):
        all_rows = [
            self.draft(c, r["id"])
            for r in c.execute(
                "SELECT id FROM draft_entities WHERE batch_id=? ORDER BY created_at,id",
                (batch_id,),
            ).fetchall()
        ]
        if not all_rows:
            raise DomainError("반영할 항목이 없습니다.")
        if any(d["status"] not in {"approved", "excluded"} for d in all_rows):
            raise DomainError("모든 항목을 승인하거나 제외해야 합니다.", 409)
        included = [d for d in all_rows if d["status"] == "approved"]
        if not included:
            raise DomainError("승인한 항목이 없습니다.")
        for d in included:
            if d["approved_revision"] != d["revision"] or d["approved_hash"] != digest(
                d["current_payload"]
            ):
                raise DomainError("승인 후 변경된 자료입니다.", 409)
        entries = [
            {
                "client_ref": d["client_ref"],
                "entity_type": d["entity_type"],
                "operation": d["operation"],
                "target_id": d["target_id"],
                "expected_version": d["expected_version"],
                "data": d["current_payload"],
                "draft_id": d["id"],
                "revision": d["revision"],
                "approved_hash": d["approved_hash"],
                "provenance": d["provenance"],
            }
            for d in included
        ]
        return all_rows, entries

    def preview(self, batch_id):
        state = self.remote.connection()
        if not state["connected"]:
            raise DomainError(state.get("message", "DB 연결 필요"), 503)
        with self.local.connect(write=True) as c:
            batch = self.batch(c, batch_id)
            self.ensure_editable(c, batch_id)
            if (
                batch["target_catalog_id"]
                and batch["target_catalog_id"] != state["catalog_id"]
            ):
                raise DomainError("검수 대상 DB와 현재 DB가 다릅니다.", 409)
            self.local.update(
                c, "import_batches", batch_id, target_catalog_id=state["catalog_id"]
            )
            rows, entries = self._entries(c, batch_id)
            revision = self.batch(c, batch_id)["revision"]
        initial = not state["initialized"]
        preview = self.remote.preview(entries, state["catalog_id"], initial)
        manifest = {
            "catalog_id": state["catalog_id"],
            "initial": initial,
            "batch_id": batch_id,
            "batch_revision": revision,
            "entries": entries,
            "excluded": [d["id"] for d in rows if d["status"] == "excluded"],
            **preview,
        }
        hash_value = digest(manifest)
        operation = uid()
        with self.local.connect(write=True) as c:
            if self.batch(c, batch_id)["revision"] != revision:
                raise DomainError("미리보기 중 자료가 변경되었습니다.", 409)
            plan = self.local.insert(
                c,
                "publish_plans",
                batch_id=batch_id,
                operation_id=operation,
                target_catalog_id=state["catalog_id"],
                expected_schema_version="catalog-v1",
                manifest_payload=pack(manifest),
                manifest_hash=hash_value,
                status="ready",
                frozen_at=now(),
            )
            self.local.update(c, "import_batches", batch_id, status="frozen")
        return {
            "manifest_id": plan,
            "operation_id": operation,
            "manifest_hash": hash_value,
            "initial": initial,
            "changes": preview["changes"],
            "excluded_count": len(manifest["excluded"]),
            "catalog_id": state["catalog_id"],
        }

    def publish(self, plan_id, hash_value, operation):
        with self.local.connect(write=True) as c:
            p = c.execute(
                "SELECT * FROM publish_plans WHERE id=?", (plan_id,)
            ).fetchone()
            if (
                not p
                or p["manifest_hash"] != hash_value
                or p["operation_id"] != operation
            ):
                raise DomainError("반영 계획을 확인하세요.", 409)
            if p["status"] == "committed":
                return {"committed": True, "operation_id": operation}
            if p["status"] not in {"ready", "publishing"}:
                raise DomainError(
                    "변경된 반영 계획입니다. 다시 미리보기를 만드세요.", 409
                )
            manifest = unpack(p["manifest_payload"])
            if digest(manifest) != hash_value:
                raise DomainError("반영 계획이 손상되었습니다.", 409)
            if self.batch(c, p["batch_id"])["revision"] != manifest["batch_revision"]:
                raise DomainError("초안 구성이 변경되었습니다.", 409)
            rows, entries = self._entries(c, p["batch_id"])
            if entries != manifest["entries"]:
                raise DomainError("승인 내용이 변경되었습니다.", 409)
            self.local.update(c, "publish_plans", plan_id, status="publishing")
            attempt_no = (
                c.execute(
                    "SELECT count(*) FROM publish_attempts WHERE plan_id=?", (plan_id,)
                ).fetchone()[0]
                + 1
            )
            attempt = self.local.insert(
                c,
                "publish_attempts",
                plan_id=plan_id,
                attempt_number=attempt_no,
                state="started",
                started_at=now(),
            )
        try:
            receipt = self.remote.publish(manifest, hash_value, operation)
        except DomainError as exc:
            with self.local.connect(write=True) as c:
                self.local.update(
                    c,
                    "publish_attempts",
                    attempt,
                    state="unknown" if exc.status == 503 else "failed",
                    error_code=str(exc.status),
                    error_message=str(exc),
                    finished_at=now(),
                )
                if exc.status != 503:
                    self.local.update(c, "publish_plans", plan_id, status="ready")
            raise
        self._finish(plan_id, receipt)
        return {"committed": True, "operation_id": operation, "receipt": receipt}

    def _finish(self, plan_id, receipt):
        with self.local.connect(write=True) as c:
            p = c.execute(
                "SELECT * FROM publish_plans WHERE id=?", (plan_id,)
            ).fetchone()
            manifest = unpack(p["manifest_payload"])
            if p["status"] == "committed":
                return
            if (
                receipt["manifest_hash"] != p["manifest_hash"]
                or str(receipt["catalog_instance_id"]) != p["target_catalog_id"]
            ):
                raise DomainError("반영 영수증의 대상/내용이 다릅니다.", 409)
            self.local.update(c, "publish_plans", plan_id, status="committed")
            self.local.update(c, "import_batches", p["batch_id"], status="published")
            c.execute(
                "UPDATE publish_attempts SET state='committed',remote_import_id=?,remote_result=?,finished_at=?,updated_at=? WHERE plan_id=? AND state IN ('started','unknown')",
                (receipt["id"], pack(receipt), now(), now(), plan_id),
            )
            refs = {e["client_ref"]: e for e in manifest["entries"]}
            for mapping in receipt["result_mapping"]:
                d = refs[mapping["client_ref"]]
                self.local.update(
                    c, "draft_entities", d["draft_id"], status="published"
                )
                self.local.insert(
                    c,
                    "remote_id_map",
                    draft_id=d["draft_id"],
                    target_catalog_id=p["target_catalog_id"],
                    entity_type=mapping["entity_type"],
                    entity_id=mapping["entity_id"],
                    remote_version=mapping.get("version"),
                    operation_id=p["operation_id"],
                    mapped_at=now(),
                )
                self._log(
                    c,
                    d["draft_id"],
                    "publish",
                    d["revision"],
                    hash_value=d["approved_hash"],
                )

    def recover(self, operation):
        receipt = self.remote.receipt(operation)
        with self.local.connect() as c:
            p = c.execute(
                "SELECT * FROM publish_plans WHERE operation_id=?", (operation,)
            ).fetchone()
        if not p:
            raise DomainError("반영 작업을 찾을 수 없습니다.", 404)
        if receipt:
            self._finish(p["id"], receipt)
        return {
            "committed": bool(receipt),
            "operation_id": operation,
            "receipt": receipt,
        }

    def history(self):
        with self.local.connect() as c:
            return [
                dict(r)
                for r in c.execute(
                    """SELECT p.id,p.batch_id,p.operation_id,p.manifest_hash,p.status,p.created_at,
             b.name FROM publish_plans p JOIN import_batches b ON b.id=p.batch_id ORDER BY p.created_at DESC LIMIT 100"""
                )
            ]

    def backup(self):
        path = self.local.workspace / ("backup-" + uid() + ".zip")
        temporary = self.local.workspace / ("snapshot-" + uid() + ".sqlite3")
        with self.local.connect() as source:
            dest = sqlite3.connect(temporary)
            try:
                source.backup(dest)
            finally:
                dest.close()
        try:
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
                z.write(temporary, "review.sqlite3")
                for f in (self.local.workspace / "snapshots").glob("*.json"):
                    if not f.is_symlink():
                        z.write(f, "snapshots/" + f.name)
        finally:
            temporary.unlink(missing_ok=True)
        return path

    def export(self, batch_id):
        with self.local.connect() as c:
            self.batch(c, batch_id)
            rows = [
                self.draft(c, r["id"])
                for r in c.execute(
                    "SELECT id FROM draft_entities WHERE batch_id=? ORDER BY created_at,id",
                    (batch_id,),
                ).fetchall()
            ]
        return {
            "schema_version": "1",
            "entities": [
                {
                    "client_ref": d["client_ref"],
                    "entity_type": d["entity_type"],
                    "operation": d["operation"],
                    "target_id": d["target_id"],
                    "expected_version": d["expected_version"],
                    "data": d["current_payload"],
                    "provenance": d["provenance"],
                }
                for d in rows
                if d["status"] != "excluded"
            ],
        }
