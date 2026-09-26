-- Revision 004: song identity support. 001-003 are immutable.
-- Adds match keys (setlist text -> song decisions), external song IDs, song aliases
-- and an append-only merge log. No existing table or column is changed.

CREATE TABLE public.song_aliases (
  id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  song_id INTEGER NOT NULL REFERENCES public.songs(id) ON DELETE CASCADE,
  alias TEXT NOT NULL CHECK (length(btrim(alias)) > 0),
  normalized_alias TEXT NOT NULL CHECK (length(btrim(normalized_alias)) > 0),
  locale TEXT CHECK (locale IS NULL OR locale ~ '^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$'),
  source TEXT NOT NULL CHECK (source IN ('manual','vocadb','utaitedb','musicbrainz','wikidata','spotify','setlist')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (song_id, normalized_alias)
);

CREATE TABLE public.song_external_ids (
  id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  song_id INTEGER NOT NULL REFERENCES public.songs(id) ON DELETE CASCADE,
  provider TEXT NOT NULL CHECK (provider IN ('vocadb','utaitedb','musicbrainz_work','wikidata')),
  external_id TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  -- One external entity maps to exactly one song: the duplicate-prevention anchor.
  UNIQUE (provider, external_id),
  CHECK (
    (provider IN ('vocadb','utaitedb') AND external_id ~ '^[1-9][0-9]*$')
    OR (provider = 'musicbrainz_work' AND external_id ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
    OR (provider = 'wikidata' AND external_id ~ '^Q[1-9][0-9]*$')
  )
);

CREATE TABLE public.song_match_keys (
  id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  key_version SMALLINT NOT NULL DEFAULT 1 CHECK (key_version >= 1),
  title_key TEXT NOT NULL CHECK (length(btrim(title_key)) > 0),
  artist_key TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','confirmed','ambiguous','rejected','not_song')),
  song_id INTEGER REFERENCES public.songs(id) ON DELETE RESTRICT,
  sample_raw_title TEXT NOT NULL CHECK (length(btrim(sample_raw_title)) > 0),
  sample_raw_artist TEXT,
  occurrence_count INTEGER NOT NULL DEFAULT 0 CHECK (occurrence_count >= 0),
  decided_by TEXT CHECK (decided_by IS NULL OR decided_by IN ('existing_link','manual','vocadb','utaitedb','musicbrainz','wikidata','spotify')),
  decided_at TIMESTAMPTZ,
  evidence JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(evidence) = 'object'),
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
  UNIQUE (key_version, title_key, artist_key),
  CHECK ((status = 'confirmed') = (song_id IS NOT NULL)),
  CHECK ((status = 'pending') = (decided_at IS NULL)),
  CHECK ((decided_at IS NULL) = (decided_by IS NULL))
);

CREATE TABLE public.song_merges (
  id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  source_song_id INTEGER NOT NULL UNIQUE REFERENCES public.songs(id) ON DELETE RESTRICT,
  target_song_id INTEGER NOT NULL REFERENCES public.songs(id) ON DELETE RESTRICT,
  import_id INTEGER REFERENCES public.catalog_imports(id) ON DELETE RESTRICT,
  reason TEXT NOT NULL CHECK (length(btrim(reason)) > 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  CHECK (source_song_id <> target_song_id)
);

CREATE INDEX song_aliases_normalized_alias_idx ON public.song_aliases (normalized_alias);
CREATE INDEX song_external_ids_song_id_idx ON public.song_external_ids (song_id);
CREATE INDEX song_match_keys_song_id_idx ON public.song_match_keys (song_id) WHERE song_id IS NOT NULL;
CREATE INDEX song_match_keys_status_count_idx ON public.song_match_keys (status, occurrence_count DESC);
CREATE INDEX song_merges_target_song_id_idx ON public.song_merges (target_song_id);

CREATE TRIGGER song_aliases_touch BEFORE UPDATE ON public.song_aliases
  FOR EACH ROW EXECUTE FUNCTION public.catalog_touch_timestamp();
CREATE TRIGGER song_external_ids_touch BEFORE UPDATE ON public.song_external_ids
  FOR EACH ROW EXECUTE FUNCTION public.catalog_touch_timestamp();
CREATE TRIGGER song_match_keys_touch BEFORE UPDATE ON public.song_match_keys
  FOR EACH ROW EXECUTE FUNCTION public.catalog_touch_version();
CREATE TRIGGER song_merges_immutable BEFORE UPDATE OR DELETE ON public.song_merges
  FOR EACH ROW EXECUTE FUNCTION public.catalog_reject_history_mutation();
CREATE TRIGGER song_aliases_parent_touch AFTER INSERT OR UPDATE OR DELETE ON public.song_aliases
  FOR EACH ROW EXECUTE FUNCTION public.catalog_touch_parent('songs','song_id');
CREATE TRIGGER song_external_ids_parent_touch AFTER INSERT OR UPDATE OR DELETE ON public.song_external_ids
  FOR EACH ROW EXECUTE FUNCTION public.catalog_touch_parent('songs','song_id');

COMMENT ON TABLE public.song_aliases IS '곡의 다른 표기·팬 호칭. 검색·매칭용이며 title_* 정규 표기를 대신하지 않음';
COMMENT ON COLUMN public.song_aliases.normalized_alias IS 'app/core/song_keys.normalize_text 결과';
COMMENT ON COLUMN public.song_aliases.locale IS '표기 언어(ko, ja, en 등). 모르면 NULL';
COMMENT ON COLUMN public.song_aliases.source IS '별칭 출처';
COMMENT ON TABLE public.song_external_ids IS '외부 DB의 작품 ID. 같은 provider+ID는 한 곡에만 연결';
COMMENT ON TABLE public.song_match_keys IS '세트리스트 원문 키(정규화 곡명+원곡자)별 곡 판정. 확정 키만 performances.song_id 연결 근거';
COMMENT ON COLUMN public.song_match_keys.key_version IS '정규화 규칙 버전. 규칙이 바뀌면 새 버전 키로 다시 집계';
COMMENT ON COLUMN public.song_match_keys.artist_key IS '정규화 원곡자. 원문에 없으면 빈 문자열';
COMMENT ON COLUMN public.song_match_keys.status IS 'pending(미판정), confirmed(곡 확정), ambiguous(동명곡 등 개별 판단), rejected(후보 거절), not_song(곡이 아닌 행)';
COMMENT ON COLUMN public.song_match_keys.occurrence_count IS '마지막 집계 시점의 가창 행 수';
COMMENT ON COLUMN public.song_match_keys.evidence IS '판정 근거와 후보 요약';
COMMENT ON TABLE public.song_merges IS '중복 곡 병합 기록. source 곡은 보관하고 target으로 안내. 추가만 허용';
