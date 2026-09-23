"""Read-only v2 queries, using the shared connection pool and bounded responses.

Legacy collector data is not repaired or merged by these queries.
"""
import json
from collections import defaultdict
from datetime import datetime, timezone
from time import perf_counter
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.core.artist_identity import group_artists, name_key
from app.schemas.read_models import ArtistRead, StatisticsRead

LIVE_FROM = '''FROM youtube_live_archives y
 LEFT JOIN artist_sources s ON s.id=y.source_id
 LEFT JOIN artists a ON a.id=s.artist_id'''
VISIBLE = '(y.duration_seconds IS NULL OR y.duration_seconds > 420)'
LIVE_COLUMNS = '''y.id, s.artist_id, COALESCE(a.name,y.performer_name,'YouTube') artist_name,
 y.youtube_url,y.youtube_video_id,y.video_title,y.broadcast_at,y.published_at,y.duration_seconds'''
PERFORMANCE_COLUMNS = 'p.id,p.song_title,p.song_title_ko,p.original_artist,p.original_artist_ko,p.start_seconds'

class ReadCatalog:
    def __init__(self, session: Session):
        self.session = session
        self.query_count = 0
        self.query_ms = 0.0
        self._artists = None

    def rows(self, sql, params=None):
        start = perf_counter()
        result = [dict(row) for row in self.session.execute(text(sql), params or {}).mappings()]
        self.query_ms += (perf_counter()-start)*1000
        self.query_count += 1
        return result

    def artists(self):
        if self._artists is None:
            # Exactly two queries, regardless of the number of artists. Keep the
            # previous representative-ID ordering; do not move saved favorites.
            artists = self.rows('''SELECT id,name,display_name,agency,profile_intro,
                                   spotify_image_url FROM artists ORDER BY id''')
            sources = self.rows('''SELECT artist_id,source_type,value,label,is_active
                                   FROM artist_sources WHERE is_active=true ORDER BY id''')
            by_id = defaultdict(list)
            for source in sources:
                by_id[source['artist_id']].append(source)
            for artist in artists:
                artist['sources'] = by_id[artist['id']]
            self._artists = [ArtistRead.model_validate(a).model_dump() for a in group_artists(artists)]
        return self._artists

    def artist(self, artist_id):
        return next((a for a in self.artists() if artist_id in a['related_artist_ids']), None)

    def scope(self, artist_id):
        artist = self.artist(artist_id)
        if not artist:
            raise LookupError('Artist not found')
        # Source IDs have priority. For source-less rows use only unambiguous
        # registered aliases, never substring or AI-generated identity guesses.
        owners = defaultdict(set)
        for a in self.artists():
            for alias in [a['name'],a['display_name'],*a['name_aliases']]:
                if alias:
                    owners[name_key(alias)].add(a['id'])
        aliases = [key for key, ids in owners.items() if ids == {artist['id']}]
        condition = '''(s.artist_id = ANY(:ids) OR (s.id IS NULL AND
          regexp_replace(lower(normalize(COALESCE(y.performer_name,''), NFKC)), '[[:space:]_]', '', 'g') = ANY(:aliases)))'''
        return condition, {'ids':artist['related_artist_ids'],'aliases':aliases}

    def page(self, sql, params, offset, limit, order_by):
        # COUNT OVER avoids an extra round trip; empty out-of-range pages get a
        # separate count so their total remains accurate.
        rows = self.rows(f'SELECT q.*,COUNT(*) OVER() _total FROM ({sql}) q ORDER BY {order_by} LIMIT :limit OFFSET :offset',
                         {**params,'limit':limit,'offset':offset})
        total = rows[0]['_total'] if rows else (self.rows(f'SELECT COUNT(*) n FROM ({sql}) q', params)[0]['n'] if offset else 0)
        for row in rows:
            row.pop('_total',None)
        return {'items':rows,'total':total,'offset':offset,'limit':limit}

    def lives(self, artist_id, offset, limit):
        scope, params = self.scope(artist_id)
        result = self.page(f'''SELECT {LIVE_COLUMNS} {LIVE_FROM} WHERE {VISIBLE} AND {scope}
                              ORDER BY COALESCE(y.broadcast_at,y.published_at) DESC NULLS LAST,y.id DESC''',params,offset,limit,'COALESCE(q.broadcast_at,q.published_at) DESC NULLS LAST,q.id DESC')
        for row in result['items']:
            row['artist_id'] = self.artist(artist_id)['id']
        return result

    def live(self, archive_id):
        rows = self.rows(f'SELECT {LIVE_COLUMNS} {LIVE_FROM} WHERE y.id=:id', {'id':archive_id})
        if not rows:
            return None
        row = rows[0]
        row['performances'] = self.rows(f'SELECT {PERFORMANCE_COLUMNS} FROM youtube_song_performances p WHERE p.archive_id=:id ORDER BY p.start_seconds,p.id',{'id':archive_id})
        return row

    def search(self, q, offset, limit):
        # Parameterized literal substring: % and _ in user input are not wildcards.
        pattern = '%' + q.replace('\\','\\\\').replace('%','\\%').replace('_','\\_') + '%'
        return self.page(f'''SELECT {PERFORMANCE_COLUMNS},p.archive_id,p.performed_on,
          s.artist_id,COALESCE(a.name,y.performer_name,'YouTube') artist_name,y.youtube_url,y.video_title
          FROM youtube_song_performances p JOIN youtube_live_archives y ON y.id=p.archive_id
          LEFT JOIN artist_sources s ON s.id=y.source_id LEFT JOIN artists a ON a.id=s.artist_id
          WHERE {VISIBLE} AND (p.song_title ILIKE :q OR p.song_title_ko ILIKE :q
            OR p.original_artist ILIKE :q OR p.original_artist_ko ILIKE :q)
          ORDER BY p.performed_on DESC NULLS LAST,p.start_seconds,p.id''',{'q':pattern},offset,limit,'q.performed_on DESC NULLS LAST,q.start_seconds,q.id')

    def statistics(self, artist_id):
        scope, params = self.scope(artist_id)
        # Aggregate in PostgreSQL. Transfer one row per distinct song/artist/month,
        # not every performance and duplicated setlist JSON.
        cte = f'''WITH archives AS (SELECT y.id,COALESCE(y.broadcast_at,y.published_at) happened
                         {LIVE_FROM} WHERE {VISIBLE} AND {scope}),
          entries AS (SELECT p.*,a.happened,
            lower(regexp_replace(trim(normalize(p.song_title,NFKC)), '[[:space:]]+', ' ', 'g')) song_key,
            lower(regexp_replace(trim(normalize(COALESCE(p.original_artist,''),NFKC)), '[[:space:]]+', ' ', 'g')) artist_key
            FROM youtube_song_performances p JOIN archives a ON a.id=p.archive_id)'''
        rows = self.rows(cte + ''' SELECT song_key,artist_key,MIN(song_title) title,
          COALESCE(MIN(original_artist),'') artist,COUNT(*) count,MAX(happened) last_date,
          string_agg(DISTINCT concat_ws(' ',song_title,song_title_ko,original_artist,original_artist_ko),' ') search
          FROM entries GROUP BY song_key,artist_key ORDER BY count DESC,song_key,artist_key''',params)
        # Archive/month totals include broadcasts without setlists, excluding
        # future/undated archives from the activity graph only.
        meta = self.rows(cte + ''' SELECT COUNT(*) total,
          COUNT(*) FILTER (WHERE EXISTS(SELECT 1 FROM youtube_song_performances p WHERE p.archive_id=archives.id)) with_setlist,
          to_char(happened AT TIME ZONE 'Asia/Seoul','YYYY-MM') AS month_key,
          COUNT(*) FILTER (WHERE happened<=CURRENT_TIMESTAMP) activity_count
          FROM archives GROUP BY month_key ORDER BY month_key NULLS LAST''',params)
        songs = []
        artists = {}
        rank = 0
        previous = None
        for i,row in enumerate(rows):
            if previous != row['count']:
                rank = i+1
            previous = row['count']
            songs.append({'key':json.dumps([row['song_key'],row['artist_key']],ensure_ascii=False),
                          'title':row['title'] or '곡명 미등록','artist':row['artist'] or '아티스트 미등록',
                          'searchText':row['search'],'count':row['count'],'lastPerformedAt':row['last_date'],'rank':rank})
            if row['artist_key']:
                item = artists.setdefault(row['artist_key'],{'key':row['artist_key'],'name':row['artist'],'count':0})
                item['count'] += row['count']
        total = sum(s['count'] for s in songs)
        ranked = sorted(artists.values(),key=lambda a:(-a['count'],a['key']))
        for item in ranked:
            item['percentage'] = item['count']/total*100 if total else 0
        return StatisticsRead(archives=sum(m['total'] for m in meta), archivesWithSetlist=sum(m['with_setlist'] for m in meta),
          performances=total,uniqueSongs=len(songs),uniqueArtists=len(ranked),songs=songs,artists=ranked,
          activity=[{'month':m['month_key'],'count':m['activity_count']} for m in meta if m['month_key'] and m['activity_count']])

    def concerts(self, offset, limit, artist_id=None, start=None, end=None):
        params = {}
        where = "status IN ('ready','synced') AND event_type='live_event' AND event_format IN ('onsite','hybrid') AND artist_id IS NOT NULL AND starts_at IS NOT NULL"
        if artist_id is not None:
            artist = self.artist(artist_id)
            if not artist:
                raise LookupError('Artist not found')
            where += ' AND artist_id=ANY(:ids)'
            params['ids'] = artist['related_artist_ids']
        # Date strings are legacy free text. Filter only ISO-shaped dates, without
        # casts that could make a malformed legacy record fail the whole request.
        where += " AND starts_at ~ '^\\d{4}-\\d{2}-\\d{2}'"
        if start:
            where += ' AND substring(starts_at,1,10)>=:start'
            params['start'] = start.isoformat()
        if end:
            where += ' AND substring(starts_at,1,10)<:end'
            params['end'] = end.isoformat()
        return self.page(f'''SELECT id,artist_id,title,starts_at,venue,price_text,source_url,ticket_url,status,event_type,event_format
                           FROM event_candidates WHERE {where} ORDER BY starts_at,id''',params,offset,limit,'q.starts_at,q.id')

    def concert(self, event_id):
        rows = self.rows('''SELECT id,artist_id,title,starts_at,venue,price_text,source_url,ticket_url,status,event_type,event_format
          FROM event_candidates WHERE id=:id AND status IN ('ready','synced') AND event_type='live_event'
          AND event_format IN ('onsite','hybrid') AND artist_id IS NOT NULL AND starts_at IS NOT NULL
          AND starts_at ~ '^\\d{4}-\\d{2}-\\d{2}' ''', {'id':event_id})
        return rows[0] if rows else None
