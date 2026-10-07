"""Apply the two user-requested, official-source affiliation corrections."""
import argparse
import hashlib
import json
import uuid

import psycopg
from psycopg.types.json import Jsonb

from scripts.migrate_catalog import configure_transaction, load_connection

ITEMS = [
    {'id': 1004, 'slug': 'nakamachi-arale', 'agency': 'BanG Dream!',
     'source_url': 'https://bang-dream.com/artist/yumemita/nakamachi-arale/'},
    {'id': 991, 'slug': 'machita-chima', 'agency': '\u306b\u3058\u3055\u3093\u3058',
     'source_url': 'https://www.nijisanji.jp/talents/l/chima-machita'},
]


def apply(conn, write=False):
    identity = conn.execute('SELECT id::text,schema_version FROM catalog_instance').fetchone()
    if not identity or identity[1] != 'catalog-v2':
        raise ValueError('Unexpected catalog identity')
    changes, plans = [], []
    if write:
        conn.execute('SELECT pg_advisory_xact_lock(731064923)')
    for item in ITEMS:
        artist = conn.execute('SELECT to_jsonb(a) FROM artists a WHERE id=%s AND slug=%s AND archived_at IS NULL',
                              (item['id'], item['slug'])).fetchone()
        if not artist:
            raise ValueError('Artist identity mismatch')
        before = artist[0]
        agencies = conn.execute('SELECT id FROM agencies WHERE name_native=%s AND archived_at IS NULL',
                                (item['agency'],)).fetchall()
        if len(agencies) > 1:
            raise ValueError('Ambiguous affiliation')
        agency = agencies[0][0] if agencies else None
        plan = {'artist_id': item['id'], 'slug': item['slug'], 'agency': item['agency'],
                'action': 'unchanged' if agency and before['agency_id'] == agency else 'update'}
        plans.append(plan)
        if not write or plan['action'] == 'unchanged':
            continue
        if agency is None:
            agency, after = conn.execute('INSERT INTO agencies(name_native) VALUES (%s) RETURNING id,to_jsonb(agencies)',
                                         (item['agency'],)).fetchone()
            changes.append(('agencies', agency, 'create', None, after, item))
        after = conn.execute('UPDATE artists SET agency_id=%s,version=version+1,updated_at=clock_timestamp() WHERE id=%s RETURNING to_jsonb(artists)',
                             (agency, item['id'])).fetchone()[0]
        changes.append(('artists', item['id'], 'update', before, after, item))
    if changes:
        digest = hashlib.sha256(json.dumps(ITEMS, sort_keys=True).encode()).hexdigest()
        operation = uuid.uuid5(uuid.NAMESPACE_URL, identity[0] + 'requested-affiliations-2026-10-07:' + digest)
        receipt = conn.execute("""INSERT INTO catalog_imports(operation_id,catalog_instance_id,manifest_hash,source_kind,result_mapping,result_summary)
            VALUES (%s,%s,%s,'correction',%s,%s) RETURNING id""",
            (operation, identity[0], digest, Jsonb(plans), Jsonb({'changes': len(changes)}))).fetchone()[0]
        for table, key, action, before, after, item in changes:
            conn.execute('INSERT INTO catalog_changes(import_id,entity_type,entity_id,action,before_data,after_data,provenance) VALUES (%s,%s,%s,%s,%s,%s,%s)',
                         (receipt, table, key, action, Jsonb(before) if before is not None else None, Jsonb(after), Jsonb({'source_url': item['source_url'], 'policy': 'requested-affiliations-2026-10-07'})))
    return {'status': 'applied' if write else 'dry_run', 'changes': len(changes), 'plans': plans}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    with psycopg.connect(load_connection(), connect_timeout=20) as conn:
        configure_transaction(conn, read_only=not args.apply)
        result = apply(conn, args.apply)
        if not args.apply:
            conn.rollback()
    print(json.dumps(result))
