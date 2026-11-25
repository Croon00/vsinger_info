"""Export lyrics review files for original songs. Reads the DB and YouTube only; writes no DB rows.

candidates.json: lyrics found in the official video description, or in a comment announced as
lyrics (channel owner first). manual-with-video.json / manual-no-video.json: every other original
song, to fill in by hand, split by whether an official video is linked. excluded-covers.json:
released covers left out of the original list (see app/repositories/released_cover_rules.py).
Both files use the same entry format and are imported with scripts/import_original_lyrics.py
after review (only ``approved: true`` entries are imported).
"""
import argparse
import asyncio
from datetime import UTC, datetime
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import text

from app.core.config import settings
from app.db.catalog_session import catalog_runtime_session
from app.integrations.youtube_catalog import YouTubeClient, YouTubeFailure
from app.repositories.recording_lyrics import existing_lyrics, original_entries, released_cover_entries
from app.schemas.lyrics_review import LyricsEntry, LyricsReviewFile
from app.services.catalog_read import CatalogRead
from app.services.lyrics_extraction import comment_lyrics, description_lyrics

INSTRUCTIONS = {
    'candidates': ('자동 추출한 가사 후보입니다. original_lyrics의 앞뒤 경계와 내용을 source_text·source_url과 대조해 고치고, '
                   '공개해도 되는 항목만 approved를 true로 바꾸세요. translation_ko·pronunciation_ko는 비워 둬도 됩니다. '
                   'source_author_is_channel_owner가 false인 댓글은 팬이 올린 가사라 정확도를 꼭 확인하세요.'),
    'manual-with-video': ('공식 YouTube 영상은 연결돼 있지만 설명란·상위 댓글에서 가사를 찾지 못한 오리지널 곡입니다. '
                          'original_lyrics(필수)와 translation_ko·pronunciation_ko(선택)를 채우고, 근거가 있으면 '
                          'source_kind(official_page·announcement·manual_note)와 source_url을 넣은 뒤 approved를 true로 바꾸세요.'),
    'manual-no-video': ('Spotify 등 발매 음원은 있지만 우리 DB에 공식 YouTube 영상이 연결되지 않아 설명란·댓글을 확인하지 못한 오리지널 곡입니다. '
                        'YouTube에 영상이 없다는 뜻은 아닙니다. Remix·Live 등 다른 버전이나 Instrumental·MC 트랙도 섞여 있습니다. '
                        'original_lyrics(필수)와 translation_ko·pronunciation_ko(선택)를 채우고, 근거가 있으면 '
                        'source_kind(official_page·announcement·manual_note)와 source_url을 넣은 뒤 approved를 true로 바꾸세요.'),
}


EXCLUDED_NOTE = ('오리지널 목록에서 제외한 발매 커버 음원입니다(제목·버전에 Cover/カバー/歌ってみた 표기가 있거나, '
                 '곡의 원곡자로 가창자·소속 그룹이 아닌 다른 아티스트만 등록됨). 오리지널인데 잘못 제외됐다면 곡의 원곡자 연결을 고쳐야 합니다.')


def _base(entry, captured):
    video = entry.get('youtube_video_id')
    return dict(key=entry['key'], recording_ids=entry['recording_ids'], title=(entry['title'] or '').strip(),
                title_ko=entry.get('title_ko'), artist=entry.get('artist_name') or '',
                youtube_url=f'https://www.youtube.com/watch?v={video}' if video else None, captured_at=captured)


async def _comment(client, video, title, owner):
    data = await client.get('commentThreads', part='snippet', videoId=video, order='relevance',
                            maxResults=100, textFormat='plainText')
    found = []
    for item in data.get('items', []):
        thread = item['snippet']
        snippet = thread['topLevelComment']['snippet']
        result = comment_lyrics(snippet.get('textDisplay') or '', title)
        if result:
            is_owner = (snippet.get('authorChannelId') or {}).get('value') == owner
            found.append((is_owner, result['method'] == 'announced', snippet.get('likeCount', 0),
                          thread['topLevelComment']['id'], snippet.get('textDisplay'), result))
    if not found:
        return None
    is_owner, _, _, comment_id, raw, result = max(found, key=lambda x: x[:3])
    return dict(source_kind='youtube_comment', source_external_id=comment_id, source_author_is_channel_owner=is_owner,
                source_url=f'https://www.youtube.com/watch?v={video}&lc={comment_id}', source_text=raw,
                extraction_method=result['method'], original_lyrics=result['lyrics'])


