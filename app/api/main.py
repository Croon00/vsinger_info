"""FastAPI lifecycle and unified catalog router composition."""
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers.read_api import router as catalog_router
from app.core.config import settings
from app.schemas.worker_jobs import WorkerReadiness
from app.services.worker_readiness import inspect_readiness


app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "HEAD", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    """Report process liveness without touching either database."""
    return {"status": "ok"}


@app.get('/ready', response_model=WorkerReadiness)
async def ready(response: Response) -> WorkerReadiness:
    result = await inspect_readiness()
    response.status_code = 200 if result.ready else 503
    return result


# `/api` is canonical. `/api/v2` remains a hidden compatibility alias until
# phase 6 removes temporary aliases after deployed consumers are verified.
app.include_router(catalog_router, prefix="/api")
app.include_router(catalog_router, prefix="/api/v2", include_in_schema=False)
