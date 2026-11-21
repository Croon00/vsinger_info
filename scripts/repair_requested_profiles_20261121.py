"""Repair exactly the user-requested names and missing 512px avatars; dry-run by default."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sqlalchemy import text
import httpx
from app.db.catalog_session import get_catalog_session, catalog_runtime_session, verify_catalog_identity
from app.services.avatar_assets import CACHE_CONTROL
from app.services.avatar_storage import variants, storage

NAMES = {
    1041: ('otonose-raco', '오토노세 라코'),
    1044: ('suiu-shino', '스이우 시노'),
    1045: ('nibiiro-yurushi', '니비이로 유루시'),
    1046: ('yayamugi', '아야무기'),
}
AVATARS = {941: 'figaro', 942: 'shin-vsinger'}
POLICY = 'requested-profile-repair-2026-11-21-v1'


def run(write=False):
    sessions = get_catalog_session()
    session = next(sessions)
    try:
        rows = {r['id']: dict(r) for r in session.execute(text(
            'SELECT * FROM artists WHERE id=ANY(:ids) AND archived_at IS NULL'),
            {'ids': list(NAMES) + list(AVATARS)}).mappings()}
    finally:
        sessions.close()
    for key, slug in {**{i: v[0] for i, v in NAMES.items()}, **AVATARS}.items():
        if rows.get(key, {}).get('slug') != slug:
            raise ValueError('Artist identity mismatch')
    names = [{'id': i, 'slug': slug, 'before': rows[i]['name_ko'], 'after': name}
             for i, (slug, name) in NAMES.items()]
    for item in names:
        if item['before'] not in (None, '', item['after']):
            raise ValueError('Existing Korean name conflict')
    repairs = []
    client = None
    with httpx.Client(timeout=20, trust_env=False) as http:
        for key in AVATARS:
            url = rows[key]['avatar_url']
            parsed = urlsplit(url)
            bucket, object_key = parsed.path.lstrip('/').split('/', 1)
            if bucket != 'avator-image' or not object_key.startswith(f'avatars/v1/{key}/') or not object_key.endswith('/512.webp'):
                raise ValueError('Unexpected managed avatar identity')
            base = url.rsplit('/', 1)[0]
            original = http.get(base + '/original')
            original.raise_for_status()
            generated = variants(original.content)
            for size in (128, 256):
                existing = http.get(base + f'/{size}.webp')
                existing.raise_for_status()
                if existing.content != generated[size]:
                    raise ValueError('Stored original does not reproduce existing variants')
            current = http.get(url)
            if current.status_code not in (200, 404):
                raise ValueError('Unexpected avatar response')
            missing = current.status_code == 404
            if not missing and current.content != generated[512]:
                raise ValueError('Existing 512px image conflict')
            if write and missing:
                if client is None:
                    client, _ = storage()
                endpoint = urlsplit(client.meta.endpoint_url)
                if endpoint.scheme != parsed.scheme or endpoint.netloc != parsed.netloc:
                    raise ValueError('Storage endpoint mismatch')
                client.put_object(Bucket=bucket, Key=object_key, Body=generated[512],
                                  ContentType='image/webp', CacheControl=CACHE_CONTROL, IfNoneMatch='*')
                verified = http.get(url)
                verified.raise_for_status()
                if verified.content != generated[512] or verified.headers.get('cache-control') != CACHE_CONTROL:
                    raise ValueError('Public avatar verification failed')
            repairs.append({'artist_id': key, 'url': url, 'missing_before': missing,
                            'bytes': len(generated[512]), 'sha256': sha256(generated[512]).hexdigest(),
                            'original_matches_existing_variants': True})
    result = {'policy': POLICY, 'status': 'applied' if write else 'dry_run', 'names': names, 'avatars': repairs}
    if not write:
        return result
    with catalog_runtime_session() as session:
        session.execute(text('SELECT pg_advisory_xact_lock(731064923)'))
        identity = verify_catalog_identity(session)
        operation = str(uuid.uuid5(uuid.NAMESPACE_URL, identity + POLICY))
        prior = session.execute(text('SELECT id FROM catalog_imports WHERE operation_id=:op'), {'op': operation}).scalar_one_or_none()
        if prior:
            return {**result, 'already_applied': True, 'receipt_id': prior}
        changes = []
        for key, previous in rows.items():
            current = dict(session.execute(text('SELECT * FROM artists WHERE id=:id FOR UPDATE'), {'id': key}).mappings().one())
            if current != previous:
                raise ValueError('Concurrent artist change; rerun preview')
            if key not in NAMES or current['name_ko'] == NAMES[key][1]:
                continue
            after = dict(session.execute(text('UPDATE artists SET name_ko=:name,version=version+1,updated_at=clock_timestamp() WHERE id=:id RETURNING *'),
                                         {'id': key, 'name': NAMES[key][1]}).mappings().one())
            changes.append((key, current, after))
        result['name_changes'] = len(changes)
        digest = sha256(json.dumps({'names': NAMES, 'avatars': AVATARS}, sort_keys=True).encode()).hexdigest()
        receipt = session.execute(text("INSERT INTO catalog_imports(operation_id,catalog_instance_id,manifest_hash,source_kind,result_mapping,result_summary) VALUES (:op,:identity,:hash,'correction','[]'::jsonb,CAST(:summary AS jsonb)) RETURNING id"),
                                  {'op': operation, 'identity': identity, 'hash': digest, 'summary': json.dumps(result, ensure_ascii=False)}).scalar_one()
        for key, before, after in changes:
            session.execute(text("INSERT INTO catalog_changes(import_id,entity_type,entity_id,action,before_data,after_data,provenance) VALUES (:receipt,'artists',:id,'update',CAST(:before AS jsonb),CAST(:after AS jsonb),CAST(:proof AS jsonb))"),
                            {'receipt': receipt, 'id': key, 'before': json.dumps(before, default=str), 'after': json.dumps(after, default=str),
                             'proof': json.dumps({'policy': POLICY, 'source': '2026-11-21 user-supplied Korean name'})})
        result['receipt_id'] = receipt
    report = ROOT / '.tmp' / 'requested-profile-repair-2026-11-21.json'
    report.parent.mkdir(exist_ok=True)
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    try:
        print(json.dumps(run(args.apply), ensure_ascii=False))
    except Exception as exc:
        # Avoid printing credential-bearing SDK request details.
        print(json.dumps({'status': 'failed', 'error_type': type(exc).__name__}))
        raise SystemExit(1) from None
