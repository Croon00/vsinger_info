import json
from sqlalchemy import text


def targets(session):
    return [dict(r) for r in session.execute(text("""SELECT v.platform_video_id, v.source_account_id account_id,e.platform_id channel_id
      FROM videos v JOIN external_accounts e ON e.id=v.source_account_id AND e.archived_at IS NULL
      LEFT JOIN collection_states cs ON cs.external_account_id=e.id
      WHERE v.platform='youtube' AND v.archived_at IS NULL
        AND v.availability IN ('public','unlisted','unknown')
        AND (EXISTS(SELECT 1 FROM covers c WHERE c.video_id=v.id AND c.archived_at IS NULL)
          OR EXISTS(SELECT 1 FROM recordings r WHERE r.official_video_id=v.id AND r.archived_at IS NULL))
        AND ((cs.provider_state->'youtube_video_statistics'->v.platform_video_id->>'captured_at') IS NULL
          OR (cs.provider_state->'youtube_video_statistics'->v.platform_video_id->>'captured_at')::timestamptz < now()-interval '24 hours')
      ORDER BY v.id LIMIT 10000""")).mappings()]


def persist(session, account, rows):
    session.execute(text("""INSERT INTO collection_states(external_account_id,provider_state)
      SELECT id,jsonb_build_object('youtube_video_statistics',CAST(:rows AS jsonb))
      FROM external_accounts WHERE id=:account AND platform='youtube' AND platform_id=:channel AND archived_at IS NULL
      ON CONFLICT (external_account_id) DO UPDATE SET provider_state=jsonb_set(collection_states.provider_state,
        '{youtube_video_statistics}',COALESCE(collection_states.provider_state->'youtube_video_statistics','{}'::jsonb)
          || (EXCLUDED.provider_state->'youtube_video_statistics'))"""),
      dict(account=account, channel=rows[0].channel_id,
           rows=json.dumps({r.video_id: r.model_dump(mode='json') for r in rows})))
