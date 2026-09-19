from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row

from app.core.config import settings
from app.core.artist_identity import find_preset_artist, normalize_artist_display_names


# RK Music 아티스트·발매 페이지에서 확인한 공식 X 계정입니다.
# 시스템 소유 source이므로 Discord route는 어느 길드에나 전달할 수 있지만,
# 특정 개인의 Google Calendar에는 의도적으로 연결하지 않습니다.
RK_MUSIC_X_SOURCES: tuple[tuple[str, str], ...] = (
    ("RK Music", "RKMusic_inc"),
    ("HACHI", "8HaChi_hacchi"),
    ("KMNZ", "KMNSTREET"),
    ("KMNZ TINA", "kmnztina"),
    ("KMNZ TINA", "kmnztina_"),
    ("NOiTA", "noitanyo"),
    ("OTOUSAN", "otousan_gifu"),
    ("VESPERBELL YOMI", "vesper_yomi"),
    ("KMNZ LITA", "kmnzlita"),
    ("KMNZ NERO", "kmnznero"),
    ("KMNZ NERO", "kmnznero_"),
    ("VESPERBELL KASUKA", "vesper_kasuka"),
    ("MEDACHI", "medachi3_3"),
    ("VESPERBELL", "vesperbell_info"),
    ("CULUA", "culua0211"),
    ("NEUN", "neun09"),
    ("MEDA", "medazcd"),
    ("CONA", "C_O_SK"),
    ("IMI", "IMI_RKMusic"),
    ("XIDEN", "XIDEN_RKMusic"),
    ("YONO", "Yono_RKMusic"),
    ("MEMESIA", "MEMESIA_0224"),
    ("LEWNE", "LEWNE_1123"),
    ("羽緒", "Hao_RKM"),
    ("Cil", "Cil_0320"),
    ("深影", "Mikage_0916"),
    ("wouca", "wouca_rkm"),
    ("妃玖", "fused_kisaki"),
    ("Diα", "fused_dia"),
    ("HONK THE HORN", "HONKTHEHORN"),
    ("NUROJUNK", "NUROJUNK"),
)
RK_MUSIC_SYSTEM_USER_ID = "system:rkmusic"
RK_MUSIC_X_SOURCE_RENAMES: dict[tuple[str, str], str] = {
    ("羽緒", "Hao_1211"): "Hao_RKM",
}

ADDITIONAL_ARTIST_X_SOURCES: tuple[tuple[str, str], ...] = (
    ("Aimer", "Aimer_and_staff"),
    ("milet", "milet_music"),
    ("ReoNa", "xoxleoxox"),
    ("tayori", "tayori_tri"),
    ("ヨルシカ", "nbuna_staff"),
    ("Rokudenashi", "Rokudenashi_nzn"),
    ("LiSA", "LiSA_OLiVE"),
    ("yanaginagi", "yanaginagi"),
    ("supercell", "supercell_sc"),
    ("fhána", "fhana_jp"),
)
ADDITIONAL_ARTISTS_SYSTEM_USER_ID = "system:additional-artists"

VTUBER_X_SOURCES: tuple[tuple[str, str], ...] = (
    ("MOCO", "hth_moco"),
    ("BAMBI", "hth_bambi"),
    ("SAKUYA", "NUROJUNK_SAKUYA"),
    ("KAGURA", "NJ_KAGURA"),
    ("Enma_Ruri", "Ruri_Enma"),
    ("Setono_Toto", "setono_toto1010"),
    ("Setono_Toto", "setono_toto_sub"),
    ("Minase_Nagi", "minase_nagi7"),
)
VTUBER_SYSTEM_USER_ID = "system:vtuber-sources"

# KAMITSUBAKI STUDIO의 V.W.P 아티스트 페이지에 연결된 공식 멤버 계정입니다.
VWP_X_SOURCES: tuple[tuple[str, str], ...] = (
    ("花譜", "virtual_kaf"),
    ("理芽", "RIM_virtual"),
    ("春猿火", "harusaruhi"),
    ("ヰ世界情緒", "isekaijoucho"),
    ("幸祜", "KOKO__virtual"),
)
VWP_SYSTEM_USER_ID = "system:vwp"

