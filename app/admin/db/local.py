from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import json
import sqlite3
import uuid


def now():
    return datetime.now(timezone.utc).isoformat()


def uid():
    return str(uuid.uuid4())


def pack(value):
    return json.dumps(value, ensure_ascii=False, default=str)


def unpack(value, default=None):
    return json.loads(value) if value is not None else default


class LocalStore:
    def __init__(self, workspace: Path):
        self.workspace = workspace
        workspace.mkdir(parents=True, exist_ok=True)
        (workspace / "snapshots").mkdir(exist_ok=True)
        self.path = workspace / "review.sqlite3"
        with self.connect() as conn:
            conn.executescript(
                Path(__file__).with_name("local.sql").read_text(encoding="utf-8")
            )

    @contextmanager
    def connect(self, write=False):
        c = sqlite3.connect(self.path, timeout=10)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys=ON")
        try:
            if write:
                c.execute("BEGIN IMMEDIATE")
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise
        finally:
            c.close()

    @staticmethod
    def insert(c, table, **values):
        values.setdefault("id", uid())
        values.setdefault("created_at", now())
        cols = {row["name"] for row in c.execute("PRAGMA table_info(" + table + ")")}
        if "updated_at" in cols:
            values.setdefault("updated_at", now())
        c.execute(
            "INSERT INTO "
            + table
            + " ("
            + ",".join(values)
            + ") VALUES ("
            + ",".join("?" for _ in values)
            + ")",
            list(values.values()),
        )
        return values["id"]

    @staticmethod
    def update(c, table, key, **values):
        values["updated_at"] = now()
        c.execute(
            "UPDATE "
            + table
            + " SET "
            + ",".join(v + "=?" for v in values)
            + " WHERE id=?",
            [*values.values(), key],
        )
