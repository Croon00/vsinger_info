-- Revision 003: latin names/titles use plain printable ASCII only.
-- Letters with diacritics (e.g. o-macron) are stored without the mark: Tokyo, not Tōkyō.
-- Existing rows were checked read-only before this revision (2026-09-27: 0 violations).
-- Column contract and catalog_instance.schema_version (catalog-v2) are unchanged.

ALTER TABLE public.artists ADD CONSTRAINT artists_name_latin_ascii
  CHECK (name_latin IS NULL OR name_latin ~ '^[\x20-\x7E]+$');
ALTER TABLE public.songs ADD CONSTRAINT songs_title_latin_ascii
  CHECK (title_latin IS NULL OR title_latin ~ '^[\x20-\x7E]+$');

COMMENT ON COLUMN public.artists.name_latin IS '공식 영어/로마자 표기. 발음 부호 없는 ASCII만 허용. 원어와 같으면 생략 가능';
COMMENT ON COLUMN public.songs.title_latin IS '영어/로마자 표기. 발음 부호 없는 ASCII만 허용';
