"""Apply explicit, source-backed singer assignments; never infer from hosts.

Default is read-only validation. --apply adds missing assignments with atomic
receipts and per-row provenance, preserving existing credits and changed rows.
No collectors, external providers, or legacy database are called.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from collections import Counter, defaultdict
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.db.catalog_session import catalog_runtime_session, get_catalog_session, verify_catalog_identity

NAMESPACE = uuid.UUID('c9bd38d7-d5e1-47c3-ad39-08588b881c21')
BUCKET_SIZE = 1000


class Credit(BaseModel):
    model_config = ConfigDict(extra='forbid')
    artist_id: int = Field(gt=0)
    role: Literal['lead', 'guest']
    position: int = Field(ge=0, le=99)


class Evidence(BaseModel):
    model_config = ConfigDict(extra='forbid')
    basis: str = Field(min_length=1)
    song_basis: str = Field(min_length=1)
    review_status: Literal['contextual', 'source_row_verified']
    source_url: str = Field(pattern=r'^https://www\.youtube\.com/watch\?v=')
    video_title: str = Field(min_length=1)
    source_line: str = Field(min_length=1)


class Assignment(BaseModel):
    model_config = ConfigDict(extra='forbid')
    performance_id: int = Field(gt=0)
    performance_version: int = Field(gt=0)
    archive_id: int = Field(gt=0)
    archive_version: int = Field(gt=0)
    video_id: int = Field(gt=0)
    video_version: int = Field(gt=0)
    source_account_id: int = Field(gt=0)
    channel_id: str = Field(pattern=r'^UC[A-Za-z0-9_-]{22}$')
    source_document_id: int = Field(gt=0)
    source_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    artists: list[Credit] = Field(min_length=1, max_length=100)
    evidence: Evidence

    @model_validator(mode='after')
    def unique_credits(self):
        if len({a.artist_id for a in self.artists}) != len(self.artists):
            raise ValueError('Duplicate singer credit')
        if len({a.position for a in self.artists}) != len(self.artists):
            raise ValueError('Duplicate singer position')
        if self.evidence.review_status == 'contextual' and len(self.artists) != 1:
            raise ValueError('Contextual solo attribution requires one singer')
        return self


class Manifest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    policy: str = Field(min_length=1, max_length=120)
    catalog_instance_id: uuid.UUID
    snapshot_at: str
    links: list[Assignment]

    @model_validator(mode='after')
    def unique_performances(self):
        if len({a.performance_id for a in self.links}) != len(self.links):
            raise ValueError('Duplicate performance assignment')
        return self


def mapped(session, sql, **params):
    return [dict(r) for r in session.execute(text(sql), params).mappings()]


def buckets(entries: list[Assignment]):
    """Never split an archive: inserting credits increments its parent version."""
    grouped=defaultdict(list)
    for entry in sorted(entries,key=lambda e:e.performance_id):
        grouped[entry.archive_id].append(entry)
    batch=[]
    for group in grouped.values():
        if len(group)>BUCKET_SIZE:
            raise ValueError('Single archive exceeds bounded bucket size')
        if batch and len(batch)+len(group)>BUCKET_SIZE:
            yield batch
            batch=[]
        batch.extend(group)
    if batch:
        yield batch


def apply_bucket(session, manifest: Manifest, entries: list[Assignment], *, write: bool) -> dict:
    """Session owner commits or rolls back inserts, receipt, and audit as one unit."""
    if len(entries) > BUCKET_SIZE:
        raise ValueError('Assignment bucket exceeds bounded size')
    instance = verify_catalog_identity(session)
    if uuid.UUID(instance) != manifest.catalog_instance_id:
        raise ValueError('Manifest belongs to another catalog instance')
    body = {'policy': manifest.policy, 'instance': instance,
            'entries': [e.model_dump(mode='json') for e in entries]}
    digest = hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False,
                                       separators=(',', ':')).encode()).hexdigest()
    operation = str(uuid.uuid5(NAMESPACE, digest))
    if write:
        session.execute(text("SET LOCAL lock_timeout='10s'"))
        # Parent locks protect reviewed versions; this short table lock also fences
        # a concurrent insertion of a different artist credit for the same song.
        session.execute(text('LOCK TABLE performance_artists IN SHARE ROW EXCLUSIVE MODE'))
    if session.execute(text('SELECT 1 FROM catalog_imports WHERE operation_id=:op'),
                       {'op': operation}).scalar():
        return {'status': 'already_committed', 'inserted': 0, 'performance_ids': []}
    locking = ' FOR SHARE' if write else ''
    pids = sorted({e.performance_id for e in entries})
    performances = {p['id']: p for p in mapped(session,
        'SELECT id,version,archive_id,source_document_id,archived_at FROM performances WHERE id=ANY(:ids) ORDER BY id'
        + (' FOR UPDATE' if write else ''), ids=pids)}
    archives = {a['id']: a for a in mapped(session,
        'SELECT id,version,video_id,archived_at FROM live_archives WHERE id=ANY(:ids) ORDER BY id'+locking,
        ids=sorted({e.archive_id for e in entries}))}
    videos = {v['id']: v for v in mapped(session,
        'SELECT id,version,source_account_id,platform,platform_video_id,title,archived_at FROM videos WHERE id=ANY(:ids) ORDER BY id'+locking,
        ids=sorted({e.video_id for e in entries}))}
    accounts = {a['id']: a for a in mapped(session,
        'SELECT id,platform,platform_id,archived_at FROM external_accounts WHERE id=ANY(:ids) ORDER BY id'+locking,
        ids=sorted({e.source_account_id for e in entries}))}
    artists = {a['id']: a for a in mapped(session,
        'SELECT id,archived_at FROM artists WHERE id=ANY(:ids) ORDER BY id'+locking,
        ids=sorted({a.artist_id for e in entries for a in e.artists}))}
    documents = {d['id']: d for d in mapped(session,
        'SELECT id,content_hash,content_text,source_url FROM source_documents WHERE id=ANY(:ids) ORDER BY id'+locking,
        ids=sorted({e.source_document_id for e in entries}))}
    owners = mapped(session, """SELECT ae.account_id,ae.artist_id FROM artist_external_accounts ae
        JOIN artists a ON a.id=ae.artist_id WHERE ae.account_id=ANY(:ids)
        AND ae.relationship='owner' AND a.archived_at IS NULL""" + (' FOR SHARE OF ae' if write else ''), ids=list(accounts))
    owner_ids = {}
    for row in owners:
        owner_ids.setdefault(row['account_id'], set()).add(row['artist_id'])
    present = set(session.execute(text('SELECT DISTINCT performance_id FROM performance_artists WHERE performance_id=ANY(:ids)'), {'ids': pids}).scalars())
    missing=[]; skipped=Counter(); conflicts=[]
    for e in entries:
        if e.performance_id in present:
            skipped['existing_credit'] += 1
            continue
        p=performances.get(e.performance_id); arc=archives.get(e.archive_id)
        vid=videos.get(e.video_id); acc=accounts.get(e.source_account_id); doc=documents.get(e.source_document_id)
        valid = (
            p and not p['archived_at'] and p['version']==e.performance_version
            and p['archive_id']==e.archive_id and p['source_document_id']==e.source_document_id
            and arc and not arc['archived_at'] and arc['version']==e.archive_version and arc['video_id']==e.video_id
            and vid and not vid['archived_at'] and vid['version']==e.video_version and vid['source_account_id']==e.source_account_id
            and vid['platform']=='youtube' and vid['title']==e.evidence.video_title
            and acc and not acc['archived_at'] and acc['platform']=='youtube' and acc['platform_id']==e.channel_id
            and all(a.artist_id in artists and not artists[a.artist_id]['archived_at'] for a in e.artists)
            and doc and doc['content_hash']==e.source_hash and doc['source_url']==e.evidence.source_url
            and e.evidence.source_line in (doc['content_text'] or '')
            and e.evidence.source_url.startswith('https://www.youtube.com/watch?v='+vid['platform_video_id'])
        )
        if e.evidence.review_status=='contextual':
            valid = valid and owner_ids.get(e.source_account_id)=={e.artists[0].artist_id}
        if not valid:
            skipped['changed_or_invalid_evidence'] += 1
            conflicts.append(e.performance_id)
            continue
        missing.append(e)
    planned = sum(len(e.artists) for e in missing)
    result={'status':'dry_run','planned_links':planned,'inserted':0,'eligible_performances':len(missing),
            'skipped':dict(skipped),'conflicts':conflicts,'performance_ids':[e.performance_id for e in missing]}
    if not write:
        return result
    data=[{'performance_id':e.performance_id,**a.model_dump()} for e in missing for a in e.artists]
    inserted = mapped(session, """INSERT INTO performance_artists(performance_id,artist_id,role,position)
        SELECT x.performance_id,x.artist_id,x.role,x.position FROM jsonb_to_recordset(CAST(:data AS jsonb))
        x(performance_id integer,artist_id integer,role text,position integer)
        RETURNING id,performance_id,to_jsonb(performance_artists) after_data""", data=json.dumps(data)) if data else []
    if len(inserted)!=planned:
        raise RuntimeError('Singer credit insertion count changed')
    import_id=session.execute(text("""INSERT INTO catalog_imports
        (operation_id,catalog_instance_id,manifest_hash,source_kind,result_mapping,result_summary)
        VALUES (:op,:instance,:digest,'correction',CAST(:mapping AS jsonb),CAST(:summary AS jsonb)) RETURNING id"""),
        {'op':operation,'instance':instance,'digest':digest,
         'mapping':json.dumps([{'entity_type':'performance_artists','id':r['id'],'performance_id':r['performance_id']} for r in inserted]),
         'summary':json.dumps({'kind':manifest.policy,'inserted':len(inserted),'performances':len(missing),'skipped':dict(skipped)})}).scalar_one()
    by_id={e.performance_id:e for e in missing}
    changes=[]
    for row in inserted:
        entry=by_id[row['performance_id']]
        changes.append({'entity_id':row['id'],'after_data':row['after_data'],
                        'provenance':{'policy':manifest.policy,'performance_id':entry.performance_id,
                                      'source_document_id':entry.source_document_id,'source_hash':entry.source_hash,
                                      **entry.evidence.model_dump()}})
    if changes:
        session.execute(text("""INSERT INTO catalog_changes(import_id,entity_type,entity_id,action,after_data,provenance)
            SELECT :import_id,'performance_artists',x.entity_id,'create',x.after_data,x.provenance
            FROM jsonb_to_recordset(CAST(:data AS jsonb)) x(entity_id integer,after_data jsonb,provenance jsonb)"""),
            {'import_id':import_id,'data':json.dumps(changes)})
    return {**result,'status':'committed','inserted':len(inserted),'import_id':import_id}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',required=True,type=Path)
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    manifest=Manifest.model_validate_json(args.manifest.read_text(encoding='utf-8'))
    entries=sorted(manifest.links,key=lambda e:e.performance_id)
    results=[]
    for batch in buckets(entries):
        if args.apply:
            with catalog_runtime_session() as session:
                result=apply_bucket(session,manifest,batch,write=True)
        else:
            dependency=get_catalog_session(); session=next(dependency)
            try:
                result=apply_bucket(session,manifest,batch,write=False)
            finally:
                dependency.close()
        results.append(result)
        # Persist progress after every successful commit; the same manifest resumes safely.
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps({'mode':'apply' if args.apply else 'dry_run','policy':manifest.policy,
            'results':results},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({k:v for k,v in result.items() if k not in ('performance_ids','conflicts')}),flush=True)
    print(json.dumps({'inserted':sum(r['inserted'] for r in results),'planned':sum(r.get('planned_links',0) for r in results)}))


if __name__=='__main__':
    try:
        main()
    except Exception as exc:
        # Connection/provider inputs never appear in diagnostics.
        print(json.dumps({'error_type':type(exc).__name__}),file=sys.stderr)
        raise SystemExit(1) from None
