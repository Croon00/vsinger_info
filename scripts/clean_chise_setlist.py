"""Hide explicitly reviewed non-song markers for Itsuki Chise; preserve originals."""
import argparse
import json
from collections import Counter
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from import_legacy_setlists import connection_url

MARKERS = {
    'こんつきー', 'こんつき一', 'こんつきこんしらせ', 'kon tsuki', 'おつつきー',
    '⚠️', '💝', '💝※【coverMV㊒】', '※【coverMV㊒】', '~※【coverMV㊒】',
    '~', '~  START', '~ START', '〜   START', '~   スパチャ読み', '~ スパチャ読み',
    '開始', '自己紹介・ゲスト紹介', '【アンコール】', '【リベンジ】', '【月間練習曲】',
    '(ワンコーラス)', '（2回目）',
}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    report_dir = Path(__file__).resolve().parents[1] / 'db-migration/reports/chise-cleanup-2026-10-09'
    report_dir.mkdir(parents=True, exist_ok=True)
    with psycopg.connect(connection_url(), row_factory=dict_row) as conn:
        artist = conn.execute("SELECT id FROM artists WHERE slug='itsuki-chise' AND archived_at IS NULL").fetchone()
        if not artist or artist['id'] != 72:
            raise ValueError('Expected Chise catalog identity missing')
        rows = conn.execute('''SELECT p.* FROM performances p JOIN live_archives l ON l.id=p.archive_id
            WHERE l.primary_artist_id=%s AND p.archived_at IS NULL ORDER BY p.id FOR UPDATE OF p''', (artist['id'],)).fetchall()
        selected = [r for r in rows if r['raw_title'].strip() in MARKERS]
        report = {'date': '2026-10-09', 'artist_id': artist['id'], 'action': 'soft_archive_non_song_markers',
                  'counts': dict(Counter(r['raw_title'] for r in selected)), 'count': len(selected), 'before': selected}
        print(json.dumps({k:v for k,v in report.items() if k != 'before'}, ensure_ascii=False))
        if args.apply and selected:
            backup = report_dir / 'before.json'
            if backup.exists():
                raise ValueError('Existing backup: review before applying again')
            backup.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str)+'\n', encoding='utf8')
            ids = [r['id'] for r in selected]
            result = conn.execute('''UPDATE performances SET archived_at=clock_timestamp(),
                updated_at=clock_timestamp(),version=version+1 WHERE id=ANY(%s) AND archived_at IS NULL''', (ids,))
            if result.rowcount != len(ids):
                raise ValueError('Concurrent modification')
            remaining = conn.execute('SELECT count(*) AS n FROM performances WHERE id=ANY(%s) AND archived_at IS NULL', (ids,)).fetchone()['n']
            if remaining:
                raise ValueError('Visibility verification failed')
            conn.commit()
            (report_dir / 'result.json').write_text(json.dumps({'archived': len(ids), 'remaining_visible': remaining}, indent=2)+'\n', encoding='utf8')
        else:
            conn.rollback()

if __name__ == '__main__':
    main()
