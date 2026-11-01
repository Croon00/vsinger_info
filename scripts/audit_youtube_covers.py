"""Explicit fair full-channel cover rescan with bounded metadata follow-ups.

Reuses the existing checkpoint and rolling request budget. Dry-run by default.
Does not enable disabled accounts, change ownership or send notifications.
"""
import argparse
import asyncio
from datetime import UTC, datetime
import json
from pathlib import Path
import re
import sys
import time
from sqlalchemy.exc import OperationalError, DisconnectionError
from sqlalchemy import text

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.core.config import settings
from app.db.catalog_session import catalog_runtime_session, verify_catalog_identity
from app.integrations.youtube_catalog import YouTubeFailure
from app.services.youtube_cover_backfill import backfill, targets, BudgetClient, BudgetReached, save_checkpoint
from app.repositories.youtube_video_format import targets as format_targets
from app.repositories.youtube_video_format import SHORT_MARKER
from app.repositories.youtube_cover_rules import COVER_TITLE_SQL, COVER_TITLE_PARAMS
from scripts.refresh_youtube_video_statistics import main as refresh_views
from scripts.classify_youtube_cover_formats import main as classify_formats


def save_state(path,state):
    save_checkpoint(path,state)


async def run(args):
    with catalog_runtime_session() as session:
        accounts=targets(session,include_disabled=args.include_disabled)
        identity=verify_catalog_identity(session)
    ids=[a['id'] for a in accounts]
    print(json.dumps(dict(targets=len(ids),run=args.run,apply=args.apply)),flush=True)
    if not args.apply:
        return
    failures=0
    bootstrap_followups=args.checkpoint.exists()
    async def followups():
        # Include explicitly registered publisher accounts added during an audit.
        with catalog_runtime_session() as session:
            ids[:]=[a['id'] for a in targets(session,include_disabled=args.include_disabled)]
        state=json.loads(args.checkpoint.read_text(encoding='utf-8'))
        if state.get('catalog_id')!=identity:
            raise ValueError('Checkpoint belongs to another catalog')
        provider=BudgetClient(settings.youtube_api_key,state,lambda:save_state(args.checkpoint,state),
                              budget=args.budget,interval=args.interval)
        await refresh_views(ids,provider=provider)
        await classify_formats(ids,max_checks=100)
        with catalog_runtime_session() as session:
            pending=sum(r['account_id'] in ids for r in format_targets(session))
            unknown=session.execute(text(f"""SELECT count(*) FROM covers c JOIN videos v ON v.id=c.video_id
              LEFT JOIN collection_states cs ON cs.external_account_id=v.source_account_id
              WHERE v.source_account_id=ANY(CAST(:accounts AS integer[])) AND c.archived_at IS NULL
                AND v.archived_at IS NULL AND v.availability IN ('public','unlisted','unknown')
                AND (v.duration_seconds<=180 OR v.duration_seconds IS NULL)
                AND v.title !~* :short_marker AND {COVER_TITLE_SQL}
                AND cs.provider_state->'youtube_video_formats'->v.platform_video_id->>'is_short' IS NULL"""),
              {'accounts':ids,'short_marker':SHORT_MARKER,**COVER_TITLE_PARAMS}).scalar_one()
        print(json.dumps(dict(stage='followups',pending_format_checks=pending,unknown_formats=unknown)),flush=True)
        return pending,state,unknown
    while True:
        try:
            if bootstrap_followups:
                await followups()
                bootstrap_followups=False
            result=await backfill(settings.youtube_api_key,args.checkpoint,budget=args.budget,
                interval=args.interval,max_pages=1,account_ids=ids,rescan_run=args.run,
                rescan_all=True,include_disabled=args.include_disabled)
            print(json.dumps(dict(stage='uploads',**result)),flush=True)
            pending,state,unknown=await followups()
            if result['completed']==len(ids) and not pending:
                print(json.dumps(dict(stage='complete' if not unknown else 'uploads_complete_formats_unresolved',
                    unknown_formats=unknown,channels=len(ids),run=args.run)),flush=True)
                return
            failures=0
            # If uploads used the budget, follow-ups may still be empty. Wait
            # for that same recorded budget rather than creating a new ledger.
            recent=[t for t in state.get('requests',[]) if t>time.time()-86400]
            delay=max(1,min(recent)+86400-time.time()+1) if len(recent)>=args.budget else 1
        except (BudgetReached,YouTubeFailure) as exc:
            state=json.loads(args.checkpoint.read_text(encoding='utf-8'))
            recent=[t for t in state.get('requests',[]) if t>time.time()-86400]
            if isinstance(exc,YouTubeFailure):
                if not exc.retry:raise
                delay=max(60,exc.retry_after)
            else:
                delay=max(1,min(recent)+86400-time.time()+1)
            print(json.dumps(dict(stage='budget_or_provider_wait',seconds=round(delay))),flush=True)
        except Exception as exc:
            if isinstance(exc,ValueError):raise
            failures+=1
            print(json.dumps(dict(stage='retry',error=type(exc).__name__,attempt=failures,
                sqlstate=getattr(getattr(exc,'orig',None),'sqlstate',None),winerror=getattr(exc,'winerror',None))),flush=True)
            if failures>=3:raise
            delay=30 if isinstance(exc,(OperationalError,DisconnectionError,PermissionError)) else 3600
        # Background runner remains interruptible; no blocking long sleep.
        deadline=time.monotonic()+delay
        while time.monotonic()<deadline:
            await asyncio.sleep(min(30,deadline-time.monotonic()))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--include-disabled',action='store_true')
    parser.add_argument('--run',default='all-covers-'+datetime.now(UTC).strftime('%Y-%m-%d'))
    parser.add_argument('--checkpoint',type=Path,default=Path('.tmp/youtube-cover-backfill.json'))
    parser.add_argument('--budget',type=int,default=1500)
    parser.add_argument('--interval',type=float,default=2)
    args=parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9._-]{1,80}',args.run):parser.error('Invalid run label')
    if not 1<=args.budget<=5000 or args.interval<1:parser.error('Invalid budget or interval')
    try:asyncio.run(run(args))
    except Exception as exc:
        print(json.dumps(dict(stage='stopped',error=type(exc).__name__)),flush=True)
        return 1
    return 0

if __name__=='__main__':raise SystemExit(main())
