-- Catalog v1: approved structure; NO music seed/import data.
-- Apply only through scripts/migrate_catalog.py, in one transaction.
SET LOCAL search_path = public, pg_catalog;



CREATE FUNCTION public.catalog_valid_date(y integer, m integer, d integer)
RETURNS boolean LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE
SET search_path = pg_catalog AS $$
BEGIN
 IF y IS NULL OR m IS NULL OR d IS NULL THEN RETURN false; END IF;
 PERFORM make_date(y,m,d);
 RETURN true;
EXCEPTION WHEN datetime_field_overflow THEN RETURN false;
END $$;

CREATE FUNCTION public.catalog_concert_time_valid(precision_value text, event_day date,
 start_time timestamptz, end_time timestamptz, zone_name text)
RETURNS boolean LANGUAGE plpgsql STABLE
SET search_path = pg_catalog AS $$
BEGIN
 IF zone_name IS NOT NULL AND NOT EXISTS (SELECT FROM pg_timezone_names WHERE name=zone_name) THEN RETURN false; END IF;
 IF precision_value='unknown' THEN
  RETURN event_day IS NULL AND start_time IS NULL AND end_time IS NULL;
 ELSIF precision_value='date' THEN
  RETURN event_day IS NOT NULL AND start_time IS NULL AND end_time IS NULL;
 ELSIF precision_value='datetime' THEN
  RETURN event_day IS NOT NULL AND start_time IS NOT NULL AND zone_name IS NOT NULL
    AND event_day=(start_time AT TIME ZONE zone_name)::date
    AND (end_time IS NULL OR end_time>start_time);
 END IF;
 RETURN false;
END $$;


CREATE TABLE public.artists (
  id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  slug TEXT NOT NULL CHECK (slug IS NULL OR length(btrim(slug)) > 0),
  name_native TEXT NOT NULL CHECK (name_native IS NULL OR length(btrim(name_native)) > 0),
  name_ko TEXT CHECK (name_ko IS NULL OR length(btrim(name_ko)) > 0),
  name_latin TEXT CHECK (name_latin IS NULL OR length(btrim(name_latin)) > 0),
  entity_kind TEXT NOT NULL CHECK (entity_kind IS NULL OR length(btrim(entity_kind)) > 0) CHECK (entity_kind IN ('solo','group')),
  is_virtual BOOLEAN,
  agency_id INTEGER,
  birthday_month SMALLINT,
  birthday_day SMALLINT,
  debut_date DATE,
  bio TEXT CHECK (bio IS NULL OR length(btrim(bio)) > 0),
  theme_color TEXT CHECK (theme_color IS NULL OR length(btrim(theme_color)) > 0),
  avatar_url TEXT CHECK (avatar_url IS NULL OR length(btrim(avatar_url)) > 0) CHECK (avatar_url IS NULL OR avatar_url ~ '^https?://[^[:space:]]+$'),
  show_in_catalog BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
  archived_at TIMESTAMPTZ,
  UNIQUE (slug),
  CHECK ((birthday_month IS NULL AND birthday_day IS NULL) OR (birthday_month IS NOT NULL AND birthday_day IS NOT NULL AND catalog_valid_date(2000,birthday_month,birthday_day))),
  CHECK (theme_color IS NULL OR theme_color ~ '^#[0-9A-Fa-f]{6}$')
);


COMMENT ON COLUMN public.artists.id IS '이 테이블 행의 고유 번호. 새 번호는 DB가 발급하며 기존 DB 번호를 그대로 재사용하지 않음';

COMMENT ON COLUMN public.artists.slug IS '주소에 사용할 고정 식별 문자열. 이름을 바꿔도 자동 변경하지 않음';

COMMENT ON COLUMN public.artists.name_native IS '공식 원어 이름';

COMMENT ON COLUMN public.artists.name_ko IS '검수한 한국어 이름. 임의 번역 금지';

COMMENT ON COLUMN public.artists.name_latin IS '공식 영어/로마자 표기. 원어와 같으면 생략 가능';

COMMENT ON COLUMN public.artists.entity_kind IS 'solo(개인 활동 주체), group(그룹)';

COMMENT ON COLUMN public.artists.is_virtual IS '가상 캐릭터 활동 여부. NULL은 아직 확인 안 됨';

COMMENT ON COLUMN public.artists.agency_id IS 'agencies.id. 소속사가 없거나 미확인일 때 비움';

COMMENT ON COLUMN public.artists.birthday_month IS '생일 월. 생년은 저장하지 않음';

COMMENT ON COLUMN public.artists.birthday_day IS '생일 일. 월과 함께 입력하거나 함께 비움';

COMMENT ON COLUMN public.artists.debut_date IS '정확히 확인된 데뷔 날짜. 연도만 알면 날짜를 만들지 않음';

COMMENT ON COLUMN public.artists.bio IS '검수된 프로필 소개';

COMMENT ON COLUMN public.artists.theme_color IS '캘린더 등에서 쓸 색상. #RRGGBB 형식';

COMMENT ON COLUMN public.artists.avatar_url IS '프로필 이미지 주소. 없으면 화면의 이름 폴백';

COMMENT ON COLUMN public.artists.show_in_catalog IS '사용자 탐색 목록에 노출할지. 수집 여부와 독립';

COMMENT ON COLUMN public.artists.created_at IS '새 DB에 이 행이 처음 등록된 시각. 공연/방송/원문 수집 시각과 별개';

COMMENT ON COLUMN public.artists.updated_at IS '행이 마지막 변경된 시각. 서비스가 수정 때 갱신';

COMMENT ON COLUMN public.artists.version IS '덮어쓰기 충돌을 막는 수정 번호. 저장 시 기대값을 대조하고 증가';

COMMENT ON COLUMN public.artists.archived_at IS '사용 중지 시각. NULL이면 활성. 물리 삭제 대신 보관하는 제안 필드';

