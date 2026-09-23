"""Read-only operational status; never starts or claims a job."""
from datetime import UTC, datetime

from app.core.config import settings
from app.schemas.worker_jobs import WorkerReadiness
from app.services.music_jobs import readiness


async def inspect_readiness() -> WorkerReadiness:
    enabled = settings.runtime_cutover_enabled and settings.agent_enabled
    try:
        data = await readiness()
    except Exception:
        return WorkerReadiness(ready=False, database_verified=False, workers_enabled=enabled)
    workers = data['local_workers']
    missing = []
    active = data['active_accounts']
    if active.get('youtube', 0) and not settings.youtube_api_key:
        missing.append('YOUTUBE_API_KEY')
    if active.get('spotify', 0) and not settings.spotify_client_id:
        missing.append('SPOTIFY_CLIENT_ID')
    if active.get('spotify', 0) and not settings.spotify_client_secret:
        missing.append('SPOTIFY_CLIENT_SECRET')
    healthy = True
    if enabled:
        for name in ('music-youtube', 'music-spotify'):
            state = workers.get(name, {})
            stamp = state.get('heartbeat_at')
            if (not stamp or state.get('state') not in ('idle', 'running')
                    or (datetime.now(UTC) - datetime.fromisoformat(stamp)).total_seconds() > 60):
                healthy = False
    return WorkerReadiness(
        ready=not enabled or (healthy and not data['unimplemented_handlers'] and not missing),
        database_verified=True, workers_enabled=enabled,
        registered_handlers=data['registered_handlers'],
        unimplemented_handlers=data['unimplemented_handlers'], workers=workers,
        missing_credentials=missing,
        optional_features={'youtube_setlist_llm': bool(settings.openai_api_key)},
        active_accounts=active,
        queue=data['queue'],
    )
