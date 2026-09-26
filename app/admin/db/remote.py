from __future__ import annotations
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
import json
from uuid import UUID

from sqlalchemy import create_engine, text, bindparam
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from ..schemas.catalog import (
    RESOURCES,
    DomainError,
    canonical,
    digest,
    generated,
    validate,
)
from ..config import ROOT

OWNERS = {
    "artist_aliases": ("artists", "artist_id"),
    "artist_group_members": ("artists", "group_id"),
    "artist_external_accounts": ("artists", "artist_id"),
    "song_artists": ("songs", "song_id"),
    "karaoke_numbers": ("songs", "song_id"),
    "archive_artists": ("live_archives", "archive_id"),
    "archive_sources": ("live_archives", "archive_id"),
    "performance_artists": ("performances", "performance_id"),
    "concert_artists": ("concerts", "concert_id"),
    "concert_ticket_windows": ("concerts", "concert_id"),
    "album_artists": ("albums", "album_id"),
    "album_tracks": ("albums", "album_id"),
    "recording_artists": ("recordings", "recording_id"),
    "recording_external_ids": ("recordings", "recording_id"),
    "cover_artists": ("covers", "cover_id"),
}
ALL_COLUMNS = json.loads(
    (ROOT / "migrations/catalog/columns.json").read_text(encoding="utf-8")
)


def plain(value):
    return json.loads(json.dumps(value, default=str))


def label_expression(name, alias="t", depth=3):
    fields = {f["name"]: f for f in RESOURCES[name]["fields"]}
    for key in (
        "name_native",
        "title_native",
        "title",
        "alias",
        "raw_title",
        "label",
        "handle",
        "content_text",
    ):
        if key in fields and key != "label":
            return (
                "COALESCE(NULLIF(left("
                + alias
                + "."
                + key
                + ",120),''),'#'||"
                + alias
                + ".id::text)"
            )
    if depth:
        refs = [f for f in fields.values() if f.get("reference")][:2]
        if refs:
            expressions = []
            for index, f in enumerate(refs):
                a = alias + "r" + str(index)
                expressions.append(
                    "COALESCE((SELECT "
                    + label_expression(f["reference"], a, depth - 1)
                    + " FROM "
                    + f["reference"]
                    + " "
                    + a
                    + " WHERE "
                    + a
                    + ".id="
                    + alias
                    + "."
                    + f["name"]
                    + "),'미연결')"
                )
            return " || ' · ' || ".join(expressions)
    key = next((k for k in ("url", "external_id", "number") if k in fields), None)
    return (
        "COALESCE(" + alias + "." + key + ",'#'||" + alias + ".id::text)"
        if key
        else "'#'||" + alias + ".id::text"
    )