KAMITSUBAKI_X_SOURCES: tuple[tuple[str, str], ...] = (
    ("KAMITSUBAKI STUDIO", "kamitsubaki_jp"),
    ("CIEL", "CIEL_VanillaSky"),
    ("Sooda", "sooda_oda"),
    ("ASU", "ASU_virtual"),
    ("佳鏡院", "kakyoin_gr"),
    ("御莉姫", "orihime_gr"),
    ("硝子宮", "garasumiya_gr"),
    ("美古途", "mikoto_gr"),
    ("夕凪機", "yunagi_gr"),
    ("氷夏至", "hinageshi_gr"),
)
KAMITSUBAKI_SYSTEM_USER_ID = "system:kamitsubaki"

RIOT_MUSIC_ARTIST_SOURCES: tuple[tuple[str, str, str], ...] = (
    ("IORI MATSUNAGA", "iori_m_RIOT", "https://www.youtube.com/channel/UC--zuEfONeFXPvLqX0Kvbuw"),
    ("ANKO ASAKURA", "anko_a_RIOT", "https://www.youtube.com/@ANKOASAKURA"),
    ("MIONA SUMERAGI", "miona_s_RIOT", "https://www.youtube.com/channel/UCoAL7HKxjpPGuA1G4bdfHTQ"),
    ("CHISE ITSUKI", "chise_i_BW", "https://www.youtube.com/@CHISEITSUKI"),
    ("SHIRASE SHIRAKAWA", "shirase_s_BW", "https://www.youtube.com/@SHIRASESHIRAKAWA"),
    ("RANZE TOKINIWA", "ranze_t_BW", "https://www.youtube.com/channel/UCw9_unaq1z9CJXeFOZm-MfQ"),
    ("MINAMI IZUMI", "minami_i_MGS", "https://www.youtube.com/@izumiminami"),
    ("SHUNA", "shuna_MGS", "https://www.youtube.com/@shuna_mgs"),
    ("MEMENTOVANITAS", "memento_v_MGS", "https://www.youtube.com/@MEMENTOVANITAS"),
    ("DENSHINBASHIRA-CHAN", "denchan_MGS", "https://www.youtube.com/@DENSHINBASHIRA-CHAN"),
    ("LECIEL MIYAJIMA", "leciel_m_MGS", "https://www.youtube.com/@LECIELMIYAJIMA"),
    ("KUGURU KASAYA", "kuguru_k_MGS", "https://www.youtube.com/@KUGURUKASAYA"),
)
RIOT_MUSIC_X_SOURCES: tuple[tuple[str, str], ...] = tuple(
    (artist_name, x_username)
    for artist_name, x_username, _youtube_url in RIOT_MUSIC_ARTIST_SOURCES
)
RIOT_MUSIC_YOUTUBE_CHANNELS: tuple[tuple[str, str], ...] = tuple(
    (artist_name, youtube_url)
    for artist_name, _x_username, youtube_url in RIOT_MUSIC_ARTIST_SOURCES
)
RIOT_MUSIC_SYSTEM_USER_ID = "system:riotmusic"


def get_connection() -> Connection:
    """환경변수 DATABASE_URL로 PostgreSQL 연결을 만들고 row를 dict 형태로 반환합니다."""
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is required for database-backed routes.")
    return psycopg.connect(settings.database_url, row_factory=dict_row)


def _seed_rkmusic_x_sources(conn: Connection) -> None:
    """Insert the curated RK Music X sources without duplicating user data."""
    for artist_name, x_username in RK_MUSIC_X_SOURCES:
        # 오래된 source preset에 깨진 표시 이름이 있어도 표준 영문 아티스트명은
        # 보존합니다.
        if x_username == "Mikage_0916":
            artist_name = "MIKAGE"
        artist = find_preset_artist(conn, RK_MUSIC_SYSTEM_USER_ID, artist_name, 'RK Music')
        if artist is None:
            artist = conn.execute(
                """
                INSERT INTO artists (discord_user_id, name, display_name, notes)
                VALUES (%s, %s, %s, %s)
                RETURNING id
                """,
                (
                    RK_MUSIC_SYSTEM_USER_ID,
                    artist_name,
                    artist_name,
                    "Official RK Music X source (managed preset)",
                ),
            ).fetchone()

        for (renamed_artist, old_username), new_username in (
            RK_MUSIC_X_SOURCE_RENAMES.items()
        ):
            if renamed_artist != artist_name or new_username != x_username:
                continue
            conn.execute(
                """
                UPDATE artist_sources
                SET
                    value = %s,
                    external_user_id = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE artist_id = %s
                    AND source_type = 'x'
                    AND value = %s
                    AND NOT EXISTS (
                        SELECT 1
                        FROM artist_sources existing
                        WHERE existing.artist_id = %s
                            AND existing.source_type = 'x'
                            AND existing.value = %s
                    )
                """,
                (
                    new_username,
                    artist["id"],
                    old_username,
                    artist["id"],
                    new_username,
                ),
            )

        conn.execute(
            """
            INSERT INTO artist_sources (artist_id, source_type, label, value)
            VALUES (%s, 'x', 'Official X', %s)
            ON CONFLICT (artist_id, source_type, value) DO NOTHING
            """,
            (artist["id"], x_username),
        )


