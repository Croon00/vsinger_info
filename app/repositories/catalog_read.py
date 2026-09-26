"""New catalog SQL. All queries are reads; no collector or legacy identity heuristics."""
from time import perf_counter
from sqlalchemy import text

LIVE_FROM = """FROM live_archives l JOIN videos v ON v.id=l.video_id
 LEFT JOIN LATERAL (SELECT ar.id,ar.name_native FROM artists ar WHERE ar.archived_at IS NULL AND ar.show_in_catalog
 AND (ar.id=l.primary_artist_id OR EXISTS(SELECT 1 FROM archive_artists aa WHERE aa.archive_id=l.id AND aa.artist_id=ar.id))
 ORDER BY (ar.id=l.primary_artist_id) DESC NULLS LAST,ar.id LIMIT 1) a ON true"""
LIVE_VISIBLE = "l.archived_at IS NULL AND v.archived_at IS NULL AND v.availability IN ('public','unlisted','unknown')"
LIVE_COLUMNS = """l.id,a.id artist_id,COALESCE(a.name_native,'') artist_name,
 'https://www.youtube.com/watch?v='||v.platform_video_id youtube_url,
 v.platform_video_id youtube_video_id,v.title video_title,l.broadcast_at,v.published_at,v.duration_seconds"""
SCOPE = """(l.primary_artist_id=:artist OR EXISTS(SELECT 1 FROM archive_artists aa
 WHERE aa.archive_id=l.id AND aa.artist_id=:artist) OR EXISTS(
 SELECT 1 FROM performances sp JOIN performance_artists spa ON spa.performance_id=sp.id
 WHERE sp.archive_id=l.id AND sp.archived_at IS NULL AND spa.artist_id=:artist))"""
# Distinct work IDs remain distinct even when their titles match.
PERFORMANCE_SQL = """SELECT p.id,p.archive_id,p.ordinal,p.start_seconds,p.song_id,
 COALESCE(s.title_native,p.raw_title) song_title,s.title_ko song_title_ko,
 COALESCE(orig.names,p.raw_artist,'') original_artist,orig.names_ko original_artist_ko,
 COALESCE(orig.artists,CASE WHEN p.raw_artist IS NOT NULL AND btrim(p.raw_artist)<>'' THEN
 jsonb_build_array(jsonb_build_object('key','raw:'||lower(btrim(p.raw_artist)),'name',p.raw_artist)) ELSE '[]'::jsonb END) originals,
 CASE WHEN s.id IS NOT NULL THEN 'song:'||s.id::text ELSE 'raw:'||md5(lower(btrim(p.raw_title))||'/'||lower(btrim(COALESCE(p.raw_artist,'')))) END song_key,
 concat_ws(' ',s.title_native,s.title_ko,s.title_latin,p.raw_title,p.raw_artist,orig.search) search_text,
 singer.artist_id singer_id,singer.name_native singer_name,singer.name_ko singer_name_ko
 FROM performances p LEFT JOIN songs s ON s.id=p.song_id AND s.archived_at IS NULL
 LEFT JOIN LATERAL (
 SELECT string_agg(oa.name_native,' · ' ORDER BY sa.position,sa.id) names,
 string_agg(COALESCE(oa.name_ko,oa.name_native),' · ' ORDER BY sa.position,sa.id) names_ko,
 string_agg(concat_ws(' ',oa.name_native,oa.name_ko,oa.name_latin,
 (SELECT string_agg(al.alias,' ') FROM artist_aliases al WHERE al.artist_id=oa.id)),' ') search,
 jsonb_agg(jsonb_build_object('key','artist:'||oa.id::text,'name',oa.name_native,'nameKo',oa.name_ko) ORDER BY sa.position,sa.id) artists
 FROM song_artists sa JOIN artists oa ON oa.id=sa.artist_id AND oa.archived_at IS NULL WHERE sa.song_id=s.id
 ) orig ON true
 LEFT JOIN LATERAL (
 SELECT pa.artist_id,va.name_native,va.name_ko FROM performance_artists pa
 JOIN artists va ON va.id=pa.artist_id AND va.archived_at IS NULL
 WHERE pa.performance_id=p.id ORDER BY pa.position,pa.id LIMIT 1
 ) singer ON true WHERE p.archived_at IS NULL"""

