from dataclasses import dataclass
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class AdminSettings:
    workspace: Path = ROOT / "db-migration" / "workspace"
    input_dir: Path = ROOT / "db-migration" / "input"
    dist: Path = ROOT / "admin-web" / "dist"
    database_url: str = ""
    origins: tuple[str, ...] = (
        "http://127.0.0.1:8010",
        "http://localhost:8010",
        "http://127.0.0.1:5176",
        "http://localhost:5176",
    )

    @classmethod
    def load(cls):
        value = os.environ.get("NEW_CATALOG_DATABASE_URL", "")
        file = ROOT / ".env.catalog"
        if not value and file.exists():
            for line in file.read_text(encoding="utf-8-sig").splitlines():
                key, sep, candidate = line.partition("=")
                if sep and key.strip() == "NEW_CATALOG_DATABASE_URL":
                    value = candidate.strip()
        return cls(
            workspace=Path(os.environ.get("ADMIN_WORKSPACE", str(cls.workspace))),
            input_dir=Path(os.environ.get("ADMIN_INPUT_DIR", str(cls.input_dir))),
            database_url=value,
        )
