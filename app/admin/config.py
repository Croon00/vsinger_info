from dataclasses import dataclass
import os
from pathlib import Path

from app.core.config import Settings

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class AdminSettings:
    workspace: Path = ROOT / "db-migration" / "workspace"
    input_dir: Path = ROOT / "db-migration" / "input"
    dist: Path = ROOT / "admin-web" / "dist"
    database_url: str = ""
    catalog_instance_id: str | None = None
    origins: tuple[str, ...] = (
        "http://127.0.0.1:8010",
        "http://localhost:8010",
        "http://127.0.0.1:5176",
        "http://localhost:5176",
    )

    @classmethod
    def load(cls):
        common = Settings()
        return cls(
            workspace=Path(os.environ.get("ADMIN_WORKSPACE", str(cls.workspace))),
            input_dir=Path(os.environ.get("ADMIN_INPUT_DIR", str(cls.input_dir))),
            database_url=common.new_database_url or "",
            catalog_instance_id=common.new_database_instance_id,
        )