def _seed_artist_x_sources(
    conn: Connection,
    *,
    owner_id: str,
    sources: tuple[tuple[str, str], ...],
    note: str,
    agency: str | None = None,
) -> None:
    """Insert a named official-source preset without modifying user-owned artists."""
    for artist_name, x_username in sources:
        artist = find_preset_artist(conn, owner_id, artist_name, agency)
        if artist is None:
            artist = conn.execute(
                """
                INSERT INTO artists (discord_user_id, name, display_name, agency, notes)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
                """,
                (owner_id, artist_name, artist_name, agency, note),
            ).fetchone()
        elif agency:
            conn.execute(
                """
                UPDATE artists
                SET agency = %s
                WHERE id = %s AND (agency IS NULL OR agency = '')
                """,
                (agency, artist["id"]),
            )
        conn.execute(
            """
            INSERT INTO artist_sources (artist_id, source_type, label, value)
            VALUES (%s, 'x', 'Official X', %s)
            ON CONFLICT (artist_id, source_type, value) DO NOTHING
            """,
            (artist["id"], x_username),
        )


def init_db() -> None:
    """앱 실행에 필요한 PostgreSQL 테이블과 기존 DB의 누락 컬럼을 준비합니다."""
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS artists (
                id SERIAL PRIMARY KEY,
                discord_user_id TEXT,
                name TEXT NOT NULL,
                display_name TEXT,
                artist_kind TEXT NOT NULL DEFAULT 'vtuber',
                agency TEXT,
                show_in_spotify BOOLEAN NOT NULL DEFAULT TRUE,
                show_in_lyrics BOOLEAN NOT NULL DEFAULT TRUE,
                show_in_youtube_lives BOOLEAN NOT NULL DEFAULT TRUE,
                notes TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS artist_sources (
                id SERIAL PRIMARY KEY,
                artist_id INTEGER NOT NULL,
                source_type TEXT NOT NULL,
                label TEXT,
                value TEXT NOT NULL,
                external_user_id TEXT,
                last_seen_external_id TEXT,
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (artist_id) REFERENCES artists(id) ON DELETE CASCADE,
                UNIQUE (artist_id, source_type, value)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS artist_agencies (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            INSERT INTO artist_agencies (name)
            VALUES ('RK Music'), ('KAMITSUBAKI STUDIO'), ('RIOT MUSIC')
            ON CONFLICT (name) DO NOTHING
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS event_candidates (
                id SERIAL PRIMARY KEY,
                artist_id INTEGER,
                discord_user_id TEXT,
                source_id INTEGER,
                event_type TEXT NOT NULL DEFAULT 'live_event',
                event_format TEXT NOT NULL DEFAULT 'unknown',
                title TEXT NOT NULL,
                starts_at TEXT,
                venue TEXT,
                ticket_opens_at TEXT,
                ticket_closes_at TEXT,
                ticket_url TEXT,
                price_text TEXT,
                source_url TEXT,
                raw_text TEXT,
                status TEXT NOT NULL DEFAULT 'needs_review',
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (artist_id) REFERENCES artists(id) ON DELETE SET NULL,
                FOREIGN KEY (source_id) REFERENCES artist_sources(id) ON DELETE SET NULL
            )
            """
        )
        conn.execute("ALTER TABLE artists ADD COLUMN IF NOT EXISTS discord_user_id TEXT")
        conn.execute(
            "ALTER TABLE artists ADD COLUMN IF NOT EXISTS artist_kind TEXT NOT NULL DEFAULT 'vtuber'"
        )
        conn.execute("ALTER TABLE artists ADD COLUMN IF NOT EXISTS agency TEXT")
        conn.execute("ALTER TABLE artists ADD COLUMN IF NOT EXISTS profile_intro TEXT")
        conn.execute("ALTER TABLE artists ADD COLUMN IF NOT EXISTS debut_date TEXT")
        conn.execute("ALTER TABLE artists ADD COLUMN IF NOT EXISTS show_in_spotify BOOLEAN NOT NULL DEFAULT TRUE")
        conn.execute("ALTER TABLE artists ADD COLUMN IF NOT EXISTS show_in_lyrics BOOLEAN NOT NULL DEFAULT TRUE")
        conn.execute("ALTER TABLE artists ADD COLUMN IF NOT EXISTS show_in_youtube_lives BOOLEAN NOT NULL DEFAULT TRUE")
        conn.execute(
            "UPDATE artists SET artist_kind = 'singer' WHERE discord_user_id = %s",
            (ADDITIONAL_ARTISTS_SYSTEM_USER_ID,),
        )
        conn.execute(
            "UPDATE artists SET agency = 'RK Music' WHERE discord_user_id = %s",
            (RK_MUSIC_SYSTEM_USER_ID,),
        )
        conn.execute(
            "UPDATE artists SET agency = 'KAMITSUBAKI STUDIO' WHERE discord_user_id = %s",
            (VWP_SYSTEM_USER_ID,),
        )
        conn.execute(
            """
            UPDATE artists
            SET discord_user_id = %s
            WHERE discord_user_id IS NULL
                AND agency = 'KAMITSUBAKI STUDIO'
            """,
            (KAMITSUBAKI_SYSTEM_USER_ID,),
        )
        conn.execute(
            "UPDATE artists SET agency = 'KAMITSUBAKI STUDIO' WHERE discord_user_id = %s",
            (KAMITSUBAKI_SYSTEM_USER_ID,),
        )
        conn.execute(
            "UPDATE artists SET agency = 'RIOT MUSIC' WHERE discord_user_id = %s",
            (RIOT_MUSIC_SYSTEM_USER_ID,),
        )
        conn.execute(
            """
            DO $$ BEGIN
                ALTER TABLE artists ADD CONSTRAINT artists_artist_kind_check
                CHECK (artist_kind IN ('vtuber', 'singer'));
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$
            """
        )
        conn.execute("ALTER TABLE artists ADD COLUMN IF NOT EXISTS spotify_artist_id TEXT")
        conn.execute(
            "ALTER TABLE artists ADD COLUMN IF NOT EXISTS spotify_sync_enabled BOOLEAN NOT NULL DEFAULT TRUE"
        )
        conn.execute("ALTER TABLE artists ADD COLUMN IF NOT EXISTS spotify_name TEXT")
        conn.execute("ALTER TABLE artists ADD COLUMN IF NOT EXISTS spotify_image_url TEXT")
        conn.execute("ALTER TABLE artists ADD COLUMN IF NOT EXISTS spotify_url TEXT")
        conn.execute(
            "ALTER TABLE artists ADD COLUMN IF NOT EXISTS spotify_match_updated_at TIMESTAMPTZ"
        )
        conn.execute("ALTER TABLE artist_sources ADD COLUMN IF NOT EXISTS external_user_id TEXT")
        conn.execute("ALTER TABLE artist_sources ADD COLUMN IF NOT EXISTS last_seen_external_id TEXT")
        conn.execute("ALTER TABLE event_candidates ADD COLUMN IF NOT EXISTS discord_user_id TEXT")
        conn.execute("ALTER TABLE event_candidates ADD COLUMN IF NOT EXISTS ticket_closes_at TEXT")
        conn.execute("ALTER TABLE event_candidates ADD COLUMN IF NOT EXISTS capacity_text TEXT")
        conn.execute("ALTER TABLE event_candidates ADD COLUMN IF NOT EXISTS setlist_json TEXT")
        conn.execute("ALTER TABLE event_candidates ADD COLUMN IF NOT EXISTS merchandise_json TEXT")
        conn.execute(
            "ALTER TABLE event_candidates ADD COLUMN IF NOT EXISTS event_type TEXT NOT NULL DEFAULT 'live_event'"
        )
        conn.execute(
            "ALTER TABLE event_candidates ADD COLUMN IF NOT EXISTS event_format TEXT NOT NULL DEFAULT 'unknown'"
        )
        conn.execute(
            """
            UPDATE event_candidates
            SET event_type = 'ticket'
            WHERE event_type = 'live_event'
              AND (
                (starts_at IS NULL AND (ticket_opens_at IS NOT NULL OR ticket_closes_at IS NOT NULL))
                OR title ~* '(ticket|チケット|티켓|先行|受付|抽選|一般販売)'
              )
            """
        )
        conn.execute(
            """
            UPDATE event_candidates
            SET event_format = CASE
                WHEN venue IS NOT NULL AND venue <> '' AND
                     venue !~* '(youtube|유튜브|온라인|配信|stream)' AND
                     COALESCE(raw_text, '') ~* '(YouTube Live|歌枠|生配信|オンライン配信|ライブ配信|streaming live)'
                    THEN 'hybrid'
                WHEN venue IS NOT NULL AND venue <> '' AND
                     venue !~* '(youtube|유튜브|온라인|配信|stream)' THEN 'onsite'
                WHEN COALESCE(ticket_url, '') ~* '(youtube\\.com|youtu\\.be)' OR
                     COALESCE(source_url, '') ~* '(youtube\\.com|youtu\\.be)' OR
                     COALESCE(raw_text, '') ~* '(歌枠|YouTube Live|生配信|オンライン配信|streaming)'
                    THEN 'online'
                ELSE event_format
            END
            WHERE event_type = 'live_event'
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS google_oauth_tokens (
                discord_user_id TEXT PRIMARY KEY,
                access_token TEXT NOT NULL,
                refresh_token TEXT,
                expires_at TIMESTAMPTZ,
                scope TEXT,
                token_type TEXT,
                calendar_id TEXT NOT NULL DEFAULT 'primary',
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS source_items (
                id SERIAL PRIMARY KEY,
                discord_user_id TEXT NOT NULL,
                source_id INTEGER,
                external_id TEXT NOT NULL,
                url TEXT,
                published_at TIMESTAMPTZ,
                raw_text TEXT NOT NULL,
                item_type TEXT,
                classification_confidence DOUBLE PRECISION,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (source_id) REFERENCES artist_sources(id) ON DELETE SET NULL,
                UNIQUE (discord_user_id, source_id, external_id)
            )
            """
        )
        conn.execute("ALTER TABLE source_items ADD COLUMN IF NOT EXISTS item_type TEXT")
        conn.execute("ALTER TABLE source_items ADD COLUMN IF NOT EXISTS classification_confidence DOUBLE PRECISION")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS youtube_live_archives (
                id SERIAL PRIMARY KEY,
                source_item_id INTEGER,
                source_id INTEGER,
                youtube_video_id TEXT NOT NULL,
                youtube_url TEXT NOT NULL,
                performer_name TEXT,
                video_title TEXT,
                published_at TIMESTAMPTZ,
                broadcast_at TIMESTAMPTZ,
                status TEXT NOT NULL DEFAULT 'pending',
                top_comment TEXT,
                setlist JSONB NOT NULL DEFAULT '[]'::jsonb,
                attempts INTEGER NOT NULL DEFAULT 0,
                next_check_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_checked_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (source_item_id) REFERENCES source_items(id) ON DELETE CASCADE,
                FOREIGN KEY (source_id) REFERENCES artist_sources(id) ON DELETE CASCADE,
                UNIQUE (source_item_id, youtube_video_id)
            )
            """
        )
        conn.execute("ALTER TABLE youtube_live_archives ALTER COLUMN source_item_id DROP NOT NULL")
        conn.execute("ALTER TABLE youtube_live_archives ALTER COLUMN source_id DROP NOT NULL")
        conn.execute("ALTER TABLE youtube_live_archives ADD COLUMN IF NOT EXISTS video_title TEXT")
        conn.execute("ALTER TABLE youtube_live_archives ADD COLUMN IF NOT EXISTS performer_name TEXT")
        conn.execute("ALTER TABLE youtube_live_archives ADD COLUMN IF NOT EXISTS published_at TIMESTAMPTZ")
        conn.execute("ALTER TABLE youtube_live_archives ADD COLUMN IF NOT EXISTS broadcast_at TIMESTAMPTZ")
        conn.execute("ALTER TABLE youtube_live_archives ADD COLUMN IF NOT EXISTS duration_seconds INTEGER")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS youtube_song_performances (
                id SERIAL PRIMARY KEY,
                archive_id INTEGER NOT NULL,
                performed_on DATE NOT NULL,
                start_seconds INTEGER NOT NULL,
                timestamp_text TEXT NOT NULL,
                song_title TEXT NOT NULL,
                song_title_ko TEXT,
                original_artist TEXT,
                original_artist_ko TEXT,
                tj_number TEXT NOT NULL DEFAULT '등록X',
                ky_number TEXT NOT NULL DEFAULT '등록X',
                karaoke_checked_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (archive_id) REFERENCES youtube_live_archives(id) ON DELETE CASCADE,
                UNIQUE (archive_id, start_seconds, song_title)
            )
            """
        )
        conn.execute("ALTER TABLE youtube_song_performances ADD COLUMN IF NOT EXISTS original_artist TEXT")
        conn.execute("ALTER TABLE youtube_song_performances ADD COLUMN IF NOT EXISTS song_title_ko TEXT")
        conn.execute("ALTER TABLE youtube_song_performances ADD COLUMN IF NOT EXISTS original_artist_ko TEXT")
        conn.execute("ALTER TABLE youtube_song_performances ADD COLUMN IF NOT EXISTS tj_number TEXT NOT NULL DEFAULT '등록X'")
        conn.execute("ALTER TABLE youtube_song_performances ADD COLUMN IF NOT EXISTS ky_number TEXT NOT NULL DEFAULT '등록X'")
        conn.execute("ALTER TABLE youtube_song_performances ADD COLUMN IF NOT EXISTS karaoke_checked_at TIMESTAMPTZ")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS youtube_song_performances_title_date_idx "
            "ON youtube_song_performances (song_title, performed_on DESC)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS youtube_cover_videos (
                id SERIAL PRIMARY KEY,
                artist_id INTEGER NOT NULL,
                youtube_video_id TEXT NOT NULL,
                youtube_url TEXT NOT NULL,
                video_title TEXT NOT NULL,
                video_description TEXT,
                published_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (artist_id) REFERENCES artists(id) ON DELETE CASCADE,
                UNIQUE (artist_id, youtube_video_id)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS youtube_cover_videos_artist_date_idx "
            "ON youtube_cover_videos (artist_id, published_at DESC)"
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS youtube_cover_collaborators (
                cover_id INTEGER NOT NULL,
                artist_id INTEGER NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (cover_id, artist_id),
                FOREIGN KEY (cover_id) REFERENCES youtube_cover_videos(id) ON DELETE CASCADE,
                FOREIGN KEY (artist_id) REFERENCES artists(id) ON DELETE CASCADE
            )"""
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS karaoke_source_matches (
                id SERIAL PRIMARY KEY,
                song_title TEXT NOT NULL,
                artist_name TEXT,
                tj_number TEXT NOT NULL,
                source_url TEXT NOT NULL,
                source_name TEXT NOT NULL,
                fetched_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (source_name, song_title, artist_name, tj_number)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS karaoke_source_matches_title_idx "
            "ON karaoke_source_matches (song_title)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS youtube_channel_monitors (
                id SERIAL PRIMARY KEY,
                discord_user_id TEXT NOT NULL,
                artist_name TEXT NOT NULL,
                youtube_channel_id TEXT NOT NULL,
                channel_title TEXT NOT NULL,
                channel_url TEXT NOT NULL,
                uploads_playlist_id TEXT NOT NULL,
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                last_checked_at TIMESTAMPTZ,
                next_check_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (discord_user_id, youtube_channel_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS youtube_channel_videos (
                id SERIAL PRIMARY KEY,
                monitor_id INTEGER NOT NULL,
                youtube_video_id TEXT NOT NULL,
                video_title TEXT NOT NULL,
                actual_end_at TIMESTAMPTZ,
                collect_after TIMESTAMPTZ,
                status TEXT NOT NULL DEFAULT 'waiting',
                archive_id INTEGER,
                last_error TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (monitor_id) REFERENCES youtube_channel_monitors(id) ON DELETE CASCADE,
                FOREIGN KEY (archive_id) REFERENCES youtube_live_archives(id) ON DELETE SET NULL,
                UNIQUE (monitor_id, youtube_video_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS notification_routes (
                id SERIAL PRIMARY KEY,
                discord_user_id TEXT,
                guild_id TEXT NOT NULL,
                source_id INTEGER,
                item_type TEXT NOT NULL,
                discord_channel_id TEXT NOT NULL,
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (source_id) REFERENCES artist_sources(id) ON DELETE CASCADE,
                UNIQUE (guild_id, source_id, item_type, discord_channel_id)
            )
            """
        )
        # route가 예전에는 분류별로 나뉘어 있었습니다. 모든 새 게시물이 같은
        # source/channel 연결을 따르도록 하나로 통합합니다.
        conn.execute(
            """
            DELETE FROM notification_routes newer
            USING notification_routes older
            WHERE newer.id > older.id
                AND newer.guild_id = older.guild_id
                AND newer.source_id IS NOT DISTINCT FROM older.source_id
                AND newer.discord_channel_id = older.discord_channel_id
            """
        )
        conn.execute("UPDATE notification_routes SET item_type = 'all' WHERE item_type <> 'all'")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS notification_deliveries (
                id SERIAL PRIMARY KEY,
                notification_route_id INTEGER NOT NULL,
                source_item_id INTEGER NOT NULL,
                discord_message_id TEXT,
                delivered_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (notification_route_id) REFERENCES notification_routes(id) ON DELETE CASCADE,
                FOREIGN KEY (source_item_id) REFERENCES source_items(id) ON DELETE CASCADE,
                UNIQUE (notification_route_id, source_item_id)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS notification_deliveries_route_item_idx "
            "ON notification_deliveries (notification_route_id, source_item_id)"
        )
        _seed_rkmusic_x_sources(conn)
        _seed_artist_x_sources(
            conn,
            owner_id=ADDITIONAL_ARTISTS_SYSTEM_USER_ID,
            sources=ADDITIONAL_ARTIST_X_SOURCES,
            note="Official X source (managed preset)",
        )
        _seed_artist_x_sources(
            conn,
            owner_id=VWP_SYSTEM_USER_ID,
            sources=VWP_X_SOURCES,
            note="Official V.W.P member X source (managed preset)",
            agency="KAMITSUBAKI STUDIO",
        )
        _seed_artist_x_sources(
            conn,
            owner_id=KAMITSUBAKI_SYSTEM_USER_ID,
            sources=KAMITSUBAKI_X_SOURCES,
            note="Official KAMITSUBAKI STUDIO X source (managed preset)",
            agency="KAMITSUBAKI STUDIO",
        )
        _seed_artist_x_sources(
            conn,
            owner_id=RIOT_MUSIC_SYSTEM_USER_ID,
            sources=RIOT_MUSIC_X_SOURCES,
            note="Official RIOT MUSIC X source (managed preset)",
            agency="RIOT MUSIC",
        )
        _seed_artist_x_sources(
            conn,
            owner_id=VTUBER_SYSTEM_USER_ID,
            sources=VTUBER_X_SOURCES,
            note="Official VTuber X source (managed preset)",
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS calendar_syncs (
                id SERIAL PRIMARY KEY,
                discord_user_id TEXT NOT NULL,
                event_candidate_id INTEGER NOT NULL,
                provider TEXT NOT NULL DEFAULT 'google',
                event_type TEXT NOT NULL DEFAULT 'live',
                provider_event_id TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (event_candidate_id) REFERENCES event_candidates(id) ON DELETE CASCADE,
                UNIQUE (discord_user_id, event_candidate_id, provider)
            )
            """
        )
        conn.execute("ALTER TABLE calendar_syncs ADD COLUMN IF NOT EXISTS event_type TEXT NOT NULL DEFAULT 'live'")
        conn.execute(
            """
            ALTER TABLE calendar_syncs
            DROP CONSTRAINT IF EXISTS calendar_syncs_discord_user_id_event_candidate_id_provider_key
            """
        )
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS calendar_syncs_unique_event_type
            ON calendar_syncs (discord_user_id, event_candidate_id, provider, event_type)
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS songs (
                id SERIAL PRIMARY KEY,
                discord_user_id TEXT,
                original_title TEXT NOT NULL,
                title_ko TEXT,
                artist_name TEXT NOT NULL,
                artist_name_ko TEXT,
                album_name TEXT,
                album_name_ko TEXT,
                release_date TEXT,
                language_code TEXT,
                duration_ms INTEGER,
                youtube_url TEXT NOT NULL,
                youtube_video_id TEXT NOT NULL,
                spotify_track_id TEXT,
                spotify_url TEXT,
                spotify_album_id TEXT,
                spotify_artist_ids TEXT[],
                cover_image_url TEXT,
                spotify_raw JSONB,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (discord_user_id, youtube_video_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS song_lyrics (
                id SERIAL PRIMARY KEY,
                song_id INTEGER NOT NULL,
                original_lyrics TEXT NOT NULL,
                translation_ko TEXT NOT NULL,
                pronunciation_ko TEXT NOT NULL,
                lyrics_source_type TEXT NOT NULL,
                lyrics_source_url TEXT,
                translation_model TEXT,
                needs_review BOOLEAN NOT NULL DEFAULT TRUE,
                review_notes TEXT,
                reviewed_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (song_id) REFERENCES songs(id) ON DELETE CASCADE,
                UNIQUE (song_id)
            )
            """
        )
        conn.execute("ALTER TABLE songs ADD COLUMN IF NOT EXISTS lyricist TEXT")
        conn.execute("ALTER TABLE songs ADD COLUMN IF NOT EXISTS composer TEXT")
        conn.execute("ALTER TABLE songs ADD COLUMN IF NOT EXISTS arranger TEXT")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS spotify_track_title_translations (
                spotify_track_id TEXT PRIMARY KEY,
                original_title TEXT NOT NULL,
                title_ko TEXT NOT NULL,
                model TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute("ALTER TABLE song_lyrics ADD COLUMN IF NOT EXISTS review_notes TEXT")
        conn.execute("ALTER TABLE song_lyrics ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS namuwiki_templates (
                template_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                template_example TEXT NOT NULL,
                discord_user_id TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute("ALTER TABLE namuwiki_templates ADD COLUMN IF NOT EXISTS discord_user_id TEXT")
        _repair_online_live_dates(conn)
        normalize_artist_display_names(conn, apply=True)
        conn.commit()


def _repair_online_live_dates(conn: Connection) -> None:
    """Repair yearless online-live dates that an extractor assigned to an old year."""
    jst = timezone(timedelta(hours=9))
    rows = conn.execute(
        """
        SELECT e.id, e.starts_at, s.published_at, s.raw_text
        FROM event_candidates e
        JOIN source_items s ON s.url = e.source_url
        WHERE e.event_type = 'live_event' AND e.event_format = 'online'
        """
    ).fetchall()
    for row in rows:
        text = unicodedata.normalize("NFKC", row["raw_text"] or "")
        published_at = row["published_at"]
        if not published_at:
            continue
        local_published = published_at.astimezone(jst)
        date_match = re.search(
            r"(?<!\d)(1[0-2]|0?[1-9])\s*[./月]\s*(3[01]|[12]\d|0?[1-9])(?:日)?(?!\d)",
            text,
        )
        is_today = bool(re.search(r"(?:本日|今日|today|오늘)", text, re.IGNORECASE))
        if not date_match and not is_today:
            continue
        if date_match:
            month, day = int(date_match.group(1)), int(date_match.group(2))
            year = local_published.year
            if (month, day) < (local_published.month, local_published.day):
                year += 1
        else:
            year, month, day = (
                local_published.year,
                local_published.month,
                local_published.day,
            )
        time_match = re.search(r"(?<!\d)([01]?\d|2[0-3])\s*[:：]\s*([0-5]\d)", text)
        corrected = (
            datetime(
                year,
                month,
                day,
                int(time_match.group(1)) if time_match else 0,
                int(time_match.group(2)) if time_match else 0,
                tzinfo=jst,
            ).isoformat()
            if time_match
            else f"{year:04d}-{month:02d}-{day:02d}"
        )
        if corrected != row["starts_at"]:
            conn.execute(
                "UPDATE event_candidates SET starts_at = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                (corrected, row["id"]),
            )


def row_to_dict(row: dict[str, Any] | None) -> dict[str, Any] | None:
    """psycopg row를 일반 dict로 바꾸고, row가 없으면 None을 그대로 반환합니다."""
    if row is None:
        return None
    return dict(row)
