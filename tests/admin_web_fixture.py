"""Browser-test server: private scratch SQLite; no Neon URL is loaded."""

from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.admin.config import AdminSettings, ROOT
from app.admin.main import create_app
from app.admin.db.remote import RemoteCatalog


def create_fixture():
    scratch = Path(tempfile.mkdtemp(prefix="admin-browser-", dir=ROOT / ".tmp"))
    settings = AdminSettings(
        workspace=scratch / "workspace", input_dir=scratch / "input"
    )
    return create_app(settings, RemoteCatalog(""))