CREATE TABLE public.artist_aliases (
  id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  artist_id INTEGER NOT NULL,
  alias TEXT NOT NULL CHECK (alias IS NULL OR length(btrim(alias)) > 0),
  normalized_alias TEXT NOT NULL CHECK (normalized_alias IS NULL OR length(btrim(normalized_alias)) > 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (artist_id, normalized_alias)
);


COMMENT ON COLUMN public.artist_aliases.id IS '이 테이블 행의 고유 번호. 새 번호는 DB가 발급하며 기존 DB 번호를 그대로 재사용하지 않음';

COMMENT ON COLUMN public.artist_aliases.artist_id IS '별칭의 주인. artists.id';

COMMENT ON COLUMN public.artist_aliases.alias IS '사용자가 검색할 수 있는 별칭 원문';

COMMENT ON COLUMN public.artist_aliases.normalized_alias IS 'NFKC·대소문자·공백 정리한 검색 키. 표시 원문을 대체하지 않음';

COMMENT ON COLUMN public.artist_aliases.created_at IS '새 DB에 이 행이 처음 등록된 시각. 공연/방송/원문 수집 시각과 별개';

COMMENT ON COLUMN public.artist_aliases.updated_at IS '행이 마지막 변경된 시각. 서비스가 수정 때 갱신';

CREATE TABLE public.agencies (
  id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name_native TEXT NOT NULL CHECK (name_native IS NULL OR length(btrim(name_native)) > 0),
  name_ko TEXT CHECK (name_ko IS NULL OR length(btrim(name_ko)) > 0),
  website_url TEXT CHECK (website_url IS NULL OR length(btrim(website_url)) > 0) CHECK (website_url IS NULL OR website_url ~ '^https?://[^[:space:]]+$'),
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
  archived_at TIMESTAMPTZ
);


COMMENT ON COLUMN public.agencies.id IS '이 테이블 행의 고유 번호. 새 번호는 DB가 발급하며 기존 DB 번호를 그대로 재사용하지 않음';

COMMENT ON COLUMN public.agencies.name_native IS '소속사 원어 이름';

COMMENT ON COLUMN public.agencies.name_ko IS '한국어 표기';

COMMENT ON COLUMN public.agencies.website_url IS '공식 사이트';

COMMENT ON COLUMN public.agencies.created_at IS '새 DB에 이 행이 처음 등록된 시각. 공연/방송/원문 수집 시각과 별개';

COMMENT ON COLUMN public.agencies.updated_at IS '행이 마지막 변경된 시각. 서비스가 수정 때 갱신';

COMMENT ON COLUMN public.agencies.version IS '덮어쓰기 충돌을 막는 수정 번호. 저장 시 기대값을 대조하고 증가';

COMMENT ON COLUMN public.agencies.archived_at IS '사용 중지 시각. NULL이면 활성. 물리 삭제 대신 보관하는 제안 필드';

CREATE TABLE public.artist_group_members (
  id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  group_id INTEGER NOT NULL,
  member_id INTEGER NOT NULL,
  joined_on DATE,
  left_on DATE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (group_id, member_id),
  CHECK (group_id <> member_id),
  CHECK (joined_on IS NULL OR left_on IS NULL OR left_on >= joined_on)
);


COMMENT ON COLUMN public.artist_group_members.id IS '이 테이블 행의 고유 번호. 새 번호는 DB가 발급하며 기존 DB 번호를 그대로 재사용하지 않음';

COMMENT ON COLUMN public.artist_group_members.group_id IS '그룹인 artists.id';

COMMENT ON COLUMN public.artist_group_members.member_id IS '멤버인 artists.id';

COMMENT ON COLUMN public.artist_group_members.joined_on IS '정확히 확인된 가입일';

COMMENT ON COLUMN public.artist_group_members.left_on IS '정확히 확인된 탈퇴일. NULL만으로 현재 재적을 확정하지 않음';

COMMENT ON COLUMN public.artist_group_members.created_at IS '새 DB에 이 행이 처음 등록된 시각. 공연/방송/원문 수집 시각과 별개';

COMMENT ON COLUMN public.artist_group_members.updated_at IS '행이 마지막 변경된 시각. 서비스가 수정 때 갱신';

CREATE TABLE public.external_accounts (
  id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  platform TEXT NOT NULL CHECK (platform IS NULL OR length(btrim(platform)) > 0) CHECK (platform IN ('youtube','spotify','x','website','fanclub')),
  platform_id TEXT CHECK (platform_id IS NULL OR length(btrim(platform_id)) > 0),
  handle TEXT CHECK (handle IS NULL OR length(btrim(handle)) > 0),
  url TEXT NOT NULL CHECK (url IS NULL OR length(btrim(url)) > 0) CHECK (url IS NULL OR url ~ '^https?://[^[:space:]]+$'),
  collection_enabled BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
  archived_at TIMESTAMPTZ,
  UNIQUE (platform, platform_id),
  CHECK (platform NOT IN ('website','fanclub') OR NOT collection_enabled)
);


COMMENT ON COLUMN public.external_accounts.id IS '이 테이블 행의 고유 번호. 새 번호는 DB가 발급하며 기존 DB 번호를 그대로 재사용하지 않음';

COMMENT ON COLUMN public.external_accounts.platform IS 'youtube, spotify, x, website, fanclub 등 허용 종류';

COMMENT ON COLUMN public.external_accounts.platform_id IS '플랫폼의 고정 ID. @핸들과 구분';

COMMENT ON COLUMN public.external_accounts.handle IS '변할 수 있는 계정 핸들';

COMMENT ON COLUMN public.external_accounts.url IS '외부 계정의 공식 주소';

COMMENT ON COLUMN public.external_accounts.collection_enabled IS '향후 수집 대상으로 사용할지. website/fanclub은 false로 제한; 실제 수집기 연결은 별도';

COMMENT ON COLUMN public.external_accounts.created_at IS '새 DB에 이 행이 처음 등록된 시각. 공연/방송/원문 수집 시각과 별개';

COMMENT ON COLUMN public.external_accounts.updated_at IS '행이 마지막 변경된 시각. 서비스가 수정 때 갱신';

COMMENT ON COLUMN public.external_accounts.version IS '덮어쓰기 충돌을 막는 수정 번호. 저장 시 기대값을 대조하고 증가';

COMMENT ON COLUMN public.external_accounts.archived_at IS '사용 중지 시각. NULL이면 활성. 물리 삭제 대신 보관하는 제안 필드';

CREATE TABLE public.artist_external_accounts (
  id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  artist_id INTEGER NOT NULL,
  account_id INTEGER NOT NULL,
  relationship TEXT NOT NULL CHECK (relationship IS NULL OR length(btrim(relationship)) > 0) CHECK (relationship IN ('owner','member')),
  is_primary BOOLEAN NOT NULL DEFAULT false,
  label TEXT CHECK (label IS NULL OR length(btrim(label)) > 0),
  position INTEGER NOT NULL DEFAULT 0 CHECK (position >= 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (artist_id, account_id)
);


COMMENT ON COLUMN public.artist_external_accounts.id IS '이 테이블 행의 고유 번호. 새 번호는 DB가 발급하며 기존 DB 번호를 그대로 재사용하지 않음';

COMMENT ON COLUMN public.artist_external_accounts.artist_id IS 'artists.id';

COMMENT ON COLUMN public.artist_external_accounts.account_id IS 'external_accounts.id';

COMMENT ON COLUMN public.artist_external_accounts.relationship IS 'owner(명의/주체), member(공유 계정 참여자)';

COMMENT ON COLUMN public.artist_external_accounts.is_primary IS '해당 아티스트의 해당 플랫폼 대표 계정 여부';

COMMENT ON COLUMN public.artist_external_accounts.label IS '해당 아티스트 프로필에서 보일 버튼 이름. 비우면 종류별 기본 이름';

COMMENT ON COLUMN public.artist_external_accounts.position IS '해당 아티스트의 프로필 링크 표시 순서';

COMMENT ON COLUMN public.artist_external_accounts.created_at IS '새 DB에 이 행이 처음 등록된 시각. 공연/방송/원문 수집 시각과 별개';

COMMENT ON COLUMN public.artist_external_accounts.updated_at IS '행이 마지막 변경된 시각. 서비스가 수정 때 갱신';

CREATE TABLE public.songs (
  id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  title_native TEXT NOT NULL CHECK (title_native IS NULL OR length(btrim(title_native)) > 0),
  title_ko TEXT CHECK (title_ko IS NULL OR length(btrim(title_ko)) > 0),
  title_latin TEXT CHECK (title_latin IS NULL OR length(btrim(title_latin)) > 0),
  language_code TEXT CHECK (language_code IS NULL OR length(btrim(language_code)) > 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
  archived_at TIMESTAMPTZ
);


COMMENT ON COLUMN public.songs.id IS '이 테이블 행의 고유 번호. 새 번호는 DB가 발급하며 기존 DB 번호를 그대로 재사용하지 않음';

COMMENT ON COLUMN public.songs.title_native IS '원어 곡명';

COMMENT ON COLUMN public.songs.title_ko IS '한국어 표기. 영어 원어를 복사해 채우지 않음';

COMMENT ON COLUMN public.songs.title_latin IS '영어/로마자 표기';

COMMENT ON COLUMN public.songs.language_code IS '가사의 언어 코드. 다국어는 mul 등 계약으로 처리';

COMMENT ON COLUMN public.songs.created_at IS '새 DB에 이 행이 처음 등록된 시각. 공연/방송/원문 수집 시각과 별개';

COMMENT ON COLUMN public.songs.updated_at IS '행이 마지막 변경된 시각. 서비스가 수정 때 갱신';

COMMENT ON COLUMN public.songs.version IS '덮어쓰기 충돌을 막는 수정 번호. 저장 시 기대값을 대조하고 증가';

COMMENT ON COLUMN public.songs.archived_at IS '사용 중지 시각. NULL이면 활성. 물리 삭제 대신 보관하는 제안 필드';

CREATE TABLE public.song_artists (
  id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  song_id INTEGER NOT NULL,
  artist_id INTEGER NOT NULL,
  position INTEGER NOT NULL DEFAULT 0 CHECK (position >= 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (song_id, artist_id)
);


COMMENT ON COLUMN public.song_artists.id IS '이 테이블 행의 고유 번호. 새 번호는 DB가 발급하며 기존 DB 번호를 그대로 재사용하지 않음';

COMMENT ON COLUMN public.song_artists.song_id IS 'songs.id';

COMMENT ON COLUMN public.song_artists.artist_id IS 'artists.id';

COMMENT ON COLUMN public.song_artists.position IS '원곡 명의 표시 순서';

COMMENT ON COLUMN public.song_artists.created_at IS '새 DB에 이 행이 처음 등록된 시각. 공연/방송/원문 수집 시각과 별개';

COMMENT ON COLUMN public.song_artists.updated_at IS '행이 마지막 변경된 시각. 서비스가 수정 때 갱신';

CREATE TABLE public.karaoke_numbers (
  id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  song_id INTEGER NOT NULL,
  provider TEXT NOT NULL CHECK (provider IS NULL OR length(btrim(provider)) > 0) CHECK (provider IN ('tj','ky')),
  number TEXT NOT NULL CHECK (number IS NULL OR length(btrim(number)) > 0),
  source_url TEXT CHECK (source_url IS NULL OR length(btrim(source_url)) > 0) CHECK (source_url IS NULL OR source_url ~ '^https?://[^[:space:]]+$'),
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (song_id, provider, number)
);


COMMENT ON COLUMN public.karaoke_numbers.id IS '이 테이블 행의 고유 번호. 새 번호는 DB가 발급하며 기존 DB 번호를 그대로 재사용하지 않음';

COMMENT ON COLUMN public.karaoke_numbers.song_id IS 'songs.id';

COMMENT ON COLUMN public.karaoke_numbers.provider IS 'tj 또는 ky';

COMMENT ON COLUMN public.karaoke_numbers.number IS '노래방 번호. 계산용 숫자가 아니므로 문자열로 보존';

COMMENT ON COLUMN public.karaoke_numbers.source_url IS '번호를 확인한 출처';

COMMENT ON COLUMN public.karaoke_numbers.created_at IS '새 DB에 이 행이 처음 등록된 시각. 공연/방송/원문 수집 시각과 별개';

COMMENT ON COLUMN public.karaoke_numbers.updated_at IS '행이 마지막 변경된 시각. 서비스가 수정 때 갱신';

CREATE TABLE public.videos (
  id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  platform TEXT NOT NULL CHECK (platform IS NULL OR length(btrim(platform)) > 0) CHECK (platform IN ('youtube')),
  platform_video_id TEXT NOT NULL CHECK (platform_video_id IS NULL OR length(btrim(platform_video_id)) > 0),
  source_account_id INTEGER,
  title TEXT NOT NULL CHECK (title IS NULL OR length(btrim(title)) > 0),
  published_at TIMESTAMPTZ,
  duration_seconds INTEGER CHECK (duration_seconds >= 0),
  availability TEXT NOT NULL DEFAULT 'unknown' CHECK (availability IS NULL OR length(btrim(availability)) > 0) CHECK (availability IN ('public','unlisted','private','deleted','unknown')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
  archived_at TIMESTAMPTZ,
  UNIQUE (platform, platform_video_id),
  CHECK (platform <> 'youtube' OR platform_video_id ~ '^[A-Za-z0-9_-]{11}$')
);


COMMENT ON COLUMN public.videos.id IS '이 테이블 행의 고유 번호. 새 번호는 DB가 발급하며 기존 DB 번호를 그대로 재사용하지 않음';

COMMENT ON COLUMN public.videos.platform IS '1차 허용 플랫폼 youtube. 추후 확장은 계약 변경';

COMMENT ON COLUMN public.videos.platform_video_id IS '플랫폼의 영상 고유 ID';

COMMENT ON COLUMN public.videos.source_account_id IS '업로드 계정. external_accounts.id';

COMMENT ON COLUMN public.videos.title IS '확인한 영상 제목';

COMMENT ON COLUMN public.videos.published_at IS '영상 공개/업로드 시각. 실제 방송 시각과 다를 수 있음';

COMMENT ON COLUMN public.videos.duration_seconds IS '영상 전체 길이(초). 모르면 0 대신 NULL';

COMMENT ON COLUMN public.videos.availability IS 'public, unlisted, private, deleted, unknown 제안값';

COMMENT ON COLUMN public.videos.created_at IS '새 DB에 이 행이 처음 등록된 시각. 공연/방송/원문 수집 시각과 별개';

COMMENT ON COLUMN public.videos.updated_at IS '행이 마지막 변경된 시각. 서비스가 수정 때 갱신';

COMMENT ON COLUMN public.videos.version IS '덮어쓰기 충돌을 막는 수정 번호. 저장 시 기대값을 대조하고 증가';

COMMENT ON COLUMN public.videos.archived_at IS '사용 중지 시각. NULL이면 활성. 물리 삭제 대신 보관하는 제안 필드';

CREATE TABLE public.live_archives (
  id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  video_id INTEGER NOT NULL,
  primary_artist_id INTEGER,
  broadcast_at TIMESTAMPTZ,
  setlist_state TEXT NOT NULL DEFAULT 'unprocessed' CHECK (setlist_state IS NULL OR length(btrim(setlist_state)) > 0) CHECK (setlist_state IN ('unprocessed','partial','complete','unavailable')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
  archived_at TIMESTAMPTZ,
  UNIQUE (video_id)
);


COMMENT ON COLUMN public.live_archives.id IS '이 테이블 행의 고유 번호. 새 번호는 DB가 발급하며 기존 DB 번호를 그대로 재사용하지 않음';

COMMENT ON COLUMN public.live_archives.video_id IS 'videos.id. 한 영상에 라이브 행 하나';

COMMENT ON COLUMN public.live_archives.primary_artist_id IS '화면에 대표로 보여줄 artists.id. 단독 가창자를 뜻하지 않음';

COMMENT ON COLUMN public.live_archives.broadcast_at IS '확인된 실제 방송 시각. 업로드 시각 자동 복사 금지';

COMMENT ON COLUMN public.live_archives.setlist_state IS 'unprocessed(미정리), partial(일부), complete(완료), unavailable(확보 불가)';

COMMENT ON COLUMN public.live_archives.created_at IS '새 DB에 이 행이 처음 등록된 시각. 공연/방송/원문 수집 시각과 별개';

COMMENT ON COLUMN public.live_archives.updated_at IS '행이 마지막 변경된 시각. 서비스가 수정 때 갱신';

COMMENT ON COLUMN public.live_archives.version IS '덮어쓰기 충돌을 막는 수정 번호. 저장 시 기대값을 대조하고 증가';

COMMENT ON COLUMN public.live_archives.archived_at IS '사용 중지 시각. NULL이면 활성. 물리 삭제 대신 보관하는 제안 필드';

CREATE TABLE public.archive_artists (
  id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  archive_id INTEGER NOT NULL,
  artist_id INTEGER NOT NULL,
  role TEXT NOT NULL CHECK (role IS NULL OR length(btrim(role)) > 0) CHECK (role IN ('host','guest')),
  position INTEGER NOT NULL DEFAULT 0 CHECK (position >= 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (archive_id, artist_id)
);


COMMENT ON COLUMN public.archive_artists.id IS '이 테이블 행의 고유 번호. 새 번호는 DB가 발급하며 기존 DB 번호를 그대로 재사용하지 않음';

COMMENT ON COLUMN public.archive_artists.archive_id IS 'live_archives.id';

COMMENT ON COLUMN public.archive_artists.artist_id IS 'artists.id';

COMMENT ON COLUMN public.archive_artists.role IS 'host(진행), guest(게스트). 불명확하면 관계 승인을 보류';

COMMENT ON COLUMN public.archive_artists.position IS '출연진 표시 순서';

COMMENT ON COLUMN public.archive_artists.created_at IS '새 DB에 이 행이 처음 등록된 시각. 공연/방송/원문 수집 시각과 별개';

COMMENT ON COLUMN public.archive_artists.updated_at IS '행이 마지막 변경된 시각. 서비스가 수정 때 갱신';

CREATE TABLE public.source_documents (
  id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  source_kind TEXT NOT NULL CHECK (source_kind IS NULL OR length(btrim(source_kind)) > 0) CHECK (source_kind IN ('youtube_comment','video_description','announcement','official_page','manual_note')),
  source_url TEXT CHECK (source_url IS NULL OR length(btrim(source_url)) > 0) CHECK (source_url IS NULL OR source_url ~ '^https?://[^[:space:]]+$'),
  external_id TEXT CHECK (external_id IS NULL OR length(btrim(external_id)) > 0),
  captured_at TIMESTAMPTZ,
  content_text TEXT CHECK (content_text IS NULL OR length(btrim(content_text)) > 0),
  content_hash TEXT NOT NULL CHECK (content_hash IS NULL OR length(btrim(content_hash)) > 0) CHECK (content_hash ~ '^[0-9a-f]{64}$'),
  source_metadata JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (source_metadata IS NULL OR jsonb_typeof(source_metadata) = 'object'),
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  CHECK (content_text IS NOT NULL OR source_metadata <> '{}'::jsonb)
);


COMMENT ON COLUMN public.source_documents.id IS '이 테이블 행의 고유 번호. 새 번호는 DB가 발급하며 기존 DB 번호를 그대로 재사용하지 않음';

COMMENT ON COLUMN public.source_documents.source_kind IS 'youtube_comment, video_description, announcement, official_page, manual_note 제안값';

COMMENT ON COLUMN public.source_documents.source_url IS '원문 주소. 외부 원문이 없으면 비움';

COMMENT ON COLUMN public.source_documents.external_id IS '댓글/게시글 등 외부 식별자. 수정본도 같은 ID일 수 있음';

COMMENT ON COLUMN public.source_documents.captured_at IS '실제로 원문을 확보한 시각. 모르면 현재 시각으로 꾸미지 않음';

COMMENT ON COLUMN public.source_documents.content_text IS '댓글·설명·공지 원문';

COMMENT ON COLUMN public.source_documents.content_hash IS '본문과 메타데이터를 정해진 방식으로 정규화한 SHA-256';

COMMENT ON COLUMN public.source_documents.source_metadata IS '승인에 필요한 원본 메타데이터·추출 출처. 비밀·계정 토큰 제외';

COMMENT ON COLUMN public.source_documents.created_at IS '새 DB에 이 행이 처음 등록된 시각. 공연/방송/원문 수집 시각과 별개';

CREATE TABLE public.archive_sources (
  id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  archive_id INTEGER NOT NULL,
  document_id INTEGER NOT NULL,
  role TEXT NOT NULL CHECK (role IS NULL OR length(btrim(role)) > 0) CHECK (role IN ('setlist_evidence','metadata_evidence')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (archive_id, document_id, role)
);


COMMENT ON COLUMN public.archive_sources.id IS '이 테이블 행의 고유 번호. 새 번호는 DB가 발급하며 기존 DB 번호를 그대로 재사용하지 않음';

COMMENT ON COLUMN public.archive_sources.archive_id IS 'live_archives.id';

COMMENT ON COLUMN public.archive_sources.document_id IS 'source_documents.id';

COMMENT ON COLUMN public.archive_sources.role IS 'setlist_evidence(세트리스트 근거), metadata_evidence(방송 정보 근거)';

COMMENT ON COLUMN public.archive_sources.created_at IS '새 DB에 이 행이 처음 등록된 시각. 공연/방송/원문 수집 시각과 별개';

COMMENT ON COLUMN public.archive_sources.updated_at IS '행이 마지막 변경된 시각. 서비스가 수정 때 갱신';

CREATE TABLE public.performances (
  id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  archive_id INTEGER NOT NULL,
  ordinal INTEGER NOT NULL CHECK (ordinal >= 1),
  song_id INTEGER,
  start_seconds INTEGER NOT NULL CHECK (start_seconds >= 0),
  end_seconds INTEGER,
  raw_title TEXT NOT NULL CHECK (raw_title IS NULL OR length(btrim(raw_title)) > 0),
  raw_artist TEXT CHECK (raw_artist IS NULL OR length(btrim(raw_artist)) > 0),
  raw_timestamp TEXT CHECK (raw_timestamp IS NULL OR length(btrim(raw_timestamp)) > 0),
  source_document_id INTEGER,
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
  archived_at TIMESTAMPTZ,
  UNIQUE (archive_id, ordinal) DEFERRABLE INITIALLY IMMEDIATE,
  CHECK (end_seconds IS NULL OR end_seconds > start_seconds)
);


COMMENT ON COLUMN public.performances.id IS '이 테이블 행의 고유 번호. 새 번호는 DB가 발급하며 기존 DB 번호를 그대로 재사용하지 않음';

COMMENT ON COLUMN public.performances.archive_id IS 'live_archives.id';

COMMENT ON COLUMN public.performances.ordinal IS '방송 안 세트리스트 순번. 1부터 시작';

COMMENT ON COLUMN public.performances.song_id IS 'songs.id. 검수된 미매칭 상태는 허용';

COMMENT ON COLUMN public.performances.start_seconds IS '영상 시작부터 노래 시작까지 초. 근거 없는 0 입력 금지';

COMMENT ON COLUMN public.performances.end_seconds IS '노래 종료 시점(초)';

COMMENT ON COLUMN public.performances.raw_title IS '입력 원문에서의 곡명. 정규 곡명으로 덮어쓰지 않음';

COMMENT ON COLUMN public.performances.raw_artist IS '원문의 원곡 아티스트 표기';

COMMENT ON COLUMN public.performances.raw_timestamp IS '원문 시각 문자열. 수동 등록이면 생략 가능';

COMMENT ON COLUMN public.performances.source_document_id IS '이 행의 근거. source_documents.id';

COMMENT ON COLUMN public.performances.created_at IS '새 DB에 이 행이 처음 등록된 시각. 공연/방송/원문 수집 시각과 별개';

COMMENT ON COLUMN public.performances.updated_at IS '행이 마지막 변경된 시각. 서비스가 수정 때 갱신';

COMMENT ON COLUMN public.performances.version IS '덮어쓰기 충돌을 막는 수정 번호. 저장 시 기대값을 대조하고 증가';

COMMENT ON COLUMN public.performances.archived_at IS '사용 중지 시각. NULL이면 활성. 물리 삭제 대신 보관하는 제안 필드';

CREATE TABLE public.performance_artists (
  id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  performance_id INTEGER NOT NULL,
  artist_id INTEGER NOT NULL,
  role TEXT NOT NULL CHECK (role IS NULL OR length(btrim(role)) > 0) CHECK (role IN ('lead','guest')),
  position INTEGER NOT NULL DEFAULT 0 CHECK (position >= 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (performance_id, artist_id)
);


COMMENT ON COLUMN public.performance_artists.id IS '이 테이블 행의 고유 번호. 새 번호는 DB가 발급하며 기존 DB 번호를 그대로 재사용하지 않음';

COMMENT ON COLUMN public.performance_artists.performance_id IS 'performances.id';

COMMENT ON COLUMN public.performance_artists.artist_id IS 'artists.id';

COMMENT ON COLUMN public.performance_artists.role IS 'lead(주 가창), guest(함께 부른 게스트)';

COMMENT ON COLUMN public.performance_artists.position IS '가창자 표시 순서';

COMMENT ON COLUMN public.performance_artists.created_at IS '새 DB에 이 행이 처음 등록된 시각. 공연/방송/원문 수집 시각과 별개';

COMMENT ON COLUMN public.performance_artists.updated_at IS '행이 마지막 변경된 시각. 서비스가 수정 때 갱신';

CREATE TABLE public.concerts (
  id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  title TEXT NOT NULL CHECK (title IS NULL OR length(btrim(title)) > 0),
  event_format TEXT NOT NULL CHECK (event_format IS NULL OR length(btrim(event_format)) > 0) CHECK (event_format IN ('onsite','online','hybrid')),
  event_date DATE,
  starts_at TIMESTAMPTZ,
  ends_at TIMESTAMPTZ,
  timezone_name TEXT CHECK (timezone_name IS NULL OR length(btrim(timezone_name)) > 0),
  time_precision TEXT NOT NULL DEFAULT 'unknown' CHECK (time_precision IS NULL OR length(btrim(time_precision)) > 0) CHECK (time_precision IN ('unknown','date','datetime')),
  city TEXT CHECK (city IS NULL OR length(btrim(city)) > 0),
  venue TEXT CHECK (venue IS NULL OR length(btrim(venue)) > 0),
  status TEXT NOT NULL CHECK (status IS NULL OR length(btrim(status)) > 0) CHECK (status IN ('scheduled','postponed','cancelled','completed')),
  source_document_id INTEGER,
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
  archived_at TIMESTAMPTZ,
  CHECK (catalog_concert_time_valid(time_precision,event_date,starts_at,ends_at,timezone_name))
);


COMMENT ON COLUMN public.concerts.id IS '이 테이블 행의 고유 번호. 새 번호는 DB가 발급하며 기존 DB 번호를 그대로 재사용하지 않음';

COMMENT ON COLUMN public.concerts.title IS '공연 공식 타이틀';

COMMENT ON COLUMN public.concerts.event_format IS 'onsite(현장), online(온라인), hybrid(병행)';

COMMENT ON COLUMN public.concerts.event_date IS '공연 기준 시간대의 현지 날짜. 날짜 미정이면 비움';

COMMENT ON COLUMN public.concerts.starts_at IS '확인된 실제 시작 시각. 시간 미정이면 00:00 대신 NULL';

COMMENT ON COLUMN public.concerts.ends_at IS '확인된 종료 시각';

COMMENT ON COLUMN public.concerts.timezone_name IS 'IANA 시간대 이름. 정확한 시작 시각이 있으면 필수';

COMMENT ON COLUMN public.concerts.time_precision IS 'unknown(날짜 미정), date(날짜만), datetime(시각까지)';

COMMENT ON COLUMN public.concerts.city IS '개최 도시. 온라인이거나 미확인이면 비움';

COMMENT ON COLUMN public.concerts.venue IS '공연장 이름. 미확인 장소를 만들어 넣지 않음';

COMMENT ON COLUMN public.concerts.status IS 'scheduled, postponed, cancelled, completed 중 검수한 상태';

COMMENT ON COLUMN public.concerts.source_document_id IS '기준 공지의 source_documents.id';

COMMENT ON COLUMN public.concerts.created_at IS '새 DB에 이 행이 처음 등록된 시각. 공연/방송/원문 수집 시각과 별개';

COMMENT ON COLUMN public.concerts.updated_at IS '행이 마지막 변경된 시각. 서비스가 수정 때 갱신';

COMMENT ON COLUMN public.concerts.version IS '덮어쓰기 충돌을 막는 수정 번호. 저장 시 기대값을 대조하고 증가';

COMMENT ON COLUMN public.concerts.archived_at IS '사용 중지 시각. NULL이면 활성. 물리 삭제 대신 보관하는 제안 필드';

CREATE TABLE public.concert_artists (
  id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  concert_id INTEGER NOT NULL,
  artist_id INTEGER NOT NULL,
  position INTEGER NOT NULL DEFAULT 0 CHECK (position >= 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (concert_id, artist_id)
);


COMMENT ON COLUMN public.concert_artists.id IS '이 테이블 행의 고유 번호. 새 번호는 DB가 발급하며 기존 DB 번호를 그대로 재사용하지 않음';

COMMENT ON COLUMN public.concert_artists.concert_id IS 'concerts.id';

COMMENT ON COLUMN public.concert_artists.artist_id IS 'artists.id';

COMMENT ON COLUMN public.concert_artists.position IS '출연진 표시 순서. 첫 출연자를 대표 이름·색상으로 사용';

COMMENT ON COLUMN public.concert_artists.created_at IS '새 DB에 이 행이 처음 등록된 시각. 공연/방송/원문 수집 시각과 별개';

COMMENT ON COLUMN public.concert_artists.updated_at IS '행이 마지막 변경된 시각. 서비스가 수정 때 갱신';

CREATE TABLE public.concert_ticket_windows (
  id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  concert_id INTEGER NOT NULL,
  label TEXT CHECK (label IS NULL OR length(btrim(label)) > 0),
  opens_at TIMESTAMPTZ,
  closes_at TIMESTAMPTZ,
  url TEXT CHECK (url IS NULL OR length(btrim(url)) > 0) CHECK (url IS NULL OR url ~ '^https?://[^[:space:]]+$'),
  price_text TEXT CHECK (price_text IS NULL OR length(btrim(price_text)) > 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  CHECK (opens_at IS NULL OR closes_at IS NULL OR closes_at >= opens_at),
  CHECK (label IS NOT NULL OR opens_at IS NOT NULL OR closes_at IS NOT NULL OR url IS NOT NULL OR price_text IS NOT NULL)
);


COMMENT ON COLUMN public.concert_ticket_windows.id IS '이 테이블 행의 고유 번호. 새 번호는 DB가 발급하며 기존 DB 번호를 그대로 재사용하지 않음';

COMMENT ON COLUMN public.concert_ticket_windows.concert_id IS 'concerts.id';

COMMENT ON COLUMN public.concert_ticket_windows.label IS '판매 구간 이름';

COMMENT ON COLUMN public.concert_ticket_windows.opens_at IS '정확한 예매 시작 시각';

COMMENT ON COLUMN public.concert_ticket_windows.closes_at IS '정확한 예매 종료 시각';

COMMENT ON COLUMN public.concert_ticket_windows.url IS '공식 예매/안내 주소';

COMMENT ON COLUMN public.concert_ticket_windows.price_text IS '통화·좌석별 조건을 포함한 안내 문구';

COMMENT ON COLUMN public.concert_ticket_windows.created_at IS '새 DB에 이 행이 처음 등록된 시각. 공연/방송/원문 수집 시각과 별개';

COMMENT ON COLUMN public.concert_ticket_windows.updated_at IS '행이 마지막 변경된 시각. 서비스가 수정 때 갱신';

CREATE TABLE public.albums (
  id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  title_native TEXT NOT NULL CHECK (title_native IS NULL OR length(btrim(title_native)) > 0),
  title_ko TEXT CHECK (title_ko IS NULL OR length(btrim(title_ko)) > 0),
  album_type TEXT NOT NULL CHECK (album_type IS NULL OR length(btrim(album_type)) > 0) CHECK (album_type IN ('single','ep','album','compilation','other')),
  release_year SMALLINT,
  release_month SMALLINT,
  release_day SMALLINT,
  cover_image_url TEXT CHECK (cover_image_url IS NULL OR length(btrim(cover_image_url)) > 0) CHECK (cover_image_url IS NULL OR cover_image_url ~ '^https?://[^[:space:]]+$'),
  spotify_album_id TEXT CHECK (spotify_album_id IS NULL OR length(btrim(spotify_album_id)) > 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
  archived_at TIMESTAMPTZ,
  UNIQUE (spotify_album_id),
  CHECK (release_year IS NULL OR release_year BETWEEN 1 AND 9999),
  CHECK (release_month IS NULL OR (release_year IS NOT NULL AND release_month BETWEEN 1 AND 12)),
  CHECK (release_day IS NULL OR (release_year IS NOT NULL AND release_month IS NOT NULL AND catalog_valid_date(release_year,release_month,release_day)))
);


COMMENT ON COLUMN public.albums.id IS '이 테이블 행의 고유 번호. 새 번호는 DB가 발급하며 기존 DB 번호를 그대로 재사용하지 않음';

COMMENT ON COLUMN public.albums.title_native IS '원어 앨범명';

COMMENT ON COLUMN public.albums.title_ko IS '한국어 앨범명';

COMMENT ON COLUMN public.albums.album_type IS 'single, ep, album, compilation, other 제안값. 외부 플랫폼 값을 검수하여 분류';

COMMENT ON COLUMN public.albums.release_year IS '확인한 발매 연도';

COMMENT ON COLUMN public.albums.release_month IS '확인한 발매 월. 월이 있으면 연도도 필수';

COMMENT ON COLUMN public.albums.release_day IS '확인한 발매 일. 일이 있으면 연/월도 필수';

COMMENT ON COLUMN public.albums.cover_image_url IS '앨범 자켓 이미지 주소';

COMMENT ON COLUMN public.albums.spotify_album_id IS 'Spotify 앨범 식별자';

COMMENT ON COLUMN public.albums.created_at IS '새 DB에 이 행이 처음 등록된 시각. 공연/방송/원문 수집 시각과 별개';

COMMENT ON COLUMN public.albums.updated_at IS '행이 마지막 변경된 시각. 서비스가 수정 때 갱신';

COMMENT ON COLUMN public.albums.version IS '덮어쓰기 충돌을 막는 수정 번호. 저장 시 기대값을 대조하고 증가';

COMMENT ON COLUMN public.albums.archived_at IS '사용 중지 시각. NULL이면 활성. 물리 삭제 대신 보관하는 제안 필드';

CREATE TABLE public.album_artists (
  id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  album_id INTEGER NOT NULL,
  artist_id INTEGER NOT NULL,
  position INTEGER NOT NULL DEFAULT 0 CHECK (position >= 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (album_id, artist_id)
);


COMMENT ON COLUMN public.album_artists.id IS '이 테이블 행의 고유 번호. 새 번호는 DB가 발급하며 기존 DB 번호를 그대로 재사용하지 않음';

COMMENT ON COLUMN public.album_artists.album_id IS 'albums.id';

COMMENT ON COLUMN public.album_artists.artist_id IS 'artists.id';

COMMENT ON COLUMN public.album_artists.position IS '공식 발매 명의 표시 순서';

COMMENT ON COLUMN public.album_artists.created_at IS '새 DB에 이 행이 처음 등록된 시각. 공연/방송/원문 수집 시각과 별개';

COMMENT ON COLUMN public.album_artists.updated_at IS '행이 마지막 변경된 시각. 서비스가 수정 때 갱신';

CREATE TABLE public.recordings (
  id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  song_id INTEGER,
  title_native TEXT NOT NULL CHECK (title_native IS NULL OR length(btrim(title_native)) > 0),
  title_ko TEXT CHECK (title_ko IS NULL OR length(btrim(title_ko)) > 0),
  version_label TEXT CHECK (version_label IS NULL OR length(btrim(version_label)) > 0),
  duration_ms INTEGER CHECK (duration_ms >= 0),
  official_video_id INTEGER,
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
  archived_at TIMESTAMPTZ
);


COMMENT ON COLUMN public.recordings.id IS '이 테이블 행의 고유 번호. 새 번호는 DB가 발급하며 기존 DB 번호를 그대로 재사용하지 않음';

COMMENT ON COLUMN public.recordings.song_id IS '공통 작품 songs.id. 미확정이면 비움';

COMMENT ON COLUMN public.recordings.title_native IS '발매 음원 원어 제목. 작품 제목과 버전 표기가 다를 수 있음';

COMMENT ON COLUMN public.recordings.title_ko IS '검수한 한국어 음원 제목';

COMMENT ON COLUMN public.recordings.version_label IS '버전 설명. 없다고 원본 버전으로 단정하지 않음';

COMMENT ON COLUMN public.recordings.duration_ms IS '재생 길이(밀리초)';

COMMENT ON COLUMN public.recordings.official_video_id IS '대표 공식 MV의 videos.id';

COMMENT ON COLUMN public.recordings.created_at IS '새 DB에 이 행이 처음 등록된 시각. 공연/방송/원문 수집 시각과 별개';

COMMENT ON COLUMN public.recordings.updated_at IS '행이 마지막 변경된 시각. 서비스가 수정 때 갱신';

COMMENT ON COLUMN public.recordings.version IS '덮어쓰기 충돌을 막는 수정 번호. 저장 시 기대값을 대조하고 증가';

COMMENT ON COLUMN public.recordings.archived_at IS '사용 중지 시각. NULL이면 활성. 물리 삭제 대신 보관하는 제안 필드';

CREATE TABLE public.recording_artists (
  id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  recording_id INTEGER NOT NULL,
  artist_id INTEGER NOT NULL,
  role TEXT NOT NULL CHECK (role IS NULL OR length(btrim(role)) > 0) CHECK (role IN ('primary','featured')),
  position INTEGER NOT NULL DEFAULT 0 CHECK (position >= 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (recording_id, artist_id)
);


COMMENT ON COLUMN public.recording_artists.id IS '이 테이블 행의 고유 번호. 새 번호는 DB가 발급하며 기존 DB 번호를 그대로 재사용하지 않음';

COMMENT ON COLUMN public.recording_artists.recording_id IS 'recordings.id';

COMMENT ON COLUMN public.recording_artists.artist_id IS 'artists.id';

COMMENT ON COLUMN public.recording_artists.role IS 'primary(주 가창), featured(피처링)';

COMMENT ON COLUMN public.recording_artists.position IS '가창 명의 표시 순서';

COMMENT ON COLUMN public.recording_artists.created_at IS '새 DB에 이 행이 처음 등록된 시각. 공연/방송/원문 수집 시각과 별개';

COMMENT ON COLUMN public.recording_artists.updated_at IS '행이 마지막 변경된 시각. 서비스가 수정 때 갱신';

CREATE TABLE public.recording_external_ids (
  id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  recording_id INTEGER NOT NULL,
  platform TEXT NOT NULL CHECK (platform IS NULL OR length(btrim(platform)) > 0) CHECK (platform IN ('spotify')),
  external_id TEXT NOT NULL CHECK (external_id IS NULL OR length(btrim(external_id)) > 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (platform, external_id)
);


COMMENT ON COLUMN public.recording_external_ids.id IS '이 테이블 행의 고유 번호. 새 번호는 DB가 발급하며 기존 DB 번호를 그대로 재사용하지 않음';

COMMENT ON COLUMN public.recording_external_ids.recording_id IS 'recordings.id';

COMMENT ON COLUMN public.recording_external_ids.platform IS '1차 spotify. 추가 플랫폼은 허용 목록 확장';

COMMENT ON COLUMN public.recording_external_ids.external_id IS '플랫폼의 트랙 고유 ID';

COMMENT ON COLUMN public.recording_external_ids.created_at IS '새 DB에 이 행이 처음 등록된 시각. 공연/방송/원문 수집 시각과 별개';

COMMENT ON COLUMN public.recording_external_ids.updated_at IS '행이 마지막 변경된 시각. 서비스가 수정 때 갱신';

CREATE TABLE public.album_tracks (
  id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  album_id INTEGER NOT NULL,
  recording_id INTEGER NOT NULL,
  disc_number INTEGER NOT NULL DEFAULT 1 CHECK (disc_number >= 1),
  track_number INTEGER NOT NULL CHECK (track_number >= 1),
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (album_id, disc_number, track_number) DEFERRABLE INITIALLY IMMEDIATE
);


COMMENT ON COLUMN public.album_tracks.id IS '이 테이블 행의 고유 번호. 새 번호는 DB가 발급하며 기존 DB 번호를 그대로 재사용하지 않음';

COMMENT ON COLUMN public.album_tracks.album_id IS 'albums.id';

COMMENT ON COLUMN public.album_tracks.recording_id IS 'recordings.id';

COMMENT ON COLUMN public.album_tracks.disc_number IS '디스크 번호';

COMMENT ON COLUMN public.album_tracks.track_number IS '디스크 안의 트랙 번호';

COMMENT ON COLUMN public.album_tracks.created_at IS '새 DB에 이 행이 처음 등록된 시각. 공연/방송/원문 수집 시각과 별개';

COMMENT ON COLUMN public.album_tracks.updated_at IS '행이 마지막 변경된 시각. 서비스가 수정 때 갱신';

CREATE TABLE public.recording_lyrics (
  id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  recording_id INTEGER NOT NULL,
  original_lyrics TEXT NOT NULL CHECK (original_lyrics IS NULL OR length(btrim(original_lyrics)) > 0),
  translation_ko TEXT CHECK (translation_ko IS NULL OR length(btrim(translation_ko)) > 0),
  pronunciation_ko TEXT CHECK (pronunciation_ko IS NULL OR length(btrim(pronunciation_ko)) > 0),
  source_document_id INTEGER,
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
  archived_at TIMESTAMPTZ,
  UNIQUE (recording_id)
);


COMMENT ON COLUMN public.recording_lyrics.id IS '이 테이블 행의 고유 번호. 새 번호는 DB가 발급하며 기존 DB 번호를 그대로 재사용하지 않음';

COMMENT ON COLUMN public.recording_lyrics.recording_id IS 'recordings.id. 녹음당 가사 묶음 최대 하나';

COMMENT ON COLUMN public.recording_lyrics.original_lyrics IS '검수한 원문 가사. 줄바꿈 보존';

COMMENT ON COLUMN public.recording_lyrics.translation_ko IS '한국어 번역';

COMMENT ON COLUMN public.recording_lyrics.pronunciation_ko IS '한국어 독음';

COMMENT ON COLUMN public.recording_lyrics.source_document_id IS '확인 근거 source_documents.id';

COMMENT ON COLUMN public.recording_lyrics.created_at IS '새 DB에 이 행이 처음 등록된 시각. 공연/방송/원문 수집 시각과 별개';

COMMENT ON COLUMN public.recording_lyrics.updated_at IS '행이 마지막 변경된 시각. 서비스가 수정 때 갱신';

COMMENT ON COLUMN public.recording_lyrics.version IS '덮어쓰기 충돌을 막는 수정 번호. 저장 시 기대값을 대조하고 증가';

COMMENT ON COLUMN public.recording_lyrics.archived_at IS '사용 중지 시각. NULL이면 활성. 물리 삭제 대신 보관하는 제안 필드';

CREATE TABLE public.covers (
  id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  video_id INTEGER NOT NULL,
  song_id INTEGER,
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
  archived_at TIMESTAMPTZ,
  UNIQUE (video_id)
);


COMMENT ON COLUMN public.covers.id IS '이 테이블 행의 고유 번호. 새 번호는 DB가 발급하며 기존 DB 번호를 그대로 재사용하지 않음';

COMMENT ON COLUMN public.covers.video_id IS 'videos.id. 영상당 커버 분류 한 건';

COMMENT ON COLUMN public.covers.song_id IS '커버한 작품 songs.id';

COMMENT ON COLUMN public.covers.created_at IS '새 DB에 이 행이 처음 등록된 시각. 공연/방송/원문 수집 시각과 별개';

COMMENT ON COLUMN public.covers.updated_at IS '행이 마지막 변경된 시각. 서비스가 수정 때 갱신';

COMMENT ON COLUMN public.covers.version IS '덮어쓰기 충돌을 막는 수정 번호. 저장 시 기대값을 대조하고 증가';

COMMENT ON COLUMN public.covers.archived_at IS '사용 중지 시각. NULL이면 활성. 물리 삭제 대신 보관하는 제안 필드';

CREATE TABLE public.cover_artists (
  id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  cover_id INTEGER NOT NULL,
  artist_id INTEGER NOT NULL,
  role TEXT NOT NULL CHECK (role IS NULL OR length(btrim(role)) > 0) CHECK (role IN ('vocal','featured')),
  position INTEGER NOT NULL DEFAULT 0 CHECK (position >= 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (cover_id, artist_id)
);


COMMENT ON COLUMN public.cover_artists.id IS '이 테이블 행의 고유 번호. 새 번호는 DB가 발급하며 기존 DB 번호를 그대로 재사용하지 않음';

COMMENT ON COLUMN public.cover_artists.cover_id IS 'covers.id';

COMMENT ON COLUMN public.cover_artists.artist_id IS 'artists.id';

COMMENT ON COLUMN public.cover_artists.role IS 'vocal(가창 명의), featured(피처링)';

COMMENT ON COLUMN public.cover_artists.position IS '참여자 표시 순서';

COMMENT ON COLUMN public.cover_artists.created_at IS '새 DB에 이 행이 처음 등록된 시각. 공연/방송/원문 수집 시각과 별개';

COMMENT ON COLUMN public.cover_artists.updated_at IS '행이 마지막 변경된 시각. 서비스가 수정 때 갱신';

CREATE TABLE public.catalog_instance (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  singleton_key SMALLINT NOT NULL DEFAULT 1,
  schema_version TEXT NOT NULL CHECK (schema_version IS NULL OR length(btrim(schema_version)) > 0),
  initial_import_id INTEGER,
  initialized_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (singleton_key),
  CHECK (singleton_key = 1),
  CHECK ((initial_import_id IS NULL) = (initialized_at IS NULL))
);


COMMENT ON COLUMN public.catalog_instance.id IS '이 카탈로그의 고정 UUID. 서버 재시작마다 바꾸지 않음';

COMMENT ON COLUMN public.catalog_instance.singleton_key IS '한 DB에 한 행만 두기 위한 값. CHECK = 1';

COMMENT ON COLUMN public.catalog_instance.schema_version IS '앱이 기대하는 스키마 계약 버전. 실제 migration revision과 시작 시 대조';

COMMENT ON COLUMN public.catalog_instance.initial_import_id IS '최초 반영이 완료되면 catalog_imports.id. 초기 반영 전에는 NULL';

COMMENT ON COLUMN public.catalog_instance.initialized_at IS '최초 데이터 반영 완료 시각. 초기 반영 영수증과 같은 트랜잭션으로 기록';

COMMENT ON COLUMN public.catalog_instance.created_at IS '빈 스키마를 준비하며 카탈로그 식별 행을 만든 시각';

COMMENT ON COLUMN public.catalog_instance.updated_at IS '버전/초기화 상태를 마지막 변경한 시각';

CREATE TABLE public.catalog_imports (
  id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  operation_id UUID NOT NULL,
  catalog_instance_id UUID NOT NULL,
  manifest_hash TEXT NOT NULL CHECK (manifest_hash IS NULL OR length(btrim(manifest_hash)) > 0) CHECK (manifest_hash ~ '^[0-9a-f]{64}$'),
  source_kind TEXT NOT NULL CHECK (source_kind IS NULL OR length(btrim(source_kind)) > 0) CHECK (source_kind IN ('initial_import','batch_import','manual','merge','correction')),
  committed_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  result_mapping JSONB NOT NULL DEFAULT '[]'::jsonb CHECK (result_mapping IS NULL OR jsonb_typeof(result_mapping) = 'array'),
  result_summary JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (result_summary IS NULL OR jsonb_typeof(result_summary) = 'object'),
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (operation_id)
);


COMMENT ON COLUMN public.catalog_imports.id IS '이 테이블 행의 고유 번호. 새 번호는 DB가 발급하며 기존 DB 번호를 그대로 재사용하지 않음';

COMMENT ON COLUMN public.catalog_imports.operation_id IS '한 논리 저장 작업의 ID. 재시도에도 같은 값';

COMMENT ON COLUMN public.catalog_imports.catalog_instance_id IS '대상 catalog_instance.id';

COMMENT ON COLUMN public.catalog_imports.manifest_hash IS '승인된 반영 내용의 SHA-256. 수동 저장도 같은 규칙';

COMMENT ON COLUMN public.catalog_imports.source_kind IS 'initial_import, batch_import, manual, merge, correction 제안값';

COMMENT ON COLUMN public.catalog_imports.committed_at IS '반영 트랜잭션 안에서 기록하는 영수증 시각. 물리 COMMIT 완료 시각과 완전히 같다는 뜻은 아님';

COMMENT ON COLUMN public.catalog_imports.result_mapping IS 'client_ref/유형별 새 ID와 결과 version 대응 목록';

COMMENT ON COLUMN public.catalog_imports.result_summary IS '생성·수정·제외 등의 수량 요약';

COMMENT ON COLUMN public.catalog_imports.created_at IS '새 DB에 이 행이 처음 등록된 시각. 공연/방송/원문 수집 시각과 별개';

CREATE TABLE public.catalog_changes (
  id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  import_id INTEGER NOT NULL,
  entity_type TEXT NOT NULL CHECK (entity_type IS NULL OR length(btrim(entity_type)) > 0),
  entity_id INTEGER NOT NULL,
  action TEXT NOT NULL CHECK (action IS NULL OR length(btrim(action)) > 0) CHECK (action IN ('create','update','archive','restore','merge','delete')),
  before_data JSONB CHECK (before_data IS NULL OR jsonb_typeof(before_data) = 'object'),
  after_data JSONB CHECK (after_data IS NULL OR jsonb_typeof(after_data) = 'object'),
  provenance JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (provenance IS NULL OR jsonb_typeof(provenance) = 'object'),
  applied_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  CHECK ((action='create' AND before_data IS NULL AND after_data IS NOT NULL) OR (action='delete' AND before_data IS NOT NULL AND after_data IS NULL) OR (action IN ('update','archive','restore','merge') AND before_data IS NOT NULL AND after_data IS NOT NULL))
);


COMMENT ON COLUMN public.catalog_changes.id IS '이 테이블 행의 고유 번호. 새 번호는 DB가 발급하며 기존 DB 번호를 그대로 재사용하지 않음';

COMMENT ON COLUMN public.catalog_changes.import_id IS 'catalog_imports.id. 수동 저장도 영수증에 연결';

COMMENT ON COLUMN public.catalog_changes.entity_type IS '변경한 테이블/리소스 유형';

COMMENT ON COLUMN public.catalog_changes.entity_id IS '변경 대상 ID. 이력 대상이므로 일반 다형 FK는 아님';

COMMENT ON COLUMN public.catalog_changes.action IS 'create, update, archive, restore, merge, delete 제안값';

COMMENT ON COLUMN public.catalog_changes.before_data IS '변경 전 값. 신규 생성이면 NULL';

COMMENT ON COLUMN public.catalog_changes.after_data IS '변경 후 값. 물리 삭제라면 NULL';

COMMENT ON COLUMN public.catalog_changes.provenance IS '원본/근거 문서 ID·승인 내용 해시 등 검수 근거. 비밀·로컬 검토 메모 제외';

COMMENT ON COLUMN public.catalog_changes.applied_at IS '트랜잭션 안에서 변경을 적용한 시각';

COMMENT ON COLUMN public.catalog_changes.created_at IS '새 DB에 이 행이 처음 등록된 시각. 공연/방송/원문 수집 시각과 별개';

ALTER TABLE public.artists ADD CONSTRAINT artists_agency_id_fk FOREIGN KEY (agency_id) REFERENCES public.agencies(id) ON DELETE RESTRICT;

ALTER TABLE public.artist_aliases ADD CONSTRAINT artist_aliases_artist_id_fk FOREIGN KEY (artist_id) REFERENCES public.artists(id) ON DELETE CASCADE;

ALTER TABLE public.artist_group_members ADD CONSTRAINT artist_group_members_group_id_fk FOREIGN KEY (group_id) REFERENCES public.artists(id) ON DELETE CASCADE;

ALTER TABLE public.artist_group_members ADD CONSTRAINT artist_group_members_member_id_fk FOREIGN KEY (member_id) REFERENCES public.artists(id) ON DELETE RESTRICT;

ALTER TABLE public.artist_external_accounts ADD CONSTRAINT artist_external_accounts_artist_id_fk FOREIGN KEY (artist_id) REFERENCES public.artists(id) ON DELETE CASCADE;

ALTER TABLE public.artist_external_accounts ADD CONSTRAINT artist_external_accounts_account_id_fk FOREIGN KEY (account_id) REFERENCES public.external_accounts(id) ON DELETE RESTRICT;

ALTER TABLE public.song_artists ADD CONSTRAINT song_artists_song_id_fk FOREIGN KEY (song_id) REFERENCES public.songs(id) ON DELETE CASCADE;

ALTER TABLE public.song_artists ADD CONSTRAINT song_artists_artist_id_fk FOREIGN KEY (artist_id) REFERENCES public.artists(id) ON DELETE RESTRICT;

ALTER TABLE public.karaoke_numbers ADD CONSTRAINT karaoke_numbers_song_id_fk FOREIGN KEY (song_id) REFERENCES public.songs(id) ON DELETE CASCADE;

ALTER TABLE public.videos ADD CONSTRAINT videos_source_account_id_fk FOREIGN KEY (source_account_id) REFERENCES public.external_accounts(id) ON DELETE RESTRICT;

ALTER TABLE public.live_archives ADD CONSTRAINT live_archives_video_id_fk FOREIGN KEY (video_id) REFERENCES public.videos(id) ON DELETE RESTRICT;

ALTER TABLE public.live_archives ADD CONSTRAINT live_archives_primary_artist_id_fk FOREIGN KEY (primary_artist_id) REFERENCES public.artists(id) ON DELETE RESTRICT;

ALTER TABLE public.archive_artists ADD CONSTRAINT archive_artists_archive_id_fk FOREIGN KEY (archive_id) REFERENCES public.live_archives(id) ON DELETE CASCADE;

ALTER TABLE public.archive_artists ADD CONSTRAINT archive_artists_artist_id_fk FOREIGN KEY (artist_id) REFERENCES public.artists(id) ON DELETE RESTRICT;

ALTER TABLE public.archive_sources ADD CONSTRAINT archive_sources_archive_id_fk FOREIGN KEY (archive_id) REFERENCES public.live_archives(id) ON DELETE CASCADE;

ALTER TABLE public.archive_sources ADD CONSTRAINT archive_sources_document_id_fk FOREIGN KEY (document_id) REFERENCES public.source_documents(id) ON DELETE RESTRICT;

ALTER TABLE public.performances ADD CONSTRAINT performances_archive_id_fk FOREIGN KEY (archive_id) REFERENCES public.live_archives(id) ON DELETE RESTRICT;

ALTER TABLE public.performances ADD CONSTRAINT performances_song_id_fk FOREIGN KEY (song_id) REFERENCES public.songs(id) ON DELETE RESTRICT;

ALTER TABLE public.performances ADD CONSTRAINT performances_source_document_id_fk FOREIGN KEY (source_document_id) REFERENCES public.source_documents(id) ON DELETE RESTRICT;

ALTER TABLE public.performance_artists ADD CONSTRAINT performance_artists_performance_id_fk FOREIGN KEY (performance_id) REFERENCES public.performances(id) ON DELETE CASCADE;

ALTER TABLE public.performance_artists ADD CONSTRAINT performance_artists_artist_id_fk FOREIGN KEY (artist_id) REFERENCES public.artists(id) ON DELETE RESTRICT;

ALTER TABLE public.concerts ADD CONSTRAINT concerts_source_document_id_fk FOREIGN KEY (source_document_id) REFERENCES public.source_documents(id) ON DELETE RESTRICT;

ALTER TABLE public.concert_artists ADD CONSTRAINT concert_artists_concert_id_fk FOREIGN KEY (concert_id) REFERENCES public.concerts(id) ON DELETE CASCADE;

ALTER TABLE public.concert_artists ADD CONSTRAINT concert_artists_artist_id_fk FOREIGN KEY (artist_id) REFERENCES public.artists(id) ON DELETE RESTRICT;

ALTER TABLE public.concert_ticket_windows ADD CONSTRAINT concert_ticket_windows_concert_id_fk FOREIGN KEY (concert_id) REFERENCES public.concerts(id) ON DELETE CASCADE;

ALTER TABLE public.album_artists ADD CONSTRAINT album_artists_album_id_fk FOREIGN KEY (album_id) REFERENCES public.albums(id) ON DELETE CASCADE;

ALTER TABLE public.album_artists ADD CONSTRAINT album_artists_artist_id_fk FOREIGN KEY (artist_id) REFERENCES public.artists(id) ON DELETE RESTRICT;

ALTER TABLE public.recordings ADD CONSTRAINT recordings_song_id_fk FOREIGN KEY (song_id) REFERENCES public.songs(id) ON DELETE RESTRICT;

ALTER TABLE public.recordings ADD CONSTRAINT recordings_official_video_id_fk FOREIGN KEY (official_video_id) REFERENCES public.videos(id) ON DELETE RESTRICT;

ALTER TABLE public.recording_artists ADD CONSTRAINT recording_artists_recording_id_fk FOREIGN KEY (recording_id) REFERENCES public.recordings(id) ON DELETE CASCADE;

ALTER TABLE public.recording_artists ADD CONSTRAINT recording_artists_artist_id_fk FOREIGN KEY (artist_id) REFERENCES public.artists(id) ON DELETE RESTRICT;

ALTER TABLE public.recording_external_ids ADD CONSTRAINT recording_external_ids_recording_id_fk FOREIGN KEY (recording_id) REFERENCES public.recordings(id) ON DELETE CASCADE;

ALTER TABLE public.album_tracks ADD CONSTRAINT album_tracks_album_id_fk FOREIGN KEY (album_id) REFERENCES public.albums(id) ON DELETE CASCADE;

ALTER TABLE public.album_tracks ADD CONSTRAINT album_tracks_recording_id_fk FOREIGN KEY (recording_id) REFERENCES public.recordings(id) ON DELETE RESTRICT;

ALTER TABLE public.recording_lyrics ADD CONSTRAINT recording_lyrics_recording_id_fk FOREIGN KEY (recording_id) REFERENCES public.recordings(id) ON DELETE RESTRICT;

ALTER TABLE public.recording_lyrics ADD CONSTRAINT recording_lyrics_source_document_id_fk FOREIGN KEY (source_document_id) REFERENCES public.source_documents(id) ON DELETE RESTRICT;

ALTER TABLE public.covers ADD CONSTRAINT covers_video_id_fk FOREIGN KEY (video_id) REFERENCES public.videos(id) ON DELETE RESTRICT;

ALTER TABLE public.covers ADD CONSTRAINT covers_song_id_fk FOREIGN KEY (song_id) REFERENCES public.songs(id) ON DELETE RESTRICT;

ALTER TABLE public.cover_artists ADD CONSTRAINT cover_artists_cover_id_fk FOREIGN KEY (cover_id) REFERENCES public.covers(id) ON DELETE CASCADE;

ALTER TABLE public.cover_artists ADD CONSTRAINT cover_artists_artist_id_fk FOREIGN KEY (artist_id) REFERENCES public.artists(id) ON DELETE RESTRICT;

ALTER TABLE public.catalog_instance ADD CONSTRAINT catalog_instance_initial_import_id_fk FOREIGN KEY (initial_import_id) REFERENCES public.catalog_imports(id) ON DELETE RESTRICT;

ALTER TABLE public.catalog_imports ADD CONSTRAINT catalog_imports_catalog_instance_id_fk FOREIGN KEY (catalog_instance_id) REFERENCES public.catalog_instance(id) ON DELETE RESTRICT;

ALTER TABLE public.catalog_changes ADD CONSTRAINT catalog_changes_import_id_fk FOREIGN KEY (import_id) REFERENCES public.catalog_imports(id) ON DELETE RESTRICT;

CREATE INDEX artists_agency_id_idx ON public.artists (agency_id);

CREATE INDEX artist_group_members_member_id_idx ON public.artist_group_members (member_id);

CREATE INDEX artist_external_accounts_account_id_idx ON public.artist_external_accounts (account_id);



CREATE INDEX videos_source_account_id_idx ON public.videos (source_account_id);

CREATE INDEX live_archives_primary_artist_id_idx ON public.live_archives (primary_artist_id);



CREATE INDEX archive_sources_document_id_idx ON public.archive_sources (document_id);



CREATE INDEX performances_source_document_id_idx ON public.performances (source_document_id);



CREATE INDEX concerts_source_document_id_idx ON public.concerts (source_document_id);



CREATE INDEX concert_ticket_windows_concert_id_idx ON public.concert_ticket_windows (concert_id);

CREATE INDEX album_artists_artist_id_idx ON public.album_artists (artist_id);

CREATE INDEX recordings_song_id_idx ON public.recordings (song_id);

CREATE INDEX recordings_official_video_id_idx ON public.recordings (official_video_id);

CREATE INDEX recording_artists_artist_id_idx ON public.recording_artists (artist_id);

CREATE INDEX recording_external_ids_recording_id_idx ON public.recording_external_ids (recording_id);

CREATE INDEX album_tracks_recording_id_idx ON public.album_tracks (recording_id);

CREATE INDEX recording_lyrics_source_document_id_idx ON public.recording_lyrics (source_document_id);

CREATE INDEX covers_song_id_idx ON public.covers (song_id);

CREATE INDEX cover_artists_artist_id_idx ON public.cover_artists (artist_id);

CREATE INDEX catalog_instance_initial_import_id_idx ON public.catalog_instance (initial_import_id);

CREATE INDEX catalog_imports_catalog_instance_id_idx ON public.catalog_imports (catalog_instance_id);

CREATE INDEX catalog_changes_import_id_idx ON public.catalog_changes (import_id);

CREATE INDEX live_archives_broadcast_at_id_idx ON public.live_archives (broadcast_at, id);

CREATE INDEX performances_song_id_archive_id_idx ON public.performances (song_id, archive_id);

CREATE INDEX performance_artists_artist_id_performance_id_idx ON public.performance_artists (artist_id, performance_id);

CREATE INDEX archive_artists_artist_id_archive_id_idx ON public.archive_artists (artist_id, archive_id);

CREATE INDEX song_artists_artist_id_song_id_idx ON public.song_artists (artist_id, song_id);

CREATE INDEX concert_artists_artist_id_concert_id_idx ON public.concert_artists (artist_id, concert_id);

CREATE INDEX concerts_event_date_id_idx ON public.concerts (event_date, id);

CREATE INDEX artist_aliases_normalized_alias_idx ON public.artist_aliases (normalized_alias);

CREATE INDEX catalog_changes_entity_type_entity_id_id_idx ON public.catalog_changes (entity_type, entity_id, id);


CREATE FUNCTION public.catalog_touch_version() RETURNS trigger LANGUAGE plpgsql
SET search_path = pg_catalog, public AS $$
BEGIN
 NEW.created_at := OLD.created_at;
 NEW.updated_at := clock_timestamp();
 NEW.version := OLD.version + 1;
 RETURN NEW;
END $$;
CREATE FUNCTION public.catalog_touch_timestamp() RETURNS trigger LANGUAGE plpgsql
SET search_path = pg_catalog, public AS $$
BEGIN
 NEW.created_at := OLD.created_at;
 NEW.updated_at := clock_timestamp();
 RETURN NEW;
END $$;
CREATE FUNCTION public.catalog_reject_history_mutation() RETURNS trigger LANGUAGE plpgsql
SET search_path = pg_catalog AS $$
BEGIN RAISE EXCEPTION 'catalog history is append-only' USING ERRCODE='23514'; END $$;
CREATE FUNCTION public.catalog_touch_parent() RETURNS trigger LANGUAGE plpgsql
SET search_path = pg_catalog, public AS $$
DECLARE previous_id integer; next_id integer;
BEGIN
 IF TG_OP <> 'INSERT' THEN previous_id := (to_jsonb(OLD)->>TG_ARGV[1])::integer; END IF;
 IF TG_OP <> 'DELETE' THEN next_id := (to_jsonb(NEW)->>TG_ARGV[1])::integer; END IF;
 EXECUTE format('UPDATE public.%I SET updated_at=clock_timestamp() WHERE id = ANY($1)',TG_ARGV[0])
 USING ARRAY[previous_id,next_id];
 RETURN NULL;
END $$;


CREATE TRIGGER artists_touch BEFORE UPDATE ON public.artists FOR EACH ROW EXECUTE FUNCTION public.catalog_touch_version();

CREATE TRIGGER artist_aliases_touch BEFORE UPDATE ON public.artist_aliases FOR EACH ROW EXECUTE FUNCTION public.catalog_touch_timestamp();

CREATE TRIGGER agencies_touch BEFORE UPDATE ON public.agencies FOR EACH ROW EXECUTE FUNCTION public.catalog_touch_version();

CREATE TRIGGER artist_group_members_touch BEFORE UPDATE ON public.artist_group_members FOR EACH ROW EXECUTE FUNCTION public.catalog_touch_timestamp();

CREATE TRIGGER external_accounts_touch BEFORE UPDATE ON public.external_accounts FOR EACH ROW EXECUTE FUNCTION public.catalog_touch_version();

CREATE TRIGGER artist_external_accounts_touch BEFORE UPDATE ON public.artist_external_accounts FOR EACH ROW EXECUTE FUNCTION public.catalog_touch_timestamp();

CREATE TRIGGER songs_touch BEFORE UPDATE ON public.songs FOR EACH ROW EXECUTE FUNCTION public.catalog_touch_version();

CREATE TRIGGER song_artists_touch BEFORE UPDATE ON public.song_artists FOR EACH ROW EXECUTE FUNCTION public.catalog_touch_timestamp();

CREATE TRIGGER karaoke_numbers_touch BEFORE UPDATE ON public.karaoke_numbers FOR EACH ROW EXECUTE FUNCTION public.catalog_touch_timestamp();

CREATE TRIGGER videos_touch BEFORE UPDATE ON public.videos FOR EACH ROW EXECUTE FUNCTION public.catalog_touch_version();

CREATE TRIGGER live_archives_touch BEFORE UPDATE ON public.live_archives FOR EACH ROW EXECUTE FUNCTION public.catalog_touch_version();

CREATE TRIGGER archive_artists_touch BEFORE UPDATE ON public.archive_artists FOR EACH ROW EXECUTE FUNCTION public.catalog_touch_timestamp();

CREATE TRIGGER source_documents_immutable BEFORE UPDATE OR DELETE ON public.source_documents FOR EACH ROW EXECUTE FUNCTION public.catalog_reject_history_mutation();

CREATE TRIGGER archive_sources_touch BEFORE UPDATE ON public.archive_sources FOR EACH ROW EXECUTE FUNCTION public.catalog_touch_timestamp();

CREATE TRIGGER performances_touch BEFORE UPDATE ON public.performances FOR EACH ROW EXECUTE FUNCTION public.catalog_touch_version();

CREATE TRIGGER performance_artists_touch BEFORE UPDATE ON public.performance_artists FOR EACH ROW EXECUTE FUNCTION public.catalog_touch_timestamp();

CREATE TRIGGER concerts_touch BEFORE UPDATE ON public.concerts FOR EACH ROW EXECUTE FUNCTION public.catalog_touch_version();

CREATE TRIGGER concert_artists_touch BEFORE UPDATE ON public.concert_artists FOR EACH ROW EXECUTE FUNCTION public.catalog_touch_timestamp();

CREATE TRIGGER concert_ticket_windows_touch BEFORE UPDATE ON public.concert_ticket_windows FOR EACH ROW EXECUTE FUNCTION public.catalog_touch_timestamp();

CREATE TRIGGER albums_touch BEFORE UPDATE ON public.albums FOR EACH ROW EXECUTE FUNCTION public.catalog_touch_version();

CREATE TRIGGER album_artists_touch BEFORE UPDATE ON public.album_artists FOR EACH ROW EXECUTE FUNCTION public.catalog_touch_timestamp();

CREATE TRIGGER recordings_touch BEFORE UPDATE ON public.recordings FOR EACH ROW EXECUTE FUNCTION public.catalog_touch_version();

CREATE TRIGGER recording_artists_touch BEFORE UPDATE ON public.recording_artists FOR EACH ROW EXECUTE FUNCTION public.catalog_touch_timestamp();

CREATE TRIGGER recording_external_ids_touch BEFORE UPDATE ON public.recording_external_ids FOR EACH ROW EXECUTE FUNCTION public.catalog_touch_timestamp();

CREATE TRIGGER album_tracks_touch BEFORE UPDATE ON public.album_tracks FOR EACH ROW EXECUTE FUNCTION public.catalog_touch_timestamp();

CREATE TRIGGER recording_lyrics_touch BEFORE UPDATE ON public.recording_lyrics FOR EACH ROW EXECUTE FUNCTION public.catalog_touch_version();

CREATE TRIGGER covers_touch BEFORE UPDATE ON public.covers FOR EACH ROW EXECUTE FUNCTION public.catalog_touch_version();

CREATE TRIGGER cover_artists_touch BEFORE UPDATE ON public.cover_artists FOR EACH ROW EXECUTE FUNCTION public.catalog_touch_timestamp();

CREATE TRIGGER catalog_instance_touch BEFORE UPDATE ON public.catalog_instance FOR EACH ROW EXECUTE FUNCTION public.catalog_touch_timestamp();

CREATE TRIGGER catalog_imports_immutable BEFORE UPDATE OR DELETE ON public.catalog_imports FOR EACH ROW EXECUTE FUNCTION public.catalog_reject_history_mutation();

CREATE TRIGGER catalog_changes_immutable BEFORE UPDATE OR DELETE ON public.catalog_changes FOR EACH ROW EXECUTE FUNCTION public.catalog_reject_history_mutation();

CREATE TRIGGER artist_aliases_parent_touch AFTER INSERT OR UPDATE OR DELETE ON public.artist_aliases FOR EACH ROW EXECUTE FUNCTION public.catalog_touch_parent('artists','artist_id');

CREATE TRIGGER artist_group_members_parent_touch AFTER INSERT OR UPDATE OR DELETE ON public.artist_group_members FOR EACH ROW EXECUTE FUNCTION public.catalog_touch_parent('artists','group_id');

CREATE TRIGGER artist_external_accounts_parent_touch AFTER INSERT OR UPDATE OR DELETE ON public.artist_external_accounts FOR EACH ROW EXECUTE FUNCTION public.catalog_touch_parent('artists','artist_id');

CREATE TRIGGER song_artists_parent_touch AFTER INSERT OR UPDATE OR DELETE ON public.song_artists FOR EACH ROW EXECUTE FUNCTION public.catalog_touch_parent('songs','song_id');

CREATE TRIGGER karaoke_numbers_parent_touch AFTER INSERT OR UPDATE OR DELETE ON public.karaoke_numbers FOR EACH ROW EXECUTE FUNCTION public.catalog_touch_parent('songs','song_id');

CREATE TRIGGER archive_artists_parent_touch AFTER INSERT OR UPDATE OR DELETE ON public.archive_artists FOR EACH ROW EXECUTE FUNCTION public.catalog_touch_parent('live_archives','archive_id');

CREATE TRIGGER archive_sources_parent_touch AFTER INSERT OR UPDATE OR DELETE ON public.archive_sources FOR EACH ROW EXECUTE FUNCTION public.catalog_touch_parent('live_archives','archive_id');

CREATE TRIGGER performance_artists_parent_touch AFTER INSERT OR UPDATE OR DELETE ON public.performance_artists FOR EACH ROW EXECUTE FUNCTION public.catalog_touch_parent('performances','performance_id');

CREATE TRIGGER concert_artists_parent_touch AFTER INSERT OR UPDATE OR DELETE ON public.concert_artists FOR EACH ROW EXECUTE FUNCTION public.catalog_touch_parent('concerts','concert_id');

CREATE TRIGGER concert_ticket_windows_parent_touch AFTER INSERT OR UPDATE OR DELETE ON public.concert_ticket_windows FOR EACH ROW EXECUTE FUNCTION public.catalog_touch_parent('concerts','concert_id');

CREATE TRIGGER album_artists_parent_touch AFTER INSERT OR UPDATE OR DELETE ON public.album_artists FOR EACH ROW EXECUTE FUNCTION public.catalog_touch_parent('albums','album_id');

CREATE TRIGGER album_tracks_parent_touch AFTER INSERT OR UPDATE OR DELETE ON public.album_tracks FOR EACH ROW EXECUTE FUNCTION public.catalog_touch_parent('albums','album_id');

CREATE TRIGGER recording_artists_parent_touch AFTER INSERT OR UPDATE OR DELETE ON public.recording_artists FOR EACH ROW EXECUTE FUNCTION public.catalog_touch_parent('recordings','recording_id');

CREATE TRIGGER recording_external_ids_parent_touch AFTER INSERT OR UPDATE OR DELETE ON public.recording_external_ids FOR EACH ROW EXECUTE FUNCTION public.catalog_touch_parent('recordings','recording_id');

CREATE TRIGGER cover_artists_parent_touch AFTER INSERT OR UPDATE OR DELETE ON public.cover_artists FOR EACH ROW EXECUTE FUNCTION public.catalog_touch_parent('covers','cover_id');

CREATE TRIGGER performances_parent_touch AFTER INSERT OR UPDATE OR DELETE ON public.performances FOR EACH ROW EXECUTE FUNCTION public.catalog_touch_parent('live_archives','archive_id');

CREATE TRIGGER recording_lyrics_parent_touch AFTER INSERT OR UPDATE OR DELETE ON public.recording_lyrics FOR EACH ROW EXECUTE FUNCTION public.catalog_touch_parent('recordings','recording_id');

INSERT INTO public.catalog_instance (schema_version) VALUES ('catalog-v1');
