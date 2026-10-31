"""Refresh metadata in the existing provider namespace without disturbing leases."""
import json
from sqlalchemy import text


def targets(session, *, include_disabled=False):
    return [dict(r) for r in session.execute(text("""SELECT DISTINCT e.id,e.platform_id
      FROM external_accounts e JOIN artist_external_accounts ae ON ae.account_id=e.id
      JOIN artists a ON a.id=ae.artist_id WHERE e.platform='youtube'
      AND (e.collection_enabled OR :include_disabled) AND e.archived_at IS NULL AND ae.relationship='owner'
      AND a.archived_at IS NULL AND a.show_in_catalog AND e.platform_id ~ '^UC[A-Za-z0-9_-]{22}$'
      ORDER BY e.id"""), {'include_disabled': include_disabled}).mappings()]


def persist(session, account, statistics, *, include_disabled=False):
    session.execute(text("""INSERT INTO collection_states(external_account_id,provider_state)
      SELECT id,jsonb_build_object('youtube_channel_statistics',CAST(:statistics AS jsonb))
      FROM external_accounts WHERE id=:account AND platform='youtube' AND platform_id=:channel
        AND (collection_enabled OR :include_disabled) AND archived_at IS NULL
      ON CONFLICT (external_account_id) DO UPDATE SET
        provider_state=collection_states.provider_state || EXCLUDED.provider_state"""),
      dict(account=account, channel=statistics.channel_id, include_disabled=include_disabled,
           statistics=json.dumps(statistics.model_dump(mode='json'))))
