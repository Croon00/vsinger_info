"""Resumable full official-upload audit and evidence-only original registration."""
from __future__ import annotations
import argparse
import asyncio
from collections import Counter
from datetime import UTC, datetime
import json
from pathlib import Path
import re
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import httpx
from sqlalchemy import text
from app.core.config import settings
from app.db.catalog_session import get_catalog_session, catalog_runtime_session, verify_catalog_identity
from app.integrations.youtube_catalog import YouTubeClient, YouTubeFailure, Video
from app.integrations.youtube_cover_rules import is_cover_title
from app.repositories import worker_jobs, youtube_collection as repository
from app.repositories.youtube_original import scope
from app.services.youtube_original import decide, ORIGINAL, EXCLUDED, POLICY
from app.schemas.worker_jobs import JobRequest
from app.services import music_jobs

RUN = 'original-backfill-2026-11-22'
STREAM = re.compile(r'歌枠|歌配信|karaoke|カラオケ|雑談|実況|耐久|配信|ゲーム|gameplay|minecraft|マイクラ|ASMR', re.I)


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, default=str), encoding='utf-8')
    temporary.replace(path)


def read_scope():
    it = get_catalog_session()
    session = next(it)
    try:
        identity = verify_catalog_identity(session)
        accounts = [dict(r) for r in session.execute(text('''SELECT e.id,e.platform_id,
            string_agg(DISTINCT a.name_native,' · ' ORDER BY a.name_native) artists,
            count(DISTINCT r.official_video_id) linked
            FROM external_accounts e JOIN artist_external_accounts ae ON ae.account_id=e.id AND ae.relationship='owner'
            JOIN artists a ON a.id=ae.artist_id AND a.archived_at IS NULL
            LEFT JOIN recording_artists ra ON ra.artist_id=a.id
            LEFT JOIN recordings r ON r.id=ra.recording_id AND r.archived_at IS NULL
            WHERE e.platform='youtube' AND e.archived_at IS NULL AND e.collection_enabled
              AND (a.show_in_catalog OR EXISTS(SELECT 1 FROM artist_group_members gm
                   JOIN artists member ON member.id=gm.member_id WHERE gm.group_id=a.id
                   AND gm.left_on IS NULL AND member.archived_at IS NULL AND member.show_in_catalog))
            GROUP BY e.id ORDER BY linked,e.id''')).mappings()]
        linked = set(session.execute(text('''SELECT v.platform_video_id FROM videos v JOIN recordings r
            ON r.official_video_id=v.id WHERE v.platform='youtube' ''')).scalars())
    finally:
        it.close()
    return identity, accounts, linked


def seed_cache(output, channels):
    old_path = ROOT / 'outputs/discography-youtube-2026-10-11/channel-cache.json'
    old = json.loads(old_path.read_text(encoding='utf-8')) if old_path.exists() else {}
    for channel in channels:
        path = output / 'channels' / f'{channel}.json'
        if not path.exists() and channel in old and old[channel].get('done'):
            data = old[channel]
            save(path, dict(items=data['items'], history_complete=True, playlist=data.get('playlist'),
                            head_complete=False, token=None, pages=0, cached_history=True))
    # Reviewed channel research already contains complete title/ID inventories.
    for path in (ROOT / 'db-migration/reports').glob('*/*.json'):
        if path.stat().st_size > 30_000_000:
            continue
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
        except (ValueError, UnicodeError):
            continue
        if not isinstance(data, dict) or not data.get('listing_complete') or data.get('channel_id') not in channels:
            continue
        channel = data['channel_id']
        dest = output / 'channels' / f'{channel}.json'
        if not dest.exists() and isinstance(data.get('uploads'), list):
            items = [dict(id=x['video_id'], title=x['title'], channel_id=channel,
                          description='', published_at=x.get('published_at')) for x in data['uploads']]
            save(dest, dict(items=items, history_complete=True, head_complete=False,
                            token=None, pages=0, cached_history=True))


class BudgetStop(Exception):
    pass


