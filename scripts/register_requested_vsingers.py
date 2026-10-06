"""Register reviewed request channels in the unified catalog; dry-run by default.

Preserves existing identities, names and ownership. Does not run collection or notify.
The ambiguous MiRan channel is excluded until the user confirms its identity.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import uuid
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.migrate_catalog import configure_transaction, load_connection

SEED = ROOT / 'data/seeds/requested_vsingers_2026_10_02.json'
POLICY = 'requested-vsingers-2026-10-03-registration-v1'


def register(conn, items, *, write=False):
    identity = conn.execute('SELECT id::text,schema_version FROM catalog_instance').fetchone()
    revisions = [r[0] for r in conn.execute('SELECT version FROM catalog_schema_migrations ORDER BY version')]
    if not identity or identity[1] != 'catalog-v2' or revisions != [f'{n:03}' for n in range(1, 8)]:
        raise ValueError('Unexpected catalog identity or revision')
    if write:
        conn.execute('SELECT pg_advisory_xact_lock(%s)', (731064923,))
    plans, changes = [], []

    def record(table, key, before, after, item):
        changes.append((table, key, 'update' if before else 'create', before, after,
                        {'policy': POLICY, 'channel_url': item['channel_url'],
                         'affiliation_source_url': item.get('affiliation_source_url')}))

    for item in items:
        if item['slug'] == 'miran':
            plans.append({'slug': 'miran', 'action': 'awaiting_channel_confirmation'})
            continue
        if not re.fullmatch(r'UC[A-Za-z0-9_-]{22}', item['channel_id']):
            raise ValueError('Invalid channel ID')
        artists = conn.execute('SELECT id,to_jsonb(a) FROM artists a WHERE slug=%s OR name_native=%s',
                               (item['slug'], item['name_native'])).fetchall()
        accounts = conn.execute("SELECT id,to_jsonb(e) FROM external_accounts e WHERE platform='youtube' AND (platform_id=%s OR url=%s)",
                                (item['channel_id'], item['channel_url'])).fetchall()
        if len(artists) > 1 or len(accounts) > 1:
            raise ValueError('Multiple identities: ' + item['slug'])
        artist = artists[0] if artists else None
        account = accounts[0] if accounts else None
        if artist and (artist[1]['slug'] != item['slug'] or artist[1]['name_native'] != item['name_native'] or artist[1]['archived_at']):
            raise ValueError('Conflicting artist: ' + item['slug'])
        if account and (account[1]['platform_id'] != item['channel_id'] or account[1]['archived_at']):
            raise ValueError('Conflicting account: ' + item['slug'])
        owners = conn.execute("SELECT artist_id FROM artist_external_accounts WHERE account_id=%s AND relationship='owner'", (account[0],)).fetchall() if account else []
        if owners and (not artist or any(r[0] != artist[0] for r in owners)):
            raise ValueError('Conflicting owner: ' + item['slug'])
        agency = None
        if item.get('agency') and item['agency'] != '개인세' and item['affiliation_status'] == 'verified':
            rows = conn.execute('SELECT id FROM agencies WHERE name_native=%s AND archived_at IS NULL', (item['agency'],)).fetchall()
            if len(rows) > 1:
                raise ValueError('Multiple agencies')
            agency = rows[0][0] if rows else None
            if artist and artist[1]['agency_id'] and artist[1]['agency_id'] != agency:
                raise ValueError('Conflicting affiliation: ' + item['slug'])
            if write and not agency:
                agency, after = conn.execute('INSERT INTO agencies(name_native) VALUES (%s) RETURNING id,to_jsonb(agencies)', (item['agency'],)).fetchone()
                record('agencies', agency, None, after, item)
        plan = {'slug': item['slug'], 'action': 'reuse' if artist else 'create',
                'agency': item.get('agency') if item['affiliation_status'] == 'verified' else None}
        plans.append(plan)
        if not write:
            continue
        if not artist:
            artist = conn.execute("INSERT INTO artists(slug,name_native,name_ko,entity_kind,is_virtual,show_in_catalog,agency_id) VALUES (%s,%s,%s,'solo',true,true,%s) RETURNING id,to_jsonb(artists)",
                                  (item['slug'], item['name_native'], item['name_ko'], agency)).fetchone()
            record('artists', artist[0], None, artist[1], item)
        elif not artist[1]['show_in_catalog'] or not artist[1]['name_ko'] or (agency and not artist[1]['agency_id']):
            after = conn.execute('UPDATE artists SET show_in_catalog=true,name_ko=COALESCE(name_ko,%s),agency_id=COALESCE(agency_id,%s),updated_at=clock_timestamp(),version=version+1 WHERE id=%s RETURNING to_jsonb(artists)',
                                 (item['name_ko'], agency, artist[0])).fetchone()[0]
            record('artists', artist[0], artist[1], after, item)
        if not account:
            account = conn.execute("INSERT INTO external_accounts(platform,platform_id,url,collection_enabled) VALUES ('youtube',%s,%s,false) RETURNING id,to_jsonb(external_accounts)",
                                   (item['channel_id'], item['channel_url'])).fetchone()
            record('external_accounts', account[0], None, account[1], item)
        if not owners:
            key, after = conn.execute("INSERT INTO artist_external_accounts(artist_id,account_id,relationship,is_primary,position) VALUES (%s,%s,'owner',true,0) RETURNING id,to_jsonb(artist_external_accounts)", (artist[0], account[0])).fetchone()
            record('artist_external_accounts', key, None, after, item)
        plan.update(artist_id=artist[0], account_id=account[0])
    if changes:
        digest = hashlib.sha256(json.dumps(items, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        operation = uuid.uuid5(uuid.NAMESPACE_URL, identity[0] + POLICY + digest)
        import_id = conn.execute("INSERT INTO catalog_imports(operation_id,catalog_instance_id,manifest_hash,source_kind,result_mapping,result_summary) VALUES (%s,%s,%s,'manual',%s,%s) RETURNING id",
                                 (operation, identity[0], digest, Jsonb(plans), Jsonb({'policy': POLICY, 'changes': len(changes)}))).fetchone()[0]
        for table, key, action, before, after, provenance in changes:
            conn.execute('INSERT INTO catalog_changes(import_id,entity_type,entity_id,action,before_data,after_data,provenance) VALUES (%s,%s,%s,%s,%s,%s,%s)',
                         (import_id, table, key, action, Jsonb(before) if before else None, Jsonb(after), Jsonb(provenance)))
    return {'status': 'committed' if changes else ('no_changes' if write else 'dry_run'), 'changes': len(changes), 'plans': plans}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    items = json.loads(SEED.read_text(encoding='utf-8'))['artists']
    with psycopg.connect(load_connection(), connect_timeout=20) as conn:
        configure_transaction(conn, read_only=not args.apply)
        result = register(conn, items, write=args.apply)
        if not args.apply:
            conn.rollback()
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