async def main(output, comments=True, limit=None):
    captured = datetime.now(UTC)
    with catalog_runtime_session() as session:
        session.execute(text('SET TRANSACTION READ ONLY'))
        entries = original_entries(session, CatalogRead(session))[:limit]
        stored = existing_lyrics(session, {r for e in entries for r in e['recording_ids']})
        excluded = released_cover_entries(session)
    client = YouTubeClient(settings.youtube_api_key, interval=0.2)
    videos = list(dict.fromkeys(e['youtube_video_id'] for e in entries if e.get('youtube_video_id')))
    details = {}
    for offset in range(0, len(videos), 50):
        data = await client.get('videos', part='snippet', id=','.join(videos[offset:offset + 50]))
        details.update({item['id']: item['snippet'] for item in data.get('items', [])})
    candidates, manual, counts = [], [], {}
    for entry in entries:
        row = _base(entry, captured)
        video = entry.get('youtube_video_id')
        if stored & set(entry['recording_ids']):
            row['status'] = 'already_stored'
        elif not video:
            row['status'] = 'no_video'
        elif video not in details:
            row['status'] = 'video_unavailable'
        else:
            snippet = details[video]
            found = description_lyrics(snippet.get('description') or '')
            if found:
                row.update(status='found_in_description', source_kind='video_description', source_external_id=video,
                           source_author_is_channel_owner=True, source_url=row['youtube_url'],
                           source_text=snippet.get('description'), extraction_method=found['method'],
                           original_lyrics=found['lyrics'])
            elif comments:
                try:
                    found = await _comment(client, video, row['title'], snippet.get('channelId'))
                    row['status'] = 'found_in_comment' if found else 'no_lyrics_found'
                    row.update(found or {})
                except YouTubeFailure as exc:
                    if exc.retry:  # quota, rate limit, 5xx: stop instead of writing a partial review file
                        raise
                    row['status'] = 'comments_unavailable'  # commentsDisabled, videoNotFound
            else:
                row['status'] = 'no_lyrics_in_description'
        counts[row['status']] = counts.get(row['status'], 0) + 1
        (candidates if row.get('original_lyrics') else manual).append(LyricsEntry(**row))
    output.mkdir(parents=True, exist_ok=True)
    files = (('candidates', 'candidates', candidates),
             ('manual-with-video', 'manual', [r for r in manual if r.youtube_url]),
             ('manual-no-video', 'manual', [r for r in manual if not r.youtube_url]))
    for name, kind, rows in files:
        document = LyricsReviewFile(kind=kind, generated_at=captured, instructions=INSTRUCTIONS[name], entries=rows)
        (output / f'{name}.json').write_text(json.dumps(document.model_dump(mode='json'), ensure_ascii=False, indent=1),
                                            encoding='utf-8')
    (output / 'excluded-covers.json').write_text(json.dumps(dict(
        generated_at=captured.isoformat(), instructions=EXCLUDED_NOTE, entries=excluded), ensure_ascii=False, indent=1),
        encoding='utf-8')
    print(json.dumps(dict(originals=len(entries), excluded_covers=len(excluded), candidates=len(candidates), manual=len(manual), by_status=counts,
                          output=str(output)), ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--output', type=Path,
                        default=Path('db-migration/reports') / f'original-lyrics-{datetime.now().date().isoformat()}')
    parser.add_argument('--skip-comments', action='store_true', help='Only read descriptions (no commentThreads calls)')
    parser.add_argument('--limit', type=int, help='Only the first N original entries (trial run)')
    args = parser.parse_args()
    try:
        asyncio.run(main(args.output, comments=not args.skip_comments, limit=args.limit))
    except YouTubeFailure as exc:
        print(json.dumps(dict(stopped=exc.reason)))
        raise SystemExit(2) from None
