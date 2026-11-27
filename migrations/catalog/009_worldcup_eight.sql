ALTER TABLE public.worldcup_runs
  DROP CONSTRAINT worldcup_runs_bracket_size_check,
  ADD CONSTRAINT worldcup_runs_bracket_size_check CHECK (bracket_size IN (8,16,32,64,128));
