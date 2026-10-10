"""Review and soft archive clear non-song setlist entries across the catalog."""
import argparse
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from clean_chise_setlist import MARKERS
from import_legacy_setlists import connection_url

# These are actual song titles, despite consisting only of symbols or resembling cues.
KEEP = {'+♂', '＋♂', '∞', 'StaRt', '〜 StaRt', 'START!!', 'アンコール', 'ありがとう', 'バイバイ'}
EXACT = MARKERS | {
    'START', 'start', '[ START ]', '【START】', 'LIVE START', 'END', 'End',
    'ENDING', 'Ending', 'ending', 'Ending 2', 'Donation & Superchat reading',
    '待機画面', '配信開始', '配信終了', 'ご挨拶', '休憩', 'トイレ休憩',
    'ミュート', 'ミュート芸', 'アフタートーク', '雑談パート', '(雑談)',
    '開始前トーク', '開始前トーク/OPトーク', '開会式トーク', '恐竜トーク',
    'ショートトーク①', 'ショートトーク②', 'スパチャ', '再告知', '大切なお知らせ',
    '終わりの挨拶', '終わりの挨拶(再)', '終わりの挨拶と明日の予定',
    'こんしらせ〜', 'こんしらせ～', 'こんしらせ～こんつき～', 'こんしらせ～こんばんにょ～',
    'こんしらせ～こんぴよ～', 'こんてな！', 'こんであ～', 'こんのい', 'こんのいー',
    'こんのい～', 'こんのの！', 'こんばぶ～', 'こんばんドドド', 'こんむあ！',
    'こんシェルたま', 'こんシェル～ハロウタノーン', 'こんありうむ～《配信開始》',
    'おつくも', 'おつくもー', 'おつくもー！', 'おつくも！', 'おつしらせ～～',
    'おつたまでした！', 'おつたま！', 'おつなぎでした〜', 'おつにゃん', 'おつのい',
    'おつまんぼう～おつりんご～', 'おつもぐの～ん', 'おつウタノン', 'おつシェルたま',
}

def reason(title):
    t = title.strip()
    if t in KEEP:
        return None
    if t in EXACT:
        return 'reviewed_greeting_or_segment'
    if not any(unicodedata.category(c)[0] in 'LN' for c in t):
        return 'symbol_or_emoji_only'
    if re.match(r'^(?:待機)?OP\s*(?:start|talk|トーク)|^ED\s*(?:talk|トーク)|^枠\s*start', t, re.I):
        return 'opening_or_ending_segment'
    if re.match(r'^(?:[①③⑤⑦⑧])?(?:トークパート|TalkPart)|^(?:オープニング|エンディング)トーク', t, re.I):
        return 'talk_segment'
    if re.match(r'^(?:スパチャ読み|スパチャチェキ|自己紹介|告知|お知らせ)', t):
        return 'announcement_or_reading_segment'
    if t.startswith('<<トーク>>'):
        return 'talk_segment'
    if re.match(r'^[\]】]\s*(?:開始|🎤(?:Talk|エンディングトーク|オープニングトーク)|💐(?:Ending Talk|Opening Talk|Talk Time)|🌙 Streaming Start|お知らせ|❗デビューグッズ|・\s*(?:LIVE出演の告知|アンコール！|少し雑談|改めて自己紹介))', t):
        return 'decorated_segment'
    if re.match(r'^[〜～]\s*(?:CD告知|Live告知|告知|新待機画面|開始/)', t):
        return 'decorated_segment'
    if re.fullmatch(r'[\W\d_]+start(?:\s+[\d:]+)?', t, re.I):
        return 'emoji_timestamp_marker'
    if t in {'̗̀  Last Talk  ̖́', '̗̀ start  ̖́-‬', '本編start', 'スタート (start)'}:
        return 'segment'
    return None

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    directory = Path(__file__).resolve().parents[1] / 'db-migration/reports/setlist-cleanup-2026-10-10'
    directory.mkdir(parents=True, exist_ok=True)
    with psycopg.connect(connection_url(), row_factory=dict_row) as conn:
        # Only the new catalog is accessed; source documents and song masters are untouched.
        rows = conn.execute('''SELECT p.*,a.name_native AS host_name FROM performances p
            JOIN live_archives l ON l.id=p.archive_id LEFT JOIN artists a ON a.id=l.primary_artist_id
            WHERE p.archived_at IS NULL ORDER BY p.id''').fetchall()
        selected = [dict(r, exclusion_reason=reason(r['raw_title'])) for r in rows if reason(r['raw_title'])]
        summary = {'date': '2026-10-10', 'scanned': len(rows), 'selected': len(selected),
                   'artists': dict(Counter(r['host_name'] for r in selected)),
                   'titles': dict(Counter(r['raw_title'] for r in selected))}
        (directory / 'plan.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
        print(json.dumps({k:v for k,v in summary.items() if k != 'titles'}, ensure_ascii=False))
        if args.apply and selected:
            backup = directory / 'before.json'
            if backup.exists():
                raise ValueError('Backup already exists; review before another application')
            backup.write_text(json.dumps(selected, ensure_ascii=False, indent=2, default=str)+'\n', encoding='utf8')
            for r in selected:
                result = conn.execute('''UPDATE performances SET archived_at=clock_timestamp(),
                    updated_at=clock_timestamp(),version=version+1
                    WHERE id=%s AND version=%s AND archived_at IS NULL''', (r['id'], r['version']))
                if result.rowcount != 1:
                    raise ValueError('Concurrent modification; transaction rolled back')
            ids = [r['id'] for r in selected]
            remaining = conn.execute('SELECT count(*) AS n FROM performances WHERE id=ANY(%s) AND archived_at IS NULL', (ids,)).fetchone()['n']
            if remaining:
                raise ValueError('Visibility verification failed')
            conn.commit()
            (directory / 'result.json').write_text(json.dumps(dict(summary, remaining_visible=remaining), ensure_ascii=False, indent=2)+'\n', encoding='utf8')
        else:
            conn.rollback()

if __name__ == '__main__':
    main()