class Client(YouTubeClient):
    def __init__(self, args, state):
        super().__init__(settings.youtube_api_key,
                         transport=httpx.AsyncHTTPTransport() if args.direct_connect else None,
                         interval=1)
        self.args, self.state = args, state

    async def get(self, resource, **params):
        now = datetime.now(UTC).timestamp()
        stop = self.state.get('provider_stop')
        if stop:
            stopped_at = datetime.fromisoformat(stop['at']).timestamp()
            if now < stopped_at + max(float(stop.get('retry_after', 0)), 60):
                raise BudgetStop()
            self.state.pop('provider_stop', None)
        self.state['requests'] = [t for t in self.state.get('requests', []) if t > now-86400]
        if len(self.state['requests']) >= self.args.budget:
            raise BudgetStop()
        self.state['requests'].append(now)
        save(self.args.output / 'checkpoint.json', self.state)
        return await super().get(resource, **params)


def candidate(item):
    title = item['title']
    if is_cover_title(title) or EXCLUDED.search(title):
        return False
    return bool(ORIGINAL.search(title)) or not STREAM.search(title)


def apply_video(account, video, decision, identity):
    request = JobRequest(job_type='youtube_collect', external_account_id=account['id'], payload=dict(
        channel_id=account['platform_id'], youtube_video_id=video.id, purpose='original',
        request_run=RUN, extraction_version='original-backfill2-20261122'))
    with catalog_runtime_session() as session:
        if verify_catalog_identity(session) != identity:
            raise ValueError('Catalog identity changed')
        job_id = worker_jobs.enqueue(session, request)
        claimed = session.execute(text('''UPDATE worker_jobs SET status='running',attempt_count=attempt_count+1,
            lease_owner=:owner,lease_expires_at=clock_timestamp()+interval '10 minutes',finished_at=NULL,last_error=NULL
            WHERE id=:id AND status IN ('pending','retry') AND attempt_count<max_attempts
            RETURNING *'''), {'id': job_id, 'owner': RUN+'-'+str(uuid4())}).mappings().one_or_none()
        if not claimed:
            return {'status': 'already_processed', 'job_id': job_id}
        # Enqueue/claim/persist commit together, so old unrelated workers never
        # see a pending new-purpose job from this explicit backfill.
        job = worker_jobs.Job(claimed['id'], claimed['job_type'], claimed['external_account_id'],
                             claimed['video_id'], claimed['payload'], claimed['attempt_count'],
                             claimed['max_attempts'], claimed['lease_owner'])
        before = repository.snapshot(session, video.id, lock=True)
        existed = session.execute(text('''SELECT r.id FROM recordings r JOIN videos v ON v.id=r.official_video_id
            WHERE v.platform='youtube' AND v.platform_video_id=:id'''), {'id': video.id}).first()
        value = dict(snapshot=before, captured_at=datetime.now(UTC), video=video, rows=[], comment=None,
                     extractor=POLICY, outcome='collected', original=decision.model_dump())
        handler = music_jobs.Handler(lambda *_: None, repository.persist_collect)
        music_jobs._persist(session, job, request.parsed_payload(), value, handler)
        found = session.execute(text('''SELECT r.id FROM recordings r JOIN videos v ON v.id=r.official_video_id
            WHERE v.platform='youtube' AND v.platform_video_id=:id AND r.archived_at IS NULL'''), {'id': video.id}).first()
        return {'status': 'registered' if found and not existed else 'preserved_or_review',
                'job_id': job_id, 'recording_id': found[0] if found else None}


