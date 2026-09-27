-- Revision 005: recordings may carry an ISRC next to their Spotify track ID.
-- The 001 allow-list CHECK (platform = 'spotify') is replaced, not widened in place, so
-- the constraint names differ from the 001 snapshot; migrate_catalog.py knows both.
-- ISRC is stored upper-case without hyphens (JPU902602729). UNIQUE (platform, external_id)
-- from 001 keeps one recording per ISRC, which is how releases of one recording are joined.
-- Column contract and catalog_instance.schema_version (catalog-v2) are unchanged.

ALTER TABLE public.recording_external_ids DROP CONSTRAINT recording_external_ids_platform_check1;
ALTER TABLE public.recording_external_ids ADD CONSTRAINT recording_external_ids_platform_allowed
  CHECK (platform IN ('spotify','isrc'));
ALTER TABLE public.recording_external_ids ADD CONSTRAINT recording_external_ids_id_format
  CHECK ((platform = 'spotify' AND external_id ~ '^[A-Za-z0-9]{22}$')
      OR (platform = 'isrc' AND external_id ~ '^[A-Z]{2}[A-Z0-9]{3}[0-9]{7}$'));

COMMENT ON COLUMN public.recording_external_ids.platform IS 'spotify(트랙 ID), isrc(국제 녹음 코드). 추가 플랫폼은 허용 목록 확장';
COMMENT ON COLUMN public.recording_external_ids.external_id IS 'spotify는 22자 트랙 ID, isrc는 하이픈 없는 대문자 12자';
