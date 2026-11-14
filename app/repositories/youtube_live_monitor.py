"""Live-only leases/state in the unified DB; no queue or archive mutations."""
import json
from sqlalchemy import text


def claim(session, token, limit=25):
    session.execute(text('''INSERT INTO collection_states(external_account_id)
        SELECT id FROM external_accounts WHERE platform='youtube' AND collection_enabled
          AND archived_at IS NULL ON CONFLICT DO NOTHING'''))
    rows = session.execute(text('''SELECT e.id,e.platform_id channel_id,
        COALESCE(cs.provider_state->'youtube_live_monitor','{}'::jsonb) state,
        cs.provider_state->>'youtube_uploads_playlist' playlist,
        COALESCE(cs.provider_state->'youtube_pending_video_ids','[]'::jsonb) pending,
        COALESCE((cs.provider_state->'youtube_live_monitor'->>'next_discovery_at')::timestamptz,
                 '-infinity'::timestamptz) <= clock_timestamp() discover
        FROM external_accounts e JOIN collection_states cs ON cs.external_account_id=e.id
        WHERE e.platform='youtube' AND e.collection_enabled AND e.archived_at IS NULL
          AND e.platform_id ~ '^UC[A-Za-z0-9_-]{22}$'
          AND COALESCE((cs.provider_state->'youtube_live_monitor'->>'lease_until')::timestamptz,
                       '-infinity'::timestamptz) <= clock_timestamp()
          AND COALESCE((cs.provider_state->'youtube_live_monitor'->>'retry_at')::timestamptz,
                       '-infinity'::timestamptz) <= clock_timestamp()
          AND (COALESCE((cs.provider_state->'youtube_live_monitor'->>'next_discovery_at')::timestamptz,
                        '-infinity'::timestamptz) <= clock_timestamp()
            OR (jsonb_array_length(COALESCE(cs.provider_state->'youtube_live_monitor'->'candidate_ids','[]'::jsonb)) > 0
                AND COALESCE((cs.provider_state->'youtube_live_monitor'->>'next_check_at')::timestamptz,
                             '-infinity'::timestamptz) <= clock_timestamp()))
        ORDER BY cs.provider_state->'youtube_live_monitor'->>'next_check_at' NULLS FIRST,e.id
        FOR UPDATE OF cs SKIP LOCKED LIMIT :limit'''), {'limit': limit}).mappings().all()
    for row in rows:
        session.execute(text('''UPDATE collection_states SET provider_state=jsonb_set(provider_state,
            '{youtube_live_monitor}',COALESCE(provider_state->'youtube_live_monitor','{}'::jsonb)
              || jsonb_build_object('lease_token',CAST(:token AS text),'lease_until',clock_timestamp()+interval '180 seconds'))
            WHERE external_account_id=:id'''), {'id': row['id'], 'token': token})
    return [dict(row) for row in rows]


def save(session, account, token, state, snapshot):
    # Account identity and lease are rechecked after the network read.
    return session.execute(text('''UPDATE collection_states cs SET provider_state=
        jsonb_set(jsonb_set(cs.provider_state,'{youtube_live_monitor}',CAST(:state AS jsonb)),
                  '{youtube_live_snapshot}',CAST(:snapshot AS jsonb))
        FROM external_accounts e WHERE e.id=cs.external_account_id AND e.id=:id
          AND e.platform='youtube' AND e.platform_id=:channel AND e.collection_enabled AND e.archived_at IS NULL
          AND cs.provider_state->'youtube_live_monitor'->>'lease_token'=:token
          AND (cs.provider_state->'youtube_live_monitor'->>'lease_until')::timestamptz > clock_timestamp()
        RETURNING e.id'''), dict(id=account['id'], channel=account['channel_id'], token=token,
                                state=json.dumps(state), snapshot=json.dumps(snapshot))).scalar_one_or_none() is not None


def defer(session, token, *, seconds=60, all_accounts=False, account_id=None):
    # Global quota/Retry-After failures pause all discovery/status requests.
    session.execute(text('''UPDATE collection_states SET provider_state=jsonb_set(provider_state,
        '{youtube_live_monitor}',
        (COALESCE(provider_state->'youtube_live_monitor','{}'::jsonb)-'lease_token'-'lease_until')
        || jsonb_build_object('retry_at',clock_timestamp()+(:seconds * interval '1 second')))
        WHERE (:all_accounts OR provider_state->'youtube_live_monitor'->>'lease_token'=:token)
          AND (CAST(:account_id AS integer) IS NULL OR external_account_id=:account_id)
          AND external_account_id IN (SELECT id FROM external_accounts WHERE platform='youtube')'''),
        dict(token=token, seconds=max(1, seconds), all_accounts=all_accounts, account_id=account_id))