class RemoteCatalog:
    def __init__(self, url, expected_instance_id=None):
        self.engine = None
        self.expected_instance_id = expected_instance_id
        if url:
            url = url.replace("postgresql://", "postgresql+psycopg://", 1).replace(
                "postgres://", "postgresql+psycopg://", 1
            )
            self.engine = create_engine(
                url,
                pool_size=3,
                max_overflow=2,
                pool_pre_ping=True,
                connect_args={"connect_timeout": 10},
                echo=False,
                hide_parameters=True,
            )

    @contextmanager
    def session(self, write=False):
        if not self.engine:
            raise DomainError("새 DB 접속 설정이 없습니다.", 503)
        try:
            with Session(self.engine) as s:
                if not write:
                    s.execute(text("SET TRANSACTION READ ONLY"))
                s.execute(text("SET LOCAL statement_timeout='60s'"))
                s.execute(text("SET LOCAL lock_timeout='10s'"))
                yield s
                if write:
                    s.commit()
                else:
                    s.rollback()
        except SQLAlchemyError as exc:
            code = getattr(getattr(exc, "orig", None), "sqlstate", None)
            if code in {"23505", "23503", "23514", "23001", "23502"}:
                raise DomainError(
                    "중복·연결·필수 값 또는 DB 제약을 확인하세요. 변경은 반영되지 않았습니다.",
                    409,
                ) from None
            raise DomainError(
                "DB 연결 또는 저장 결과 확인이 필요합니다. 같은 작업을 다시 만들지 말고 결과 확인을 누르세요.",
                503,
            ) from None

    def identity(self, s, lock=False):
        revisions = tuple(s.execute(text(
            "SELECT version FROM catalog_schema_migrations ORDER BY version"
        )).scalars())
        if revisions not in {("001", "002"), ("001", "002", "003")}:
            raise DomainError("지원하지 않는 DB migration revision입니다.", 409)
        r = (
            s.execute(
                text("SELECT * FROM catalog_instance" + (" FOR UPDATE" if lock else ""))
            )
            .mappings()
            .one()
        )
        if r["schema_version"] != "catalog-v2":
            raise DomainError("지원하지 않는 DB 구조 버전입니다.", 409)
        if self.expected_instance_id:
            try:
                matches = UUID(str(r["id"])) == UUID(self.expected_instance_id)
            except ValueError:
                matches = False
            if not matches:
                raise DomainError("설정한 DB instance identity와 일치하지 않습니다.", 409)
        return dict(r)

    def connection(self):
        try:
            with self.session() as s:
                r = self.identity(s)
                return {
                    "connected": True,
                    "catalog_id": str(r["id"]),
                    "schema_version": r["schema_version"],
                    "initialized": r["initial_import_id"] is not None,
                }
        except DomainError as e:
            return {"connected": False, "message": str(e), "initialized": False}

    def get(self, s, name, key, lock=False):
        if name not in RESOURCES:
            raise DomainError("지원하지 않는 자료입니다.")
        r = (
            s.execute(
                text(
                    "SELECT * FROM "
                    + name
                    + " WHERE id=:id"
                    + (" FOR UPDATE" if lock else "")
                ),
                {"id": key},
            )
            .mappings()
            .first()
        )
        if not r:
            raise DomainError("연결할 자료가 없습니다: " + name, 404)
        return dict(r)

    def version(self, s, name, row, lock=False):
        if "version" in row:
            return row["version"]
        if name in OWNERS:
            parent, key = OWNERS[name]
            return self.get(s, parent, row[key], lock=lock)["version"]
        return None

    def page(self, name, q="", page=1, page_size=50):
        if name not in RESOURCES:
            raise DomainError("지원하지 않는 자료입니다.")
        fields = [
            f["name"]
            for f in RESOURCES[name]["fields"]
            if f["type"] == "TEXT" and not f.get("reference")
        ]
        terms = [
            "CAST(t.id AS text) ILIKE :q",
            "(" + label_expression(name) + ") ILIKE :q",
        ] + ["COALESCE(t." + f + ",'') ILIKE :q" for f in fields]
        clause = " WHERE (" + " OR ".join(terms) + ")" if q else ""
        params = {
            "q": "%" + q + "%",
            "limit": page_size,
            "offset": (page - 1) * page_size,
        }
        with self.session() as s:
            total = s.execute(
                text("SELECT count(*) FROM " + name + " t" + clause), params
            ).scalar_one()
            rows = (
                s.execute(
                    text(
                        "SELECT t.*,("
                        + label_expression(name)
                        + ") AS _label FROM "
                        + name
                        + " t"
                        + clause
                        + " ORDER BY t.id DESC LIMIT :limit OFFSET :offset"
                    ),
                    params,
                )
                .mappings()
                .all()
            )
            return {
                "items": plain([dict(r) for r in rows]),
                "total": total,
                "page": page,
                "page_size": page_size,
            }

    def detail(self, name, key):
        with self.session() as s:
            row = self.get(s, name, key)
            row["_version"] = self.version(s, name, row)
            return plain(row)

    def platform_registration(self, key):
        with self.session() as s:
            account = self.get(s, "external_accounts", key)
            if account.get("archived_at"):
                raise DomainError("보관된 계정은 먼저 복원하세요.")
            account["_version"] = self.version(s, "external_accounts", account)
            links = [dict(row) for row in s.execute(text(
                "SELECT * FROM artist_external_accounts WHERE account_id=:key ORDER BY position,id"
            ), {"key": key}).mappings()]
            for row in links:
                row["_version"] = self.version(s, "artist_external_accounts", row)
            return plain({"account": account, "artists": links})

    def _resolve(self, s, entry, data, known, refs, signatures):
        name = entry["entity_type"]
        for field in RESOURCES[name]["fields"]:
            key, target = field["name"], field.get("reference")
            if not target or data.get(key) is None:
                continue
            value = data[key]
            if isinstance(value, dict):
                ref = value.get("$ref")
                if ref not in refs or refs[ref]["entity_type"] != target:
                    raise DomainError(key + ": 연결된 초안 종류가 다르거나 없습니다.")
                if ref not in known:
                    raise DomainError("연결 순서를 해결할 수 없습니다.")
                value = known[ref]["id"]
                data[key] = value
                record = known[ref]["data"]
            else:
                record = self.get(s, target, value)
                signatures[target + ":" + str(value)] = digest(record)
            if record.get("archived_at"):
                raise DomainError(key + ": 보관된 자료는 새 연결에 사용할 수 없습니다.")
        return data

    def ordered(self, entries):
        refs = {e["client_ref"]: e for e in entries}
        if len(refs) != len(entries):
            raise DomainError("client_ref가 중복되었습니다.")
        result = []
        pending = list(entries)
        done = set()
        while pending:
            ready = [
                e
                for e in pending
                if all(
                    not isinstance(v, dict) or "$ref" not in v or v["$ref"] in done
                    for v in e["data"].values()
                )
            ]
            if not ready:
                raise DomainError("연결이 없거나 순환 참조가 있습니다.")
            for e in ready:
                result.append(e)
                done.add(e["client_ref"])
                pending.remove(e)
        return result

    def check_relations(self, s, name, data, lookup):
        def record(target, key):
            return lookup(target, data[key]) if data.get(key) is not None else None

        if name == "artist_group_members":
            if (
                record("artists", "group_id")["entity_kind"] != "group"
                or record("artists", "member_id")["entity_kind"] != "solo"
            ):
                raise DomainError("그룹과 개인 멤버를 각각 선택하세요.")
        if name == "performances":
            archive = record("live_archives", "archive_id")
            video = lookup("videos", archive["video_id"])
            length = video.get("duration_seconds")
            if (
                length is not None
                and max(data["start_seconds"], data.get("end_seconds") or 0) > length
            ):
                raise DomainError("가창 시점이 영상 길이를 넘었습니다.")
        if name == "artist_external_accounts" and data.get("is_primary"):
            account = record("external_accounts", "account_id")
            rows = s.execute(
                text(
                    """SELECT a.id FROM artist_external_accounts a JOIN external_accounts e ON e.id=a.account_id
                WHERE a.artist_id=:artist AND a.is_primary AND e.platform=:platform AND a.account_id<>:account"""
                ),
                {
                    "artist": data["artist_id"],
                    "platform": account["platform"],
                    "account": data["account_id"],
                },
            ).all()
            if rows:
                raise DomainError("같은 플랫폼의 대표 계정이 이미 있습니다.", 409)

    def preview(self, entries, catalog_id, initial):
        with self.session() as s:
            identity = self.identity(s)
            if str(identity["id"]) != str(catalog_id):
                raise DomainError("대상 DB가 변경되었습니다.", 409)
            if initial != (identity["initial_import_id"] is None):
                raise DomainError("초기 반영 상태가 바뀌었습니다.", 409)
            return self._prepare(s, entries, dry=True)

    def _prepare(self, s, entries, dry=False):
        seen_targets = set()
        for entry in entries:
            if entry["operation"] != "create":
                if entry["entity_type"] == "source_documents":
                    raise DomainError(
                        "원문은 수정할 수 없습니다. 새 원문으로 등록하세요."
                    )
                target = (entry["entity_type"], entry.get("target_id"))
                if target in seen_targets:
                    raise DomainError(
                        "같은 자료를 한 작업에서 두 번 수정할 수 없습니다."
                    )
                seen_targets.add(target)
                original = self.get(s, *target, lock=not dry)
                if self.version(s, target[0], original, lock=not dry) != entry.get(
                    "expected_version"
                ):
                    raise DomainError(
                        "다른 작업에서 수정된 자료입니다. 다시 불러오세요.", 409
                    )
        ordered = self.ordered(entries)
        refs = {e["client_ref"]: e for e in entries}
        known = {}
        signatures = {}
        changes = []
        synthetic = {}

        def lookup(target, key):
            if (target, key) in synthetic:
                return synthetic[target, key]
            r = self.get(s, target, key)
            signatures[target + ":" + str(key)] = digest(r)
            return r

        for index, e in enumerate(ordered):
            name = e["entity_type"]
            before = None
            if e["operation"] != "create":
                if not e.get("target_id") or not e.get("expected_version"):
                    raise DomainError("수정 대상과 기준 버전이 필요합니다.")
                before = self.get(s, name, e["target_id"])

                signatures[name + ":" + str(before["id"])] = digest(before)
                editable = {f["name"] for f in RESOURCES[name]["fields"]}
                data = {k: v for k, v in plain(before).items() if k in editable}
                data.update(e["data"])
            else:
                data = dict(e["data"])
            data = validate(name, data)
            data = self._resolve(s, e, data, known, refs, signatures)
            self.check_relations(s, name, data, lookup)
            values = generated(name, data)
            if e["operation"] in {"archive", "restore"}:
                if not RESOURCES[name]["archivable"]:
                    raise DomainError("보관할 수 없는 자료입니다.")
                values["archived_at"] = (
                    e["archive_time"] if e["operation"] == "archive" else None
                )
            if dry:
                key = e.get("target_id") or -(index + 1)
                record = {"id": key, **values}
                synthetic[name, key] = record
            else:
                params = {k: v for k, v in values.items()}
                for f in RESOURCES[name]["fields"]:
                    if params.get(f["name"]) is not None:
                        if f["type"] == "DATE":
                            params[f["name"]] = date.fromisoformat(params[f["name"]])
                        if f["type"] == "TIMESTAMPTZ":
                            params[f["name"]] = datetime.fromisoformat(
                                params[f["name"]]
                            )
                if before:
                    query = (
                        "UPDATE "
                        + name
                        + " SET "
                        + ",".join(k + "=:" + k for k in params)
                        + " WHERE id=:target RETURNING *"
                    )
                    params["target"] = before["id"]
                else:
                    query = (
                        "INSERT INTO "
                        + name
                        + " ("
                        + ",".join(params)
                        + ") VALUES ("
                        + ",".join(":" + k for k in params)
                        + ") RETURNING *"
                    )
                stmt = text(query)
                json_fields = {
                    f["name"] for f in ALL_COLUMNS[name] if f["type"] == "JSONB"
                }
                for key in json_fields & params.keys():
                    stmt = stmt.bindparams(bindparam(key, type_=JSONB))
                record = dict(s.execute(stmt, params).mappings().one())
                key = record["id"]
            known[e["client_ref"]] = {"id": key, "data": record}
            changes.append(
                {
                    "client_ref": e["client_ref"],
                    "entity_type": name,
                    "entity_id": key,
                    "before": plain(before),
                    "after": plain(record),
                    "operation": e["operation"],
                }
            )
        return {"changes": changes, "signatures": signatures}

    def receipt(self, operation_id):
        with self.session() as s:
            row = (
                s.execute(
                    text("SELECT * FROM catalog_imports WHERE operation_id=:id"),
                    {"id": operation_id},
                )
                .mappings()
                .first()
            )
            return plain(dict(row)) if row else None

    def publish(self, manifest, hash_value, operation_id):
        with self.session(write=True) as s:
            identity = self.identity(s, lock=True)
            if str(identity["id"]) != manifest["catalog_id"]:
                raise DomainError("대상 DB가 변경되었습니다.", 409)
            receipt = (
                s.execute(
                    text("SELECT * FROM catalog_imports WHERE operation_id=:id"),
                    {"id": operation_id},
                )
                .mappings()
                .first()
            )
            if receipt:
                if receipt["manifest_hash"] != hash_value:
                    raise DomainError("작업 ID의 내용이 다릅니다.", 409)
                return plain(dict(receipt))
            if manifest["initial"] != (identity["initial_import_id"] is None):
                raise DomainError("초기 반영 상태가 변경되었습니다.", 409)
            # Serialize cooperating writers through catalog_instance; compare every reviewed existing row.
            for key, expected in manifest["signatures"].items():
                name, id_value = key.split(":")
                if digest(self.get(s, name, int(id_value), lock=True)) != expected:
                    raise DomainError("미리보기 이후 연결 자료가 변경되었습니다.", 409)
            outcome = self._prepare(s, manifest["entries"])
            self.validate_graph(s)
            for change in outcome["changes"]:
                change["after"] = plain(
                    self.get(s, change["entity_type"], change["entity_id"])
                )
            mapping = [
                {
                    "client_ref": c["client_ref"],
                    "entity_type": c["entity_type"],
                    "entity_id": c["entity_id"],
                    "version": c["after"].get("version"),
                }
                for c in outcome["changes"]
            ]
            summary = {
                "created_count": sum(
                    c["operation"] == "create" for c in outcome["changes"]
                ),
                "updated_count": sum(
                    c["operation"] == "update" for c in outcome["changes"]
                ),
                "archived_count": sum(
                    c["operation"] in {"archive", "restore"} for c in outcome["changes"]
                ),
            }
            stmt = text(
                """INSERT INTO catalog_imports(operation_id,catalog_instance_id,manifest_hash,source_kind,result_mapping,result_summary)
                VALUES (:op,:catalog,:hash,:kind,:mapping,:summary) RETURNING *"""
            ).bindparams(
                bindparam("mapping", type_=JSONB), bindparam("summary", type_=JSONB)
            )
            receipt = dict(
                s.execute(
                    stmt,
                    {
                        "op": operation_id,
                        "catalog": identity["id"],
                        "hash": hash_value,
                        "kind": manifest.get("source_kind")
                        or (
                            "initial_import" if manifest["initial"] else "batch_import"
                        ),
                        "mapping": mapping,
                        "summary": summary,
                    },
                )
                .mappings()
                .one()
            )
            for change in outcome["changes"]:
                stmt = text(
                    """INSERT INTO catalog_changes(import_id,entity_type,entity_id,action,before_data,after_data,provenance)
                 VALUES (:receipt,:type,:id,:action,:before,:after,:provenance)"""
                ).bindparams(
                    bindparam("before", type_=JSONB(none_as_null=True)),
                    bindparam("after", type_=JSONB),
                    bindparam("provenance", type_=JSONB),
                )
                s.execute(
                    stmt,
                    {
                        "receipt": receipt["id"],
                        "type": change["entity_type"],
                        "id": change["entity_id"],
                        "action": change["operation"],
                        "before": change["before"],
                        "after": change["after"],
                        "provenance": {
                            "approved_hash": hash_value,
                            "source": next(
                                (
                                    e.get("provenance", {})
                                    for e in manifest["entries"]
                                    if e["client_ref"] == change["client_ref"]
                                ),
                                {},
                            ),
                        },
                    },
                )
            if manifest["initial"]:
                s.execute(
                    text(
                        "UPDATE catalog_instance SET initial_import_id=:id,initialized_at=clock_timestamp()"
                    ),
                    {"id": receipt["id"]},
                )
            return plain(receipt)

    def manual_save(self, request):
        entity = request.entity.model_dump(mode="json")
        manifest = {
            "catalog_id": str(request.catalog_id),
            "initial": False,
            "source_kind": "manual",
            "entries": [entity],
            "signatures": {},
        }
        return self.publish(manifest, digest(manifest), str(request.operation_id))

    def imports(self):
        with self.session() as s:
            rows = (
                s.execute(
                    text(
                        "SELECT id,operation_id,source_kind,result_summary,created_at FROM catalog_imports ORDER BY id DESC LIMIT 100"
                    )
                )
                .mappings()
                .all()
            )
            return plain([dict(r) for r in rows])

    def archive(self, name, key, request):
        # Stable timestamp is derived from the first receipt path only; retry compares stable request hash.
        from datetime import timezone

        operation = "archive" if request.archived else "restore"
        if name not in RESOURCES or not RESOURCES[name]["archivable"]:
            raise DomainError("보관할 수 없는 자료입니다.")
        request_data = {
            "catalog_id": str(request.catalog_id),
            "kind": name,
            "id": key,
            "version": request.expected_version,
            "operation": operation,
        }
        hash_value = digest(request_data)
        entry = {
            "client_ref": "manual:" + str(key),
            "entity_type": name,
            "operation": operation,
            "data": {},
            "target_id": key,
            "expected_version": request.expected_version,
            "archive_time": datetime.now(timezone.utc).isoformat(),
        }
        manifest = {
            "catalog_id": str(request.catalog_id),
            "initial": False,
            "source_kind": "manual",
            "entries": [entry],
            "signatures": {},
        }
        return self.publish(manifest, hash_value, str(request.operation_id))

    def validate_graph(self, s):
        # Cross-table rules are checked after the whole batch, so its insertion order cannot
        # reject a valid primary artist or a setlist reference created later in that batch.
        checks = [
            (
                "SELECT 1 FROM artist_group_members m JOIN artists g ON g.id=m.group_id JOIN artists a ON a.id=m.member_id WHERE g.entity_kind<>'group' OR a.entity_kind<>'solo' LIMIT 1",
                "그룹 소속이 있는 아티스트의 활동 형태를 변경할 수 없습니다.",
            ),
            (
                "SELECT 1 FROM artist_external_accounts a JOIN external_accounts e ON e.id=a.account_id WHERE a.is_primary GROUP BY a.artist_id,e.platform HAVING count(*)>1 LIMIT 1",
                "같은 플랫폼의 대표 계정은 아티스트마다 하나만 지정하세요.",
            ),
            (
                "SELECT 1 FROM performances p JOIN live_archives a ON a.id=p.archive_id JOIN videos v ON v.id=a.video_id WHERE v.duration_seconds IS NOT NULL AND (p.start_seconds>v.duration_seconds OR p.end_seconds>v.duration_seconds) LIMIT 1",
                "영상 길이보다 뒤에 있는 세트리스트 시점이 있습니다.",
            ),
            (
                "SELECT 1 FROM live_archives a WHERE a.primary_artist_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM archive_artists x WHERE x.archive_id=a.id AND x.artist_id=a.primary_artist_id) LIMIT 1",
                "대표 아티스트를 먼저 해당 라이브의 출연진으로 연결하세요. 묶음에서는 함께 반영할 수 있습니다.",
            ),
            (
                "SELECT 1 FROM performance_artists p JOIN performances x ON x.id=p.performance_id WHERE NOT EXISTS(SELECT 1 FROM archive_artists a WHERE a.archive_id=x.archive_id AND a.artist_id=p.artist_id) LIMIT 1",
                "가창 아티스트를 먼저 해당 라이브의 출연진으로 연결하세요.",
            ),
            (
                "SELECT 1 FROM performances p WHERE p.source_document_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM archive_sources a WHERE a.archive_id=p.archive_id AND a.document_id=p.source_document_id) LIMIT 1",
                "세트리스트의 근거 문서를 먼저 해당 라이브의 출처로 연결하세요.",
            ),
        ]
        for query, message in checks:
            if s.execute(text(query)).first():
                raise DomainError(message, 409)
