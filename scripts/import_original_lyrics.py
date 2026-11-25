"""Import reviewed lyrics files. Dry run by default; --apply writes in one transaction.

Only ``approved: true`` entries are imported. Each entry stores its source in
source_documents and adds recording_lyrics for every listed recording that has none yet.
Imported lyrics are public through /api/recordings/{id}/lyrics as soon as they are written.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.db.catalog_session import catalog_runtime_session
from app.repositories import recording_lyrics as repository
from app.schemas.lyrics_review import LyricsReviewFile


def main(paths, apply=False):
    entries = []
    for path in paths:
        entries += [e for e in LyricsReviewFile.model_validate_json(Path(path).read_text(encoding='utf-8')).entries
                    if e.approved]
    keys = Counter(e.key for e in entries)
    if duplicate := [k for k, n in keys.items() if n > 1]:
        raise SystemExit(f'Approved more than once: {duplicate[:5]}')
    counts = Counter()
    with catalog_runtime_session() as session:
        ids = {r for e in entries for r in e.recording_ids}
        active = repository.active_recordings(session, ids) if ids else set()
        stored = repository.existing_lyrics(session, ids)
        for entry in entries:
            targets = [r for r in entry.recording_ids if r in active and r not in stored]
            counts['skipped_existing_or_archived'] += len(entry.recording_ids) - len(targets)
            if not targets:
                continue
            counts['entries'] += 1
            counts['recordings'] += len(targets)
            if apply:
                document = repository.source_document(session, entry)
                for recording in targets:
                    repository.insert(session, recording, entry, document)
                stored.update(targets)
        if not apply:
            session.rollback()
    print(json.dumps(dict(approved=len(entries), applied=apply, **counts), ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('files', nargs='+', help='candidates.json and/or manual.json')
    parser.add_argument('--apply', action='store_true', help='Write to the database (default is a dry run)')
    args = parser.parse_args()
    main(args.files, apply=args.apply)
