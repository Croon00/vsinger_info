import json
from sqlalchemy import text

SHORT_MARKER = r'(^|[^a-z])shorts([^a-z]|$)|#short([^a-z]|$)|#ショート|#숏츠'
SHORT_VISIBILITY = """v.title !~* :short_marker
  AND COALESCE((cs.provider_state->'youtube_video_formats'->v.platform_video_id->>'is_short')::boolean,false)=false
  AND (v.duration_seconds>180 OR (cs.provider_state->'youtube_video_formats'->v.platform_video_id->>'is_short')::boolean=false)"""


def targets(session):
    return [dict(r) for r in session.execute(text("""SELECT v.platform_video_id,e.id account_id,
      v.title ~* :marker marked FROM covers c JOIN videos v ON v.id=c.video_id
      JOIN external_accounts e ON e.id=v.source_account_id AND e.archived_at IS NULL
      LEFT JOIN collection_states cs ON cs.external_account_id=e.id
      WHERE c.archived_at IS NULL AND v.archived_at IS NULL AND v.platform='youtube'
        AND v.availability IN ('public','unlisted','unknown')
        AND (v.duration_seconds<=180 OR v.duration_seconds IS NULL OR v.title ~* :marker)
        AND (cs.provider_state->'youtube_video_formats'->v.platform_video_id IS NULL
          OR ((cs.provider_state->'youtube_video_formats'->v.platform_video_id->>'is_short') IS NULL
            AND (cs.provider_state->'youtube_video_formats'->v.platform_video_id->>'captured_at')::timestamptz < now()-interval '24 hours'))
      ORDER BY (v.title ~* :marker) DESC,v.id LIMIT 10000"""), {'marker': SHORT_MARKER}).mappings()]


def persist(session, account, rows):
    session.execute(text("""INSERT INTO collection_states(external_account_id,provider_state)
      SELECT id,jsonb_build_object('youtube_video_formats',CAST(:rows AS jsonb))
      FROM external_accounts WHERE id=:account AND platform='youtube' AND archived_at IS NULL
      ON CONFLICT (external_account_id) DO UPDATE SET provider_state=jsonb_set(collection_states.provider_state,
        '{youtube_video_formats}',COALESCE(collection_states.provider_state->'youtube_video_formats','{}'::jsonb)
          || (EXCLUDED.provider_state->'youtube_video_formats'))"""),dict(account=account,rows=json.dumps(rows)))
