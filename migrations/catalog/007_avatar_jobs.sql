-- Automatic initial avatars. No network calls or existing-artist backfill in DDL.
SET LOCAL search_path = public, pg_catalog;

CREATE TABLE public.avatar_jobs (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  artist_id INTEGER NOT NULL REFERENCES public.artists(id) ON DELETE RESTRICT,
  sources JSONB NOT NULL CHECK (jsonb_typeof(sources) = 'array'),
  source_fingerprint TEXT NOT NULL CHECK (source_fingerprint ~ '^[0-9a-f]{32}$'),
  request_run TEXT NOT NULL DEFAULT 'automatic' CHECK (length(request_run) BETWEEN 1 AND 120),
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN
    ('pending','running','retry','succeeded','no_source','skipped_existing','conflict','failed')),
  attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
  max_attempts INTEGER NOT NULL DEFAULT 5 CHECK (max_attempts BETWEEN 1 AND 10),
  next_attempt_at TIMESTAMPTZ,
  lease_owner TEXT,
  lease_expires_at TIMESTAMPTZ,
  last_error TEXT,
  result JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(result) = 'object'),
  finished_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (artist_id,source_fingerprint,request_run),
  CHECK (attempt_count <= max_attempts),
  CHECK ((lease_owner IS NULL) = (lease_expires_at IS NULL)),
  CHECK ((status = 'running') = (lease_owner IS NOT NULL)),
  CHECK ((status IN ('succeeded','no_source','skipped_existing','conflict','failed')) = (finished_at IS NOT NULL))
);
CREATE INDEX avatar_jobs_due_idx ON public.avatar_jobs(next_attempt_at,id)
  WHERE status IN ('pending','retry','running');

CREATE FUNCTION public.avatar_sources(artist integer) RETURNS jsonb
LANGUAGE sql STABLE SET search_path = public,pg_catalog AS $$
  SELECT COALESCE(jsonb_agg(jsonb_build_object(
    'id',e.id,'platform',e.platform,'platform_id',e.platform_id,'handle',e.handle,'url',e.url,
    'is_primary',ae.is_primary,'position',ae.position)
    ORDER BY CASE e.platform WHEN 'youtube' THEN 0 ELSE 1 END,ae.is_primary DESC,ae.position,e.id),'[]'::jsonb)
  FROM artist_external_accounts ae JOIN external_accounts e ON e.id=ae.account_id
  WHERE ae.artist_id=artist AND ae.relationship='owner' AND e.archived_at IS NULL
    AND e.platform IN ('youtube','x');
$$;

CREATE FUNCTION public.avatar_enqueue(artist integer, run_label text DEFAULT 'automatic') RETURNS bigint
LANGUAGE plpgsql SET search_path = public,pg_catalog AS $$
DECLARE image text; archived timestamptz; candidates jsonb; job bigint;
BEGIN
  SELECT avatar_url,archived_at INTO image,archived FROM artists WHERE id=artist FOR UPDATE;
  IF NOT FOUND OR image IS NOT NULL OR archived IS NOT NULL THEN RETURN NULL; END IF;
  candidates := avatar_sources(artist);
  IF candidates = '[]'::jsonb THEN RETURN NULL; END IF;
  INSERT INTO avatar_jobs(artist_id,sources,source_fingerprint,request_run)
    VALUES (artist,candidates,md5(candidates::text),run_label)
    ON CONFLICT (artist_id,source_fingerprint,request_run) DO NOTHING RETURNING id INTO job;
  IF job IS NULL THEN
    SELECT id INTO job FROM avatar_jobs WHERE artist_id=artist
      AND source_fingerprint=md5(candidates::text) AND request_run=run_label;
  END IF;
  RETURN job;
END $$;

CREATE FUNCTION public.avatar_artist_changed() RETURNS trigger
LANGUAGE plpgsql SET search_path = public,pg_catalog AS $$
BEGIN
  PERFORM avatar_enqueue(NEW.id);
  RETURN NEW;
END $$;
CREATE TRIGGER avatar_artist_enqueue AFTER INSERT OR UPDATE OF avatar_url,archived_at ON public.artists
  FOR EACH ROW EXECUTE FUNCTION public.avatar_artist_changed();

CREATE FUNCTION public.avatar_link_changed() RETURNS trigger
LANGUAGE plpgsql SET search_path = public,pg_catalog AS $$
BEGIN
  IF TG_OP <> 'INSERT' THEN PERFORM avatar_enqueue(OLD.artist_id); END IF;
  IF TG_OP <> 'DELETE' THEN PERFORM avatar_enqueue(NEW.artist_id); RETURN NEW; END IF;
  RETURN OLD;
END $$;
CREATE TRIGGER avatar_link_enqueue AFTER INSERT OR UPDATE OR DELETE ON public.artist_external_accounts
  FOR EACH ROW EXECUTE FUNCTION public.avatar_link_changed();

CREATE FUNCTION public.avatar_account_changed() RETURNS trigger
LANGUAGE plpgsql SET search_path = public,pg_catalog AS $$
DECLARE artist integer;
BEGIN
  FOR artist IN SELECT DISTINCT artist_id FROM artist_external_accounts WHERE account_id=NEW.id ORDER BY artist_id LOOP
    PERFORM avatar_enqueue(artist);
  END LOOP;
  RETURN NEW;
END $$;
CREATE TRIGGER avatar_account_enqueue AFTER UPDATE OF platform,platform_id,handle,url,archived_at ON public.external_accounts
  FOR EACH ROW EXECUTE FUNCTION public.avatar_account_changed();
