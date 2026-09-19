"""Preview/apply bilingual display names without deleting or moving any records."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.artist_identity import group_artists, normalize_artist_display_names
from app.core.db import get_connection


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    with get_connection() as conn:
        if not args.apply:
            conn.execute('SET TRANSACTION READ ONLY')
        changes = normalize_artist_display_names(conn, apply=args.apply)
        groups = group_artists(conn.execute('SELECT id, name, display_name, agency FROM artists').fetchall())
        print(json.dumps({'applied': args.apply, 'changes': changes, 'grouped': [
            {'label': row['display_name'], 'ids': row['related_artist_ids']}
            for row in groups if len(row['related_artist_ids']) > 1
        ]}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
