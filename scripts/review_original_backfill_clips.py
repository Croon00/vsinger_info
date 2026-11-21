"""Reversibly exclude exact promotional clips created by this backfill only."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
from uuid import NAMESPACE_URL, uuid5

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import text
from app.db.catalog_session import catalog_runtime_session, verify_catalog_identity

CLIPS = {'odqQuGTTNM0', 'Mip3el6hTmA', 'BmBtdmxKG20', 'eu7yNWotliM',
         'S0ZM8if6MQw', 'NqLiTA2so-I', 'SgPGJ1iZQ_c', 'yxNfJTxydDA', 'BXFxER1CNS4'}
POLICY = 'original-backfill-20261122-promotion-review-1'


def run(apply=False):
    with catalog_runtime_session() as s:
        identity = verify_catalog_identity(s)
        s.execute(text('SELECT pg_advisory_xact_lock(731064923)'))
        operation = str(uuid5(NAMESPACE_URL, identity + POLICY))
        if s.execute(text('SELECT 1 FROM catalog_imports WHERE operation_id=:op'), {'op': operation}).first():
            return {'already_applied': True}
        changes = []
        for external in sorted(CLIPS):
            before = dict(s.execute(text('''SELECT r.* FROM recordings r JOIN videos v ON v.id=r.official_video_id
                WHERE v.platform='youtube' AND v.platform_video_id=:external FOR UPDATE OF r'''),
                {'external': external}).mappings().one())
            created = s.execute(text('''SELECT c.after_data FROM catalog_changes c JOIN catalog_imports i ON i.id=c.import_id
                WHERE c.entity_type='recordings' AND c.entity_id=:id AND c.action='create'
                AND i.result_summary->>'policy' IN ('youtube-original-evidence-1','youtube-original-evidence-2')
                AND EXISTS(SELECT 1 FROM worker_jobs j WHERE j.id=(i.result_summary->>'job_id')::bigint
                    AND j.payload->>'request_run'='original-backfill-2026-11-22')'''), {'id': before['id']}).scalar_one()
            credits = s.execute(text('SELECT count(*) FROM recording_artists WHERE recording_id=:id'), {'id': before['id']}).scalar_one()
            # catalog_touch_parent increments once per inserted vocal credit.
            unchanged = all(str(before.get(k)) == str(v) for k, v in created.items()
                            if k not in ('version', 'created_at', 'updated_at'))
            if before['archived_at'] or before['version'] != created['version'] + credits or not unchanged:
                raise ValueError('Post-import modification preserved')
            changes.append((external, before))
        if not apply:
            return {'clips_to_archive': len(changes)}
        proof = {'policy': POLICY, 'reason': 'Promotional/shortened clip; preserve source and exclude from full-song list',
                 'video_ids': sorted(CLIPS)}
        receipt = s.execute(text('''INSERT INTO catalog_imports(operation_id,catalog_instance_id,manifest_hash,
            source_kind,result_mapping,result_summary) VALUES (:op,:instance,:hash,'manual',CAST(:mapping AS jsonb),
            CAST(:proof AS jsonb)) RETURNING id'''),
            {'op': operation, 'instance': identity, 'hash': hashlib.sha256(json.dumps(proof).encode()).hexdigest(),
             'mapping': json.dumps([{'entity_type': 'recordings', 'id': b['id']} for _, b in changes]),
             'proof': json.dumps(proof)}).scalar_one()
        for external, before in changes:
            after = dict(s.execute(text('''UPDATE recordings SET archived_at=clock_timestamp(),
                updated_at=clock_timestamp(),version=version+1 WHERE id=:id RETURNING *'''), {'id': before['id']}).mappings().one())
            s.execute(text('''INSERT INTO catalog_changes(import_id,entity_type,entity_id,action,before_data,after_data,provenance)
                VALUES (:receipt,'recordings',:id,'update',CAST(:before AS jsonb),CAST(:after AS jsonb),CAST(:proof AS jsonb))'''),
                {'receipt': receipt, 'id': before['id'], 'before': json.dumps(before, default=str),
                 'after': json.dumps(after, default=str), 'proof': json.dumps({**proof, 'source_url': 'https://www.youtube.com/watch?v='+external})})
        return {'archived_clips': len(changes), 'receipt': receipt}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    print(json.dumps(run(parser.parse_args().apply)))