# Match on narrow rows first; constructing PERFORMANCE_SQL for every candidate
# makes a paged search pay for all setlist display fields and lateral aggregates.
SEARCH_CANDIDATES_SQL = f"""WITH matched_artists AS MATERIALIZED (
 SELECT a.id,a.name_native,a.name_ko,a.name_latin FROM artists a
 WHERE a.archived_at IS NULL AND (a.name_native ILIKE :query OR a.name_ko ILIKE :query
 OR a.name_latin ILIKE :query OR EXISTS (
 SELECT 1 FROM artist_aliases al WHERE al.artist_id=a.id AND al.alias ILIKE :query))
), matched_names AS MATERIALIZED (
 SELECT lower(btrim(n.name)) name FROM matched_artists a
 CROSS JOIN LATERAL (VALUES (a.name_native),(a.name_ko),(a.name_latin)) n(name)
 WHERE n.name IS NOT NULL
 UNION
 SELECT lower(btrim(al.alias)) FROM artist_aliases al
 JOIN matched_artists a ON a.id=al.artist_id
), candidates AS MATERIALIZED (
 SELECT p.id,p.archive_id,p.ordinal,COALESCE(l.broadcast_at,v.published_at) broadcast_at
 FROM performances p JOIN live_archives l ON l.id=p.archive_id
 JOIN videos v ON v.id=l.video_id
 LEFT JOIN songs s ON s.id=p.song_id AND s.archived_at IS NULL
 WHERE p.archived_at IS NULL AND {LIVE_VISIBLE} AND (
 concat_ws(' ',s.title_native,s.title_ko,s.title_latin,p.raw_title,p.raw_artist) ILIKE :query
 OR l.primary_artist_id IN (SELECT id FROM matched_artists)
 OR EXISTS (SELECT 1 FROM performance_artists pa WHERE pa.performance_id=p.id
   AND pa.artist_id IN (SELECT id FROM matched_artists))
 OR EXISTS (SELECT 1 FROM song_artists sa WHERE sa.song_id=s.id
   AND sa.artist_id IN (SELECT id FROM matched_artists))
 OR (p.song_id IS NULL AND lower(btrim(p.raw_artist)) IN (SELECT name FROM matched_names))
))"""

