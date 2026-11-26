"""World cup runs and statistics. Writes only touch the two world cup tables."""
from sqlalchemy import bindparam, text


def ready(session) -> bool:
    """Migration 008 may be applied after this code is deployed."""
    return bool(session.execute(text("SELECT to_regclass('public.worldcup_runs') IS NOT NULL")).scalar_one())


PLAYABLE = {
    # Official MVs of active recordings (original-song world cup).
    'original': '''SELECT DISTINCT v.platform_video_id FROM videos v
        JOIN recordings r ON r.official_video_id=v.id AND r.archived_at IS NULL
        WHERE v.platform='youtube' AND v.archived_at IS NULL AND v.platform_video_id IN :ids''',
    # Stored cover videos (cover world cup).
    'cover': '''SELECT DISTINCT v.platform_video_id FROM covers c JOIN videos v ON v.id=c.video_id
        WHERE c.archived_at IS NULL AND v.platform='youtube' AND v.archived_at IS NULL
          AND v.platform_video_id IN :ids''',
}


def playable_videos(session, video_ids, song_kind='original'):
    return set(session.execute(text(PLAYABLE[song_kind]).bindparams(bindparam('ids', expanding=True)),
                               {'ids': list(video_ids)}).scalars())


def submission_run(session, submission_id):
    return session.execute(text('SELECT id,is_local,song_kind FROM worldcup_runs WHERE submission_id=:id'),
                           {'id': submission_id}).one_or_none()


def recent_client_runs(session, client_id, minutes=60):
    return session.execute(text('''SELECT count(*) FROM worldcup_runs
        WHERE client_id=:client AND created_at > clock_timestamp() - make_interval(mins => :minutes)'''),
        {'client': client_id, 'minutes': minutes}).scalar_one()


def insert_run(session, submission, champion, is_local):
    run_id = session.execute(text('''INSERT INTO worldcup_runs(submission_id,client_id,song_kind,scope_kind,
        scope_label,bracket_size,duration_seconds,winner_video_id,is_local)
        VALUES (:submission,:client,:kind,:scope,:label,:size,:duration,:winner,:local)
        ON CONFLICT (submission_id) DO NOTHING RETURNING id'''),
        dict(submission=submission.submission_id, client=submission.client_id, kind=submission.song_kind,
             scope=submission.scope_kind, label=submission.scope_label, size=submission.size,
             duration=submission.duration_seconds, winner=champion, local=is_local)).scalar_one_or_none()
    if run_id is None:  # a concurrent duplicate won the race
        return None
    session.execute(text('''INSERT INTO worldcup_matches(run_id,match_index,round_size,winner_video_id,loser_video_id)
        VALUES (:run,:index,:round,:winner,:loser)'''),
        [dict(run=run_id, index=index, round=match.round, winner=match.winner, loser=match.loser)
         for index, match in enumerate(submission.matches)])
    return run_id


STAT_ORDERS = {
    'championships': 'q.championships DESC,q.championship_rate DESC NULLS LAST,q.appearances DESC,q.video_id',
    'championship_rate': 'q.championship_rate DESC NULLS LAST,q.appearances DESC,q.video_id',
    'match_win_rate': 'q.match_win_rate DESC NULLS LAST,(q.match_wins+q.match_losses) DESC,q.video_id',
}

# Title, credited names and agencies per video. Originals use recording credits; covers use
# the official channel owners (the cover's performers).
META = {
    'original': '''SELECT v.platform_video_id video,min(r.title_native) title,min(r.title_ko) title_ko,
          COALESCE(string_agg(DISTINCT a.name_native,' · '),'') artist_name,
          array_remove(array_agg(DISTINCT g.name_native),NULL) agencies
        FROM videos v JOIN recordings r ON r.official_video_id=v.id AND r.archived_at IS NULL
        LEFT JOIN recording_artists ra ON ra.recording_id=r.id
        LEFT JOIN artists a ON a.id=ra.artist_id AND a.archived_at IS NULL
        LEFT JOIN agencies g ON g.id=a.agency_id AND g.archived_at IS NULL
        WHERE v.platform='youtube' AND v.platform_video_id IN (SELECT video FROM per)
        GROUP BY v.platform_video_id''',
    'cover': '''SELECT v.platform_video_id video,min(v.title) title,NULL::text title_ko,
          COALESCE(string_agg(DISTINCT a.name_native,' · '),'') artist_name,
          array_remove(array_agg(DISTINCT g.name_native),NULL) agencies
        FROM covers c JOIN videos v ON v.id=c.video_id
        LEFT JOIN artist_external_accounts ae ON ae.account_id=v.source_account_id AND ae.relationship='owner'
        LEFT JOIN artists a ON a.id=ae.artist_id AND a.archived_at IS NULL
        LEFT JOIN agencies g ON g.id=a.agency_id AND g.archived_at IS NULL
        WHERE v.platform='youtube' AND v.platform_video_id IN (SELECT video FROM per)
        GROUP BY v.platform_video_id''',
}


def stats(session, *, include_local, song_kind='original', agency=None, video_ids=(), order='championships',
          min_appearances=1, offset=0, limit=50):
    params = dict(local=include_local, kind=song_kind, agency=agency, videos=list(video_ids),
                  minimum=min_appearances, offset=offset, limit=limit)
    base = f'''WITH runs AS (SELECT id,winner_video_id FROM worldcup_runs
        WHERE song_kind=:kind AND (:local OR NOT is_local)),
      played AS (SELECT m.* FROM worldcup_matches m JOIN runs r ON r.id=m.run_id),
      appeared AS (SELECT run_id,winner_video_id video FROM played UNION SELECT run_id,loser_video_id FROM played),
      per AS (SELECT video,count(*) appearances FROM appeared GROUP BY video),
      wins AS (SELECT winner_video_id video,count(*) n FROM played GROUP BY 1),
      losses AS (SELECT loser_video_id video,count(*) n FROM played GROUP BY 1),
      champs AS (SELECT winner_video_id video,count(*) n FROM runs GROUP BY 1),
      meta AS ({META[song_kind]}),
      q AS (
        SELECT p.video video_id,m.title,m.title_ko,m.artist_name,p.appearances,
          COALESCE(c.n,0) championships,COALESCE(c.n,0)::float/p.appearances championship_rate,
          COALESCE(w.n,0) match_wins,COALESCE(l.n,0) match_losses,
          COALESCE(w.n,0)::float/NULLIF(COALESCE(w.n,0)+COALESCE(l.n,0),0) match_win_rate
        FROM per p JOIN meta m ON m.video=p.video
        LEFT JOIN champs c ON c.video=p.video LEFT JOIN wins w ON w.video=p.video
        LEFT JOIN losses l ON l.video=p.video
        WHERE p.appearances >= :minimum
          AND (CAST(:agency AS text) IS NULL OR :agency = ANY(m.agencies))
          AND (cardinality(CAST(:videos AS text[]))=0 OR p.video = ANY(CAST(:videos AS text[]))))'''
    rows = [dict(r) for r in session.execute(text(
        f'{base} SELECT q.*,count(*) OVER() _total FROM q ORDER BY {STAT_ORDERS[order]} LIMIT :limit OFFSET :offset'),
        params).mappings()]
    total = rows[0]['_total'] if rows else 0
    for row in rows:
        row.pop('_total')
    total_runs = session.execute(text('''SELECT count(*) FROM worldcup_runs
        WHERE song_kind=:kind AND (:local OR NOT is_local)'''), {'local': include_local, 'kind': song_kind}).scalar_one()
    return dict(items=rows, total=total, offset=offset, limit=limit, total_runs=total_runs)
