-- Revision 006: provider artist credits per stored Spotify track ID. 001-005 are immutable.
-- recording_artists links only registered artists, so a release saved whole (an artist's
-- own album with guest or remix tracks) could not show who performs each track. This keeps
-- Spotify's own credit list as evidence, unregistered artists included, without creating
-- artists. Owned by its recording_external_ids row (CASCADE with it). No existing table or
-- column is changed; catalog_instance.schema_version (catalog-v2) is unchanged.

CREATE TABLE public.recording_provider_credits (
  id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  platform TEXT NOT NULL DEFAULT 'spotify' CHECK (platform = 'spotify'),
  track_id TEXT NOT NULL CHECK (track_id ~ '^[A-Za-z0-9]{22}$'),
  position SMALLINT NOT NULL CHECK (position BETWEEN 0 AND 99),
  provider_artist_id TEXT NOT NULL CHECK (provider_artist_id ~ '^[A-Za-z0-9]{22}$'),
  name TEXT NOT NULL CHECK (length(btrim(name)) > 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (platform, track_id, position),
  FOREIGN KEY (platform, track_id) REFERENCES public.recording_external_ids(platform, external_id) ON DELETE CASCADE
);

CREATE INDEX recording_provider_credits_artist_idx ON public.recording_provider_credits (provider_artist_id);

COMMENT ON TABLE public.recording_provider_credits IS 'Spotify 트랙의 원문 아티스트 명의. 등록되지 않은 아티스트도 이름 그대로 보존';
COMMENT ON COLUMN public.recording_provider_credits.track_id IS 'recording_external_ids(platform=spotify).external_id';
COMMENT ON COLUMN public.recording_provider_credits.position IS 'Spotify 명의 순서(0부터)';
COMMENT ON COLUMN public.recording_provider_credits.provider_artist_id IS 'Spotify 아티스트 ID. 등록 계정과의 연결은 external_accounts.platform_id로 판단';
COMMENT ON COLUMN public.recording_provider_credits.name IS 'Spotify가 표시하는 명의 이름';
