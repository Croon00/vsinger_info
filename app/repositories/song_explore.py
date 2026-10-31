"""Read-only, paginated song exploration with scoped aggregates."""
from app.repositories.catalog_read import CatalogReadRepository
from app.repositories.youtube_video_format import SHORT_MARKER, SHORT_VISIBILITY
from app.repositories.youtube_cover_rules import COVER_TITLE_SQL, COVER_TITLE_PARAMS
from app.repositories.shared_youtube import COVER_CREDITS_CTE, SHARED_PARAMS


def explore(session, *, kind, agency, q, order, offset, limit, repository=None):
    repo = repository or CatalogReadRepository(session)
    params = {'agency': agency, 'query': '%' + q.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%', 'short_marker': SHORT_MARKER, **COVER_TITLE_PARAMS, **SHARED_PARAMS}
    scope = """a.archived_at IS NULL AND a.show_in_catalog AND
      (:agency='all' OR (:agency='independent' AND g.id IS NULL) OR g.name_native=:agency)"""
    if kind == 'utawaku':
        sql = f"""WITH artist_search AS MATERIALIZED (
          SELECT a.id,concat_ws(' ',a.name_native,a.name_ko,a.name_latin,
            (SELECT string_agg(al.alias,' ') FROM artist_aliases al WHERE al.artist_id=a.id)) singer_search
          FROM artists a WHERE a.archived_at IS NULL AND a.show_in_catalog
        ), eligible AS (
          SELECT p.id,s.id song_id,p.raw_title,p.raw_artist,p.start_seconds,p.archive_id,
            v.platform_video_id,COALESCE(l.broadcast_at,v.published_at) published_at,a.id artist_id,
            CASE WHEN s.id IS NOT NULL THEN 'song:'||s.id::text ELSE
              'raw:'||md5(lower(btrim(p.raw_title))||'/'||lower(btrim(COALESCE(p.raw_artist,'')))) END key,
            COALESCE(s.title_native,p.raw_title) title,s.title_ko,
            asearch.singer_search
          FROM performances p JOIN live_archives l ON l.id=p.archive_id
          JOIN videos v ON v.id=l.video_id LEFT JOIN songs s ON s.id=p.song_id AND s.archived_at IS NULL
          LEFT JOIN performance_artists pa ON pa.performance_id=p.id
          JOIN artists a ON a.id=COALESCE(pa.artist_id,l.primary_artist_id)
          JOIN artist_search asearch ON asearch.id=a.id
          LEFT JOIN agencies g ON g.id=a.agency_id AND g.archived_at IS NULL
          WHERE p.archived_at IS NULL AND l.archived_at IS NULL AND v.archived_at IS NULL
            AND v.availability IN ('public','unlisted','unknown') AND {scope}
        ) SELECT key,min(title) title,min(title_ko) title_ko,
          COALESCE((SELECT string_agg(ar.name_native,' · ' ORDER BY sa.position,sa.id)
            FROM song_artists sa JOIN artists ar ON ar.id=sa.artist_id AND ar.archived_at IS NULL
            WHERE sa.song_id=min(e.song_id)),min(raw_artist),'') artist_name,
          count(DISTINCT id) performance_count,count(DISTINCT artist_id) artist_count,
          (array_agg(archive_id ORDER BY published_at DESC NULLS LAST,id DESC))[1] archive_id,
          (array_agg(start_seconds ORDER BY published_at DESC NULLS LAST,id DESC))[1] start_seconds,
          NULL::text youtube_video_id,NULL::bigint view_count,NULL::timestamptz views_updated_at,
          max(published_at) published_at,concat_ws(' ',string_agg(DISTINCT singer_search,' '),
            (SELECT string_agg(concat_ws(' ',ar.name_native,ar.name_ko,ar.name_latin,
              (SELECT string_agg(al.alias,' ') FROM artist_aliases al WHERE al.artist_id=ar.id)),' ')
              FROM song_artists sa JOIN artists ar ON ar.id=sa.artist_id AND ar.archived_at IS NULL
              WHERE sa.song_id=min(e.song_id))) search_text
          FROM eligible e GROUP BY key"""
    else:
        common = """v.platform_video_id youtube_video_id,
          (cs.provider_state->'youtube_video_statistics'->v.platform_video_id->>'view_count')::bigint view_count,
          (cs.provider_state->'youtube_video_statistics'->v.platform_video_id->>'captured_at')::timestamptz views_updated_at,
          v.published_at,NULL::bigint performance_count,NULL::bigint artist_count,
          NULL::integer archive_id,NULL::integer start_seconds"""
        if kind == 'cover':
            cover_scope = """a.archived_at IS NULL AND
              (a.show_in_catalog OR EXISTS(SELECT 1 FROM shared_members shared
                WHERE shared.group_id=a.id AND shared.account_id=v.source_account_id))
              AND (:agency='all' OR (:agency='independent' AND g.id IS NULL) OR g.name_native=:agency)"""
            sql = f"""WITH {COVER_CREDITS_CTE} SELECT 'cover:'||c.id::text key,v.title title,NULL::text title_ko,
              string_agg(DISTINCT a.name_native,' · ' ORDER BY a.name_native) artist_name,{common},
              string_agg(DISTINCT concat_ws(' ',a.name_native,a.name_ko,a.name_latin,
                (SELECT string_agg(al.alias,' ') FROM artist_aliases al WHERE al.artist_id=a.id)),' ') search_text
              FROM covers c JOIN videos v ON v.id=c.video_id
              JOIN external_accounts ea ON ea.id=v.source_account_id AND ea.archived_at IS NULL
              JOIN cover_credits cc ON cc.cover_id=c.id
              JOIN artists a ON a.id=cc.artist_id LEFT JOIN agencies g ON g.id=a.agency_id AND g.archived_at IS NULL
              LEFT JOIN collection_states cs ON cs.external_account_id=v.source_account_id
              WHERE c.archived_at IS NULL AND v.archived_at IS NULL AND v.platform='youtube'
                AND v.availability IN ('public','unlisted','unknown') AND {cover_scope}
                AND {SHORT_VISIBILITY}
                AND {COVER_TITLE_SQL}
              GROUP BY c.id,v.id,cs.external_account_id"""
        else:
            # Singles and albums can reference different recordings of the
            # same YouTube upload. Collapse those before counting/pagination;
            # recordings without a visible video keep their own identity.
            sql = f"""SELECT 'recording:'||min(r.id)::text key,min(r.title_native) title,min(r.title_ko) title_ko,
              string_agg(DISTINCT a.name_native,' · ' ORDER BY a.name_native) artist_name,{common},
              string_agg(DISTINCT concat_ws(' ',r.title_native,r.title_ko,a.name_native,a.name_ko,a.name_latin,
                (SELECT string_agg(al.alias,' ') FROM artist_aliases al WHERE al.artist_id=a.id)),' ') search_text
              FROM recordings r JOIN recording_artists ra ON ra.recording_id=r.id
              JOIN artists a ON a.id=ra.artist_id LEFT JOIN agencies g ON g.id=a.agency_id AND g.archived_at IS NULL
              LEFT JOIN videos v ON v.id=r.official_video_id AND v.archived_at IS NULL
                AND v.availability IN ('public','unlisted','unknown') AND v.platform='youtube'
              LEFT JOIN collection_states cs ON cs.external_account_id=v.source_account_id
              WHERE r.archived_at IS NULL AND {scope}
                AND NOT EXISTS(SELECT 1 FROM covers c WHERE c.video_id=r.official_video_id AND c.archived_at IS NULL AND {COVER_TITLE_SQL})
              GROUP BY CASE WHEN v.id IS NULL THEN r.id END,v.id,cs.external_account_id"""
    sql = f"SELECT * FROM ({sql}) entries WHERE concat_ws(' ',title,title_ko,artist_name,search_text) ILIKE :query"
    if kind == 'utawaku':
        sql += " AND NULLIF(btrim(artist_name),'') IS NOT NULL"
    if order == 'name':
        ordering = 'q.title,q.key'
    elif order == 'latest':
        ordering = 'q.published_at DESC NULLS LAST,q.key'
    else:
        metric = 'performance_count' if kind == 'utawaku' else 'view_count'
        ordering = f"q.{metric} {'ASC' if order == 'low' else 'DESC'} NULLS LAST,q.title,q.key"
    return repo.page(sql, params, offset, limit, ordering)


def performers(repository, song_key, agency):
    params = {'agency': agency, 'key': song_key}
    if song_key.startswith('song:'):
        condition = 'p.song_id=:song_id AND s.id IS NOT NULL'
        params['song_id'] = int(song_key.split(':')[1])
    else:
        condition = "s.id IS NULL AND 'raw:'||md5(lower(btrim(p.raw_title))||'/'||lower(btrim(COALESCE(p.raw_artist,''))))=:key"
    return repository.rows(f"""SELECT DISTINCT a.id,a.name_native name,a.name_ko display_name
      FROM performances p JOIN live_archives l ON l.id=p.archive_id JOIN videos v ON v.id=l.video_id
      LEFT JOIN songs s ON s.id=p.song_id AND s.archived_at IS NULL
      LEFT JOIN performance_artists pa ON pa.performance_id=p.id
      JOIN artists a ON a.id=COALESCE(pa.artist_id,l.primary_artist_id)
      LEFT JOIN agencies g ON g.id=a.agency_id AND g.archived_at IS NULL
      WHERE p.archived_at IS NULL AND l.archived_at IS NULL AND v.archived_at IS NULL
        AND v.availability IN ('public','unlisted','unknown') AND a.archived_at IS NULL AND a.show_in_catalog
        AND (:agency='all' OR (:agency='independent' AND g.id IS NULL) OR g.name_native=:agency)
        AND {condition} ORDER BY a.name_native,a.id""", params)
