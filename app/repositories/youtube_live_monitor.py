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
        WHERE e.platform='youtube' AND e.archived_at IS NULL
          AND (e.collection_enabled OR (cs.provider_state @> '{"youtube_live_only": true}'
               AND EXISTS (SELECT 1 FROM artist_external_accounts ae JOIN artists a ON a.id=ae.artist_id
                           WHERE ae.account_id=e.id AND ae.relationship='owner'
                             AND a.entity_kind='group' AND a.archived_at IS NULL)))
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
          AND e.platform='youtube' AND e.platform_id=:channel AND e.archived_at IS NULL
          AND (e.collection_enabled OR (cs.provider_state @> '{"youtube_live_only": true}'
               AND EXISTS (SELECT 1 FROM artist_external_accounts ae JOIN artists a ON a.id=ae.artist_id
                           WHERE ae.account_id=e.id AND ae.relationship='owner'
                             AND a.entity_kind='group' AND a.archived_at IS NULL)))
          AND cs.provider_state->'youtube_live_monitor'->>'lease_token'=:token
          AND (cs.provider_state->'youtube_live_monitor'->>'lease_until')::timestamptz > clock_timestamp()
        RETURNING e.id'''), dict(id=account['id'], channel=account['channel_id'], token=token,
                                state=json.dumps(state), snapshot=json.dumps(snapshot))).scalar_one_or_none() is not None


def defer(session, token, *, seconds=60, all_accounts=False, account_id=None, namespace='youtube_live_monitor'):
    # Global quota/Retry-After failures pause all discovery/status requests.
    session.execute(text('''UPDATE collection_states SET provider_state=jsonb_set(provider_state,
        ARRAY[CAST(:namespace AS text)],
        (COALESCE(provider_state->:namespace,'{}'::jsonb)-'lease_token'-'lease_until')
        || jsonb_build_object('retry_at',clock_timestamp()+(:seconds * interval '1 second')))
        WHERE (:all_accounts OR provider_state->:namespace->>'lease_token'=:token)
          AND (CAST(:account_id AS integer) IS NULL OR external_account_id=:account_id)
          AND external_account_id IN (SELECT id FROM external_accounts WHERE platform='youtube')'''),
        dict(token=token, seconds=max(1, seconds), all_accounts=all_accounts, account_id=account_id, namespace=namespace))


def claim_holodex(session, token, limit=500, *, poll_seconds=3600, live_check_seconds=180):
    """Separate provider lease/retry; YouTube quota never blocks Holodex reads."""
    session.execute(text('''INSERT INTO collection_states(external_account_id)
        SELECT id FROM external_accounts WHERE platform='youtube' AND collection_enabled
          AND archived_at IS NULL ON CONFLICT DO NOTHING'''))
    discovery_due = """(COALESCE((cs.provider_state->'holodex_live_monitor'->>'next_check_at')::timestamptz,
                       '-infinity'::timestamptz) <= clock_timestamp()
          AND (cs.provider_state->'youtube_live_snapshot'->>'provider' IS DISTINCT FROM 'holodex'
               OR COALESCE((cs.provider_state->'youtube_live_snapshot'->>'checked_at')::timestamptz,
                           '-infinity'::timestamptz) + (:poll_seconds * interval '1 second') <= clock_timestamp()))"""
    rows = session.execute(text(f'''WITH due AS (SELECT e.id,e.platform_id channel_id,
        COALESCE(cs.provider_state->'holodex_live_monitor','{{}}'::jsonb) state,
        COALESCE(cs.provider_state->'youtube_live_snapshot','{{}}'::jsonb) snapshot,
        {discovery_due} discover
        FROM external_accounts e JOIN collection_states cs ON cs.external_account_id=e.id
        WHERE e.platform='youtube' AND e.archived_at IS NULL
          AND (e.collection_enabled OR cs.provider_state @> '{{"youtube_live_only": true}}')
          AND e.platform_id ~ '^UC[A-Za-z0-9_-]{{22}}$'
          AND EXISTS (SELECT 1 FROM artist_external_accounts ae JOIN artists a ON a.id=ae.artist_id
                      WHERE ae.account_id=e.id AND a.archived_at IS NULL
                        AND (a.show_in_catalog OR (a.entity_kind='group' AND ae.relationship='owner'
                            AND cs.provider_state @> '{{"youtube_live_only": true}}')))
          AND COALESCE((cs.provider_state->'holodex_live_monitor'->>'lease_until')::timestamptz,
                       '-infinity'::timestamptz) <= clock_timestamp()
          AND COALESCE((cs.provider_state->'holodex_live_monitor'->>'retry_at')::timestamptz,
                       '-infinity'::timestamptz) <= clock_timestamp()
          AND ({discovery_due}
            OR (cs.provider_state->'youtube_live_snapshot'->>'provider'='holodex'
                AND (jsonb_array_length(COALESCE(cs.provider_state->'youtube_live_snapshot'->'streams','[]'::jsonb)) > 0
                     OR EXISTS (SELECT 1 FROM jsonb_to_recordset(
                         COALESCE(cs.provider_state->'youtube_live_snapshot'->'upcoming','[]'::jsonb)
                       ) AS pending(scheduled_at timestamptz)
                       WHERE pending.scheduled_at <= clock_timestamp()))
                AND COALESCE((cs.provider_state->'holodex_live_monitor'->>'next_live_check_at')::timestamptz,
                             '-infinity'::timestamptz) <= clock_timestamp()
                AND COALESCE((cs.provider_state->'youtube_live_snapshot'->>'live_checked_at')::timestamptz,
                             (cs.provider_state->'youtube_live_snapshot'->>'checked_at')::timestamptz,
                             '-infinity'::timestamptz) + (:live_check_seconds * interval '1 second') <= clock_timestamp()))
        ORDER BY cs.provider_state->'holodex_live_monitor'->>'next_check_at' NULLS FIRST,e.id
        FOR UPDATE OF cs SKIP LOCKED LIMIT :limit)
        UPDATE collection_states cs SET provider_state=jsonb_set(cs.provider_state,
            '{{holodex_live_monitor}}',COALESCE(cs.provider_state->'holodex_live_monitor','{{}}'::jsonb)
              || jsonb_build_object('lease_token',CAST(:token AS text),'lease_until',clock_timestamp()+interval '180 seconds'))
        FROM due WHERE cs.external_account_id=due.id
        RETURNING due.id,due.channel_id,due.state,due.snapshot,due.discover'''),
        {'limit': limit, 'token': token, 'poll_seconds': poll_seconds, 'live_check_seconds': live_check_seconds}).mappings().all()
    return [dict(row) for row in rows]


def save_holodex_batch(session, token, updates):
    """One transaction/query; revalidate ownership of every provider lease."""
    return set(session.execute(text('''UPDATE collection_states cs SET provider_state=
        jsonb_set(jsonb_set(cs.provider_state,'{holodex_live_monitor}',x.state),
                  '{youtube_live_snapshot}',x.snapshot)
        FROM jsonb_to_recordset(CAST(:updates AS jsonb))
             AS x(id bigint,channel_id text,state jsonb,snapshot jsonb), external_accounts e
        WHERE e.id=x.id AND cs.external_account_id=e.id
          AND e.platform='youtube' AND e.platform_id=x.channel_id AND e.archived_at IS NULL
          AND (e.collection_enabled OR cs.provider_state @> '{"youtube_live_only": true}')
          AND EXISTS (SELECT 1 FROM artist_external_accounts ae JOIN artists a ON a.id=ae.artist_id
                      WHERE ae.account_id=e.id AND a.archived_at IS NULL
                        AND (a.show_in_catalog OR (a.entity_kind='group' AND ae.relationship='owner'
                            AND cs.provider_state @> '{"youtube_live_only": true}')))
          AND cs.provider_state->'holodex_live_monitor'->>'lease_token'=:token
          AND (cs.provider_state->'holodex_live_monitor'->>'lease_until')::timestamptz > clock_timestamp()
        RETURNING e.id'''), dict(token=token, updates=json.dumps(updates))).scalars())
