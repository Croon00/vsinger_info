-- Original/cover song world cup results submitted by browsers. Anonymous: a random per-browser
-- client ID only, no IP or account. Runs from the local dev proxy are flagged and kept out
-- of public statistics. Songs are identified by their official YouTube video ID.
SET LOCAL search_path = public, pg_catalog;

CREATE TABLE public.worldcup_runs (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  submission_id UUID NOT NULL UNIQUE,
  client_id UUID NOT NULL,
  song_kind TEXT NOT NULL CHECK (song_kind IN ('original','cover')),
  scope_kind TEXT NOT NULL CHECK (scope_kind IN ('agency','artists','random')),
  scope_label TEXT NOT NULL CHECK (length(btrim(scope_label)) BETWEEN 1 AND 200),
  bracket_size SMALLINT NOT NULL CHECK (bracket_size IN (16,32,64,128)),
  duration_seconds INTEGER NOT NULL CHECK (duration_seconds BETWEEN 0 AND 604800),
  winner_video_id TEXT NOT NULL CHECK (winner_video_id ~ '^[A-Za-z0-9_-]{11}$'),
  is_local BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX worldcup_runs_client_idx ON public.worldcup_runs (client_id, created_at);
CREATE INDEX worldcup_runs_winner_idx ON public.worldcup_runs (song_kind, winner_video_id) WHERE NOT is_local;

CREATE TABLE public.worldcup_matches (
  run_id BIGINT NOT NULL REFERENCES public.worldcup_runs(id) ON DELETE CASCADE,
  match_index SMALLINT NOT NULL CHECK (match_index BETWEEN 0 AND 126),
  round_size SMALLINT NOT NULL CHECK (round_size IN (2,4,8,16,32,64,128)),
  winner_video_id TEXT NOT NULL CHECK (winner_video_id ~ '^[A-Za-z0-9_-]{11}$'),
  loser_video_id TEXT NOT NULL CHECK (loser_video_id ~ '^[A-Za-z0-9_-]{11}$'),
  PRIMARY KEY (run_id, match_index),
  CHECK (winner_video_id <> loser_video_id)
);
CREATE INDEX worldcup_matches_winner_idx ON public.worldcup_matches (winner_video_id);
CREATE INDEX worldcup_matches_loser_idx ON public.worldcup_matches (loser_video_id);

COMMENT ON TABLE public.worldcup_runs IS '완료된 곡 월드컵 한 판(오리지널 또는 커버). 익명 브라우저 ID만 저장';
COMMENT ON COLUMN public.worldcup_runs.is_local IS '로컬 개발 프록시에서 제출됨. 공개 통계에서 제외';
COMMENT ON TABLE public.worldcup_matches IS '월드컵 한 판의 경기별 승패(오리지널 공식 MV 또는 커버 영상 ID 기준)';