async def main(args):
    identity, accounts, linked = read_scope()
    if args.account:
        accounts = [a for a in accounts if a['id'] in args.account]
    channels = {a['platform_id'] for a in accounts}
    seed_cache(args.output, channels)
    checkpoint = args.output / 'checkpoint.json'
    state = json.loads(checkpoint.read_text(encoding='utf-8')) if checkpoint.exists() else {'catalog_id': identity, 'requests': []}
    if state['catalog_id'] != identity:
        raise ValueError('Checkpoint belongs to another catalog')
    provider = Client(args, state)
    summary = Counter()
    print(json.dumps({'status': 'started', 'accounts': len(accounts), 'already_linked': len(linked), 'apply': args.apply}), flush=True)
    try:
        for index, account in enumerate(accounts, 1):
            channel = account['platform_id']
            path = args.output / 'channels' / f'{channel}.json'
            cache = json.loads(path.read_text(encoding='utf-8')) if path.exists() else dict(
                items=[], history_complete=False, head_complete=False, pages=0, token=None)
            old_ids = {x['id'] for x in cache['items']} if cache.get('cached_history') else set()
            if not cache.get('playlist'):
                response = await provider.get('channels', part='contentDetails', id=channel)
                if not response['items']:
                    summary['unavailable_channels'] += 1
                    continue
                cache['playlist'] = response['items'][0]['contentDetails']['relatedPlaylists']['uploads']
            while not cache['head_complete']:
                if cache['pages'] >= args.max_pages:
                    raise BudgetStop()
                response = await provider.get('playlistItems', part='snippet,contentDetails', playlistId=cache['playlist'],
                    maxResults=50, **({'pageToken': cache['token']} if cache['token'] else {}))
                items = []
                for item in response['items']:
                    snippet = item['snippet']
                    if snippet.get('videoOwnerChannelId', channel) != channel:
                        continue
                    items.append(dict(id=item['contentDetails']['videoId'], title=snippet['title'],
                                      description=snippet.get('description', ''), channel_id=channel))
                overlap = bool(old_ids & {x['id'] for x in items})
                existing = {x['id']: x for x in cache['items']}
                existing.update({x['id']: x for x in items})
                cache.update(items=list(existing.values()), token=response.get('nextPageToken'), pages=cache['pages']+1,
                             head_complete=overlap or not response.get('nextPageToken'))
                if not response.get('nextPageToken'):
                    cache['history_complete'] = True
                save(path, cache)
            summary['channels_scanned'] += 1
            summary['uploads_checked'] += len(cache['items'])
            ids = [x['id'] for x in cache['items'] if x['id'] not in linked and candidate(x)]
            detail_path = args.output / 'details' / f'{channel}.json'
            details = json.loads(detail_path.read_text(encoding='utf-8')) if detail_path.exists() else {}
            missing = [external for external in ids if external not in details]
            for offset in range(0, len(missing), 50):
                batch = missing[offset:offset+50]
                values = await provider.videos(batch)
                details.update({external: None for external in batch})
                details.update({v.id: v.model_dump(mode='json') for v in values})
                save(detail_path, details)
            it = get_catalog_session()
            session = next(it)
            try:
                current_scope = scope(session, account['id'])
            finally:
                it.close()
            results = []
            for external in ids:
                if not details.get(external):
                    continue
                video = Video.model_validate(details[external])
                if video.channel_id != channel:
                    summary['foreign_publisher'] += 1
                    continue
                decision = decide(video, current_scope)
                result = {'id': video.id, 'title': video.title, 'status': decision.status, 'reason': decision.reason,
                          'artist_ids': decision.artist_ids, 'recording_id': decision.recording_id}
                summary[decision.status] += 1
                if args.apply and decision.status in ('new_original', 'link_recording'):
                    applied = await asyncio.to_thread(apply_video, account, video, decision, identity)
                    result['application'] = applied
                    summary[applied['status']] += 1
                    if applied['status'] == 'registered':
                        linked.add(video.id)
                results.append(result)
            save(args.output / 'results' / f'{channel}.json', {'account': account, 'history_complete': cache['history_complete'],
                 'uploads': len(cache['items']), 'results': results})
            print(json.dumps({'channel_done': index, 'total': len(accounts), 'account': account['id'],
                              'artists': account['artists'], 'uploads': len(cache['items']), 'candidates': len(ids),
                              'summary': dict(summary)}, ensure_ascii=True), flush=True)
    except BudgetStop:
        summary['stopped_budget_or_page_limit'] += 1
    except YouTubeFailure as exc:
        state['provider_stop'] = {'reason': exc.reason, 'retry_after': exc.retry_after, 'at': datetime.now(UTC).isoformat()}
        save(checkpoint, state)
        summary['stopped_'+exc.reason] += 1
    save(args.output / 'summary.json', {'run': RUN, 'accounts': len(accounts), 'summary': dict(summary),
         'requests_last_24h': len(state['requests']), 'finished_at': datetime.now(UTC).isoformat()})
    print(json.dumps({'status': 'finished_or_checkpointed', 'summary': dict(summary), 'requests_last_24h': len(state['requests'])}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--direct-connect', action='store_true')
    parser.add_argument('--account', type=int, action='append')
    parser.add_argument('--budget', type=int, choices=range(1, 5001), default=3000)
    parser.add_argument('--max-pages', type=int, choices=range(1, 1001), default=400)
    parser.add_argument('--output', type=Path, default=ROOT/'outputs'/RUN)
    args = parser.parse_args()
    try:
        asyncio.run(main(args))
    except Exception as exc:
        print(json.dumps({'stopped': type(exc).__name__}), flush=True)
        raise SystemExit(1) from None
