"""Run the local catalog admin without starting the legacy service or workers."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if __name__ == "__main__":
    if not (ROOT / "admin-web/dist/index.html").is_file():
        raise SystemExit(
            "Build the frontend first: cd admin-web; npm ci; npm run build"
        )
    import uvicorn

    uvicorn.run(
        "app.admin.main:create_app",
        factory=True,
        host="127.0.0.1",
        port=8010,
        proxy_headers=False,
        access_log=False,
    )
