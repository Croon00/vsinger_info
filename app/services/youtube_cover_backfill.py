"""Resumable official-channel cover import into the unified catalog only."""
from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import re

from sqlalchemy import text

from app.db.catalog_session import catalog_runtime_session, verify_catalog_identity
from app.integrations.youtube_catalog import YouTubeClient, purpose
from app.repositories.youtube_cover_backfill import save_page as persist_page
from app.repositories.shared_youtube import SHARED_MEMBERS_CTE, SHARED_PARAMS, COVER_SOURCE_CHANNELS


class BudgetReached(Exception):
    pass


class BudgetClient(YouTubeClient):
    """Persist attempted requests before sending; cap this import over 24 hours."""
    def __init__(self, key, state, save, *, budget=1500, interval=2):
        super().__init__(key, interval=interval)
        self.state, self.save, self.budget = state, save, budget

    async def get(self, resource, **params):
        now = datetime.now(UTC).timestamp()
        attempts = [t for t in self.state.get('requests', []) if t > now - 86400]
        if len(attempts) >= self.budget:
            raise BudgetReached()
        self.state['requests'] = attempts + [now]
        self.save()
        return await super().get(resource, **params)


def targets(session):
    return [dict(r) for r in session.execute(text(f"""WITH {SHARED_MEMBERS_CTE} SELECT e.id,e.platform_id,
        string_agg(DISTINCT a.name_native, ', ' ORDER BY a.name_native) artists
        FROM external_accounts e JOIN artist_external_accounts ae ON ae.account_id=e.id
        JOIN artists a ON a.id=ae.artist_id
        WHERE e.platform='youtube' AND e.collection_enabled AND e.archived_at IS NULL
          AND ae.relationship='owner' AND a.archived_at IS NULL
          AND (a.show_in_catalog OR EXISTS(SELECT 1 FROM shared_members sm WHERE sm.group_id=a.id AND sm.account_id=e.id))
        GROUP BY e.id ORDER BY e.id"""), SHARED_PARAMS).mappings()]


def save_page(account, videos):
    with catalog_runtime_session() as session:
        # Official uploads playlists can contain videos published under a
        # separate music/member channel ID. Never rewrite their source ID.
        approved = next((channels for channels in COVER_SOURCE_CHANNELS.values()
                         if account['platform_id'] in channels), [account['platform_id']])
        sources = {a['platform_id']: a for a in targets(session)
                   if a['platform_id'] in approved}
        total = 0
        for channel, source in sources.items():
            selected = [v for v in videos if v.channel_id == channel and purpose(v) == 'cover']
            if selected:
                total += persist_page(session, source, selected)
        return total


async def backfill(key: str, checkpoint: Path, *, budget=1500, interval=2, max_pages=2000, account_ids=None, rescan_run=None):
    if not key:
        raise ValueError('YOUTUBE_API_KEY is not configured')
    if not 1 <= budget <= 5000 or interval < 1 or not 1 <= max_pages <= 10000:
        raise ValueError('Invalid request budget, interval or page limit')
    if rescan_run and not account_ids:
        raise ValueError('Rescans require explicit account IDs')
    # One import at a time, including when callers use different checkpoint paths.
    with catalog_runtime_session() as guard:
        if not guard.execute(text('SELECT pg_try_advisory_xact_lock(749203108)')).scalar_one():
            raise ValueError('A cover backfill is already running')
        instance = verify_catalog_identity(guard)
        accounts = targets(guard)
        if account_ids:
            accounts = [a for a in accounts if a['id'] in account_ids]
        state = json.loads(checkpoint.read_text(encoding='utf-8')) if checkpoint.exists() else {
            'catalog_id': instance, 'channels': {}, 'requests': []}
        if state.get('catalog_id') != instance:
            raise ValueError('Checkpoint belongs to another catalog')
        def save():
            checkpoint.parent.mkdir(parents=True, exist_ok=True)
            temporary = checkpoint.with_suffix('.tmp')
            temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
            temporary.replace(checkpoint)
        provider = BudgetClient(key, state, save, budget=budget, interval=interval)
        result = dict(channels=len(accounts), completed=0, covers_saved=0, pages=0,
                      missing_channel_ids=[], paused=False)
        for account in accounts:
            channel = account['platform_id'] or ''
            if not re.fullmatch(r'UC[A-Za-z0-9_-]{22}', channel):
                result['missing_channel_ids'].append(account['id'])
                continue
            progress = state['channels'].setdefault(channel, {})
            if rescan_run and progress.get('rescan_run') != rescan_run:
                progress.setdefault('rescan_history', []).append(dict(run=rescan_run,
                    previous_done=progress.get('done'), previous_token=progress.get('token'),
                    previous_pages=progress.get('pages',0), previous_covers_saved=progress.get('covers_saved',0)))
                progress.update(done=False,token=None,rescan_run=rescan_run)
                save()
            if progress.get('done'):
                result['completed'] += 1
                continue
            try:
                playlist = progress.get('playlist')
                if not playlist:
                    data = await provider.get('channels', part='contentDetails', id=channel)
                    items = data['items']
                    if not items or items[0]['id'] != channel:
                        raise ValueError('Registered channel unavailable')
                    playlist = items[0]['contentDetails']['relatedPlaylists']['uploads']
                    progress['playlist'] = playlist
                    save()
                for _ in range(max_pages):
                    data = await provider.get('playlistItems', part='contentDetails', playlistId=playlist,
                        maxResults=50, **({'pageToken': progress['token']} if progress.get('token') else {}))
                    ids = list(dict.fromkeys(item['contentDetails']['videoId'] for item in data['items']))
                    videos = await provider.videos(ids)
                    saved = save_page(account, videos)
                    result['covers_saved'] += saved
                    result['pages'] += 1
                    progress['pages'] = progress.get('pages', 0) + 1
                    progress['covers_saved'] = progress.get('covers_saved', 0) + saved
                    progress['token'] = data.get('nextPageToken')
                    progress['done'] = not bool(progress['token'])
                    save()
                    print(json.dumps(dict(account_id=account['id'], pages=progress['pages'],
                        covers_saved=progress['covers_saved'], done=progress['done'])), flush=True)
                    if progress['done']:
                        result['completed'] += 1
                        break
                if not progress.get('done'):
                    result['paused'] = True
            except BudgetReached:
                result['paused'] = True
                break
        return result
