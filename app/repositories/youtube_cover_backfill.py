"""Batch cover persistence; preserve owners, removals, live archives and raw sources."""
from datetime import UTC, datetime
import hashlib
import json

from sqlalchemy import text
from app.integrations.youtube_cover_rules import is_cover_title
from app.integrations.youtube_catalog import purpose
from app.repositories.shared_youtube import SHARED_MEMBERS_CTE, SHARED_PARAMS


def save_page(session, account, videos):
    videos = [video for video in videos if video.channel_id == account['platform_id']
              and is_cover_title(video.title) and purpose(video)=='cover']
    active = session.execute(text(f"""WITH {SHARED_MEMBERS_CTE} SELECT e.id FROM external_accounts e
      WHERE e.id=:id AND e.platform='youtube' AND e.platform_id=:platform_id
        AND e.collection_enabled AND e.archived_at IS NULL
        AND EXISTS (SELECT 1 FROM artist_external_accounts ae JOIN artists a ON a.id=ae.artist_id
          WHERE ae.account_id=e.id AND ae.relationship='owner' AND a.archived_at IS NULL
            AND (a.show_in_catalog OR EXISTS(SELECT 1 FROM shared_members sm WHERE sm.group_id=a.id AND sm.account_id=e.id)))
      FOR SHARE OF e"""), {**account, **SHARED_PARAMS}).scalar_one_or_none()
    if active is None:
        raise ValueError('Account disabled or ownership changed during import')
    if not videos:
        return 0
    rows = [dict(external=v.id, title=v.title, published=v.published_at.isoformat() if v.published_at else None,
                 duration=v.duration_seconds, availability=v.availability,
                 completed_music_premiere=bool(v.started_at and v.ended_at and
                     v.duration_seconds and v.duration_seconds<=900 and purpose(v)=='cover')) for v in videos]
    params = dict(account=account['id'], rows=json.dumps(rows))
    # Same ordered video locks as the normal collector; no absent-row race.
    session.execute(text("""SELECT pg_advisory_xact_lock(hashtextextended(x.external,941203))
      FROM jsonb_to_recordset(CAST(:rows AS jsonb)) x(external text) ORDER BY x.external"""), params)
    session.execute(text("""INSERT INTO videos(platform,platform_video_id,source_account_id,title,
        published_at,duration_seconds,availability)
      SELECT 'youtube',x.external,:account,x.title,x.published,x.duration,x.availability
      FROM jsonb_to_recordset(CAST(:rows AS jsonb))
        x(external text,title text,published timestamptz,duration integer,availability text)
      ON CONFLICT (platform,platform_video_id) DO NOTHING"""), params)
    # Fill only absent provenance after the caller verifies the video's exact
    # channel ID. Never replace a previously assigned source or archive record.
    session.execute(text("""UPDATE videos v SET source_account_id=:account
      FROM jsonb_to_recordset(CAST(:rows AS jsonb)) x(external text)
      WHERE v.platform='youtube' AND v.platform_video_id=x.external
        AND v.source_account_id IS NULL AND v.archived_at IS NULL"""), params)
    added = session.execute(text("""INSERT INTO covers(video_id)
      SELECT v.id FROM videos v JOIN jsonb_to_recordset(CAST(:rows AS jsonb)) x(external text,completed_music_premiere boolean)
        ON v.platform_video_id=x.external
      WHERE v.platform='youtube' AND v.source_account_id=:account AND v.archived_at IS NULL
        AND (x.completed_music_premiere OR NOT EXISTS (SELECT 1 FROM live_archives l WHERE l.video_id=v.id))
      ON CONFLICT (video_id) DO NOTHING RETURNING video_id"""), params).scalars().all()
    if not added:
        return 0
    external_ids = set(session.execute(text('SELECT platform_video_id FROM videos WHERE id=ANY(:ids)'),
                                       {'ids': added}).scalars())
    documents = []
    for video in videos:
        if video.id not in external_ids:
            continue
        metadata = dict(collector='youtube-cover-backfill', video=video.model_dump(mode='json'),
                        attribution='channel_owner_catalog_only', extractor='cover-title-v3')
        canonical = json.dumps(dict(kind='video_description', external_id=video.id,
            content=video.description, metadata=metadata), sort_keys=True, ensure_ascii=False, separators=(',', ':'))
        documents.append(dict(url=f'https://www.youtube.com/watch?v={video.id}', external=video.id,
            content=video.description or None, hash=hashlib.sha256(canonical.encode()).hexdigest(), metadata=metadata))
    session.execute(text("""INSERT INTO source_documents(source_kind,source_url,external_id,captured_at,
        content_text,content_hash,source_metadata)
      SELECT 'video_description',x.url,x.external,:captured,x.content,x.hash,x.metadata
      FROM jsonb_to_recordset(CAST(:documents AS jsonb))
        x(url text,external text,content text,hash text,metadata jsonb)
      WHERE NOT EXISTS (SELECT 1 FROM source_documents d WHERE d.content_hash=x.hash)"""),
      dict(documents=json.dumps(documents, ensure_ascii=False), captured=datetime.now(UTC)))
    return len(added)