class CatalogReadRepository:
    def __init__(self, session):
        self.session = session
        self.query_ms = 0.0
        self.query_count = 0

    def rows(self, sql, params=None):
        started = perf_counter()
        result = [dict(row) for row in self.session.execute(text(sql), params or {}).mappings()]
        self.query_ms += (perf_counter()-started)*1000
        self.query_count += 1
        return result

    def page(self, sql, params, offset, limit, order):
        rows = self.rows(f"SELECT q.*,count(*) OVER() _total FROM ({sql}) q ORDER BY {order} LIMIT :limit OFFSET :offset",
                         {**params,"limit":limit,"offset":offset})
        total = rows[0]["_total"] if rows else (self.rows(f"SELECT count(*) n FROM ({sql}) q",params)[0]["n"] if offset else 0)
        for row in rows:
            row.pop("_total", None)
        return {"items": rows, "total": total, "offset": offset, "limit": limit}

    def artists(self):
        return self.rows("""SELECT a.id,a.name_native name,a.name_ko display_name,a.name_latin,
        g.name_native agency,a.bio profile_intro,a.avatar_url spotify_image_url,a.theme_color,
        CASE WHEN a.birthday_month IS NOT NULL AND a.birthday_day IS NOT NULL THEN
          lpad(a.birthday_month::text,2,'0')||'-'||lpad(a.birthday_day::text,2,'0') END birthday,
        ARRAY[a.id] related_artist_ids,
        ARRAY(SELECT alias FROM artist_aliases WHERE artist_id=a.id ORDER BY id) name_aliases,
        COALESCE((SELECT jsonb_agg(jsonb_build_object('source_type',
          CASE WHEN e.platform='website' THEN 'official_site' ELSE e.platform END,
          'value',e.url,'label',ae.label,'is_active',true) ORDER BY ae.position,ae.id)
          FROM artist_external_accounts ae JOIN external_accounts e ON e.id=ae.account_id
          WHERE ae.artist_id=a.id AND e.archived_at IS NULL),'[]'::jsonb) sources
        FROM artists a LEFT JOIN agencies g ON g.id=a.agency_id AND g.archived_at IS NULL
        WHERE a.archived_at IS NULL AND a.show_in_catalog ORDER BY lower(a.name_native),a.id""")

    def lives(self, artist_id, offset, limit):
        return self.page(f"""SELECT {LIVE_COLUMNS},
          (SELECT count(*) FROM performances p WHERE p.archive_id=l.id AND p.archived_at IS NULL) performance_count
          {LIVE_FROM} WHERE {LIVE_VISIBLE} AND {SCOPE}""",
                         {"artist":artist_id},offset,limit,"COALESCE(q.broadcast_at,q.published_at) DESC NULLS LAST,q.id DESC")

    def live(self, key):
        rows = self.rows(f"SELECT {LIVE_COLUMNS} {LIVE_FROM} WHERE {LIVE_VISIBLE} AND l.id=:id", {"id":key})
        if not rows:
            return None
        row = rows[0]
        row["performances"] = self.rows(f"SELECT * FROM ({PERFORMANCE_SQL}) p WHERE archive_id=:id ORDER BY ordinal,id", {"id":key})
        return row

    def search(self, query, offset, limit):
        pattern = "%" + query.replace("\\","\\\\").replace("%","\\%").replace("_","\\_") + "%"
        params = {"query":pattern,"offset":offset,"limit":limit}
        rows = self.rows(f"""{SEARCH_CANDIDATES_SQL}, page AS MATERIALIZED (
        SELECT candidates.*,count(*) OVER() _total FROM candidates
        ORDER BY broadcast_at DESC NULLS LAST,archive_id DESC,ordinal,id
        LIMIT :limit OFFSET :offset)
        SELECT p.*,COALESCE(p.singer_id,l.primary_artist_id) artist_id,
        COALESCE(p.singer_name,a.name_native,'') artist_name,p.singer_name_ko artist_name_ko,
        'https://www.youtube.com/watch?v='||v.platform_video_id youtube_url,
        v.title video_title,page.broadcast_at,
        (page.broadcast_at AT TIME ZONE 'Asia/Seoul')::date performed_on,page._total
        FROM page JOIN LATERAL (SELECT * FROM ({PERFORMANCE_SQL}) detail
          WHERE detail.id=page.id) p ON true
        JOIN live_archives l ON l.id=page.archive_id
        JOIN videos v ON v.id=l.video_id LEFT JOIN artists a ON a.id=l.primary_artist_id AND a.archived_at IS NULL
        ORDER BY page.broadcast_at DESC NULLS LAST,page.archive_id DESC,page.ordinal,page.id""",params)
        total = rows[0].pop("_total") if rows else (
            self.rows(SEARCH_CANDIDATES_SQL + " SELECT count(*) n FROM candidates",params)[0]["n"]
            if offset else 0)
        for row in rows[1:]:
            row.pop("_total")
        return {"items":rows,"total":total,"offset":offset,"limit":limit}

    def statistic_rows(self, artist_id):
        cte = f"""WITH archives AS (SELECT l.id,COALESCE(l.broadcast_at,v.published_at) happened
        {LIVE_FROM} WHERE {LIVE_VISIBLE} AND {SCOPE}),
        entries AS (SELECT p.*,a.happened FROM ({PERFORMANCE_SQL}) p JOIN archives a ON a.id=p.archive_id
        WHERE EXISTS (SELECT 1 FROM performance_artists pa WHERE pa.performance_id=p.id AND pa.artist_id=:artist))"""
        songs = self.rows(cte+""" SELECT song_key,MIN(song_title) title,
        MIN(NULLIF(btrim(song_title_ko),'')) title_ko,MIN(original_artist) artist,
        MIN(NULLIF(btrim(original_artist_ko),'')) artist_ko,
        originals,COUNT(*) count,MAX(happened) last_date,string_agg(DISTINCT search_text,' ') search
        FROM entries GROUP BY song_key,originals ORDER BY count DESC,song_key""",{"artist":artist_id})
        months = self.rows(cte+""" SELECT count(*) total,count(*) FILTER(WHERE EXISTS
        (SELECT 1 FROM entries e WHERE e.archive_id=archives.id)) with_setlist,
        to_char(happened AT TIME ZONE 'Asia/Seoul','YYYY-MM') month_key,
        count(*) FILTER(WHERE happened<=CURRENT_TIMESTAMP) activity_count
        FROM archives GROUP BY month_key ORDER BY month_key NULLS LAST""",{"artist":artist_id})
        return songs, months

    def concerts(self, offset, limit, artist_id=None, start=None, end=None, key=None):
        day = "COALESCE((c.starts_at AT TIME ZONE 'Asia/Seoul')::date,c.event_date)"
        return self.page(f"""SELECT c.id,participants.ids artist_ids,
        COALESCE(CAST(:artist AS integer),participants.ids[1]) artist_id,c.title,
        c.starts_at,c.event_date,c.city,c.venue,c.event_format,c.status,
        'live_event' event_type,doc.source_url,ticket.url ticket_url,ticket.price_text
        FROM concerts c
        JOIN LATERAL (SELECT array_agg(ca.artist_id ORDER BY ca.position,ca.id) ids
          FROM concert_artists ca JOIN artists a ON a.id=ca.artist_id
          WHERE ca.concert_id=c.id AND a.archived_at IS NULL AND a.show_in_catalog) participants ON participants.ids IS NOT NULL
        LEFT JOIN source_documents doc ON doc.id=c.source_document_id
        LEFT JOIN LATERAL (SELECT url,price_text FROM concert_ticket_windows WHERE concert_id=c.id
          ORDER BY opens_at NULLS LAST,id LIMIT 1) ticket ON true
        WHERE c.archived_at IS NULL AND c.status<>'cancelled'
        AND (CAST(:artist AS integer) IS NULL OR :artist=ANY(participants.ids))
        AND (CAST(:start AS date) IS NULL OR {day}>=:start)
        AND (CAST(:end AS date) IS NULL OR {day}<:end)
        AND (CAST(:key AS integer) IS NULL OR c.id=:key)""",
        {"artist":artist_id,"start":start,"end":end,"key":key},offset,limit,"COALESCE(q.starts_at,q.event_date::timestamp AT TIME ZONE 'Asia/Seoul') NULLS LAST,q.id")

    def albums(self, artist_id=None, key=None):
        return self.rows("""SELECT a.id::text id,a.title_native name,a.title_ko name_ko,a.album_type,
        concat_ws('-',a.release_year::text,lpad(a.release_month::text,2,'0'),lpad(a.release_day::text,2,'0')) release_date,
        a.cover_image_url image_url,
        CASE WHEN a.spotify_album_id IS NOT NULL THEN 'https://open.spotify.com/album/'||a.spotify_album_id END spotify_url,
        (SELECT count(*) FROM album_tracks t JOIN recordings r ON r.id=t.recording_id AND r.archived_at IS NULL WHERE t.album_id=a.id) total_tracks
        FROM albums a WHERE a.archived_at IS NULL
        AND (CAST(:key AS integer) IS NULL OR a.id=:key)
        AND (CAST(:artist AS integer) IS NULL
          OR EXISTS (SELECT 1 FROM album_artists aa WHERE aa.album_id=a.id AND aa.artist_id=:artist)
          OR EXISTS (SELECT 1 FROM album_tracks t JOIN recordings r ON r.id=t.recording_id AND r.archived_at IS NULL
            JOIN recording_artists ra ON ra.recording_id=r.id
            WHERE t.album_id=a.id AND ra.artist_id=:artist))
        ORDER BY a.release_year DESC NULLS LAST,a.release_month DESC NULLS LAST,a.release_day DESC NULLS LAST,a.id DESC""",
        {"artist":artist_id,"key":key})

    def tracks(self, album_id):
        return self.rows("""SELECT t.id::text id,r.id recording_id,r.song_id,r.title_native name,r.title_ko name_ko,
        r.duration_ms,t.disc_number,t.track_number,
        EXISTS(SELECT 1 FROM recording_lyrics rl WHERE rl.recording_id=r.id AND rl.archived_at IS NULL) has_lyrics
        FROM album_tracks t JOIN recordings r ON r.id=t.recording_id AND r.archived_at IS NULL
        WHERE t.album_id=:id ORDER BY t.disc_number,t.track_number,t.id""",{"id":album_id})

    def lyrics(self, recording_id):
        rows = self.rows("""SELECT r.id recording_id,r.song_id,r.title_native original_title,
        COALESCE((SELECT string_agg(a.name_native,' · ' ORDER BY ra.position,ra.id) FROM recording_artists ra
          JOIN artists a ON a.id=ra.artist_id AND a.archived_at IS NULL WHERE ra.recording_id=r.id),'') artist_name,
        l.original_lyrics,COALESCE(l.translation_ko,'') translation_ko,COALESCE(l.pronunciation_ko,'') pronunciation_ko,
        d.source_url lyrics_source_url,COALESCE(d.source_kind,'') lyrics_source_type,false needs_review
        FROM recording_lyrics l JOIN recordings r ON r.id=l.recording_id
        LEFT JOIN source_documents d ON d.id=l.source_document_id
        WHERE r.id=:id AND r.archived_at IS NULL AND l.archived_at IS NULL""",{"id":recording_id})
        return rows[0] if rows else None
