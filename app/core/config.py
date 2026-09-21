from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Railway와 로컬 .env에서 읽어오는 앱 전체 설정입니다."""

    app_name: str = "schedule-music"
    # DATABASE_URL is retained for isolated legacy and read-only migration tools.
    # Normal API/runtime code uses new_database_url and the identity guard.
    database_url: str | None = None
    new_database_url: str | None = None
    new_catalog_instance_id: str | None = None
    catalog_schema_version: str = "catalog-v2"
    api_key: str | None = None
    discord_bot_token: str | None = None
    discord_guild_id: int | None = None
    agent_interval_seconds: int = 86400
    agent_enabled: bool = False
    agent_run_on_start: bool = False
    runtime_cutover_enabled: bool = False
    database_auto_init: bool = False
    public_base_url: str | None = None
    cors_allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    x_provider: Literal["auto", "twscrape", "x_api"] = "auto"
    x_bearer_token: str | None = None
    twscrape_auth_token: str | None = None
    twscrape_ct0: str | None = None
    twscrape_username: str = "schedule_music"
    twscrape_db_path: str = "data/twscrape_accounts.db"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1-mini"
    openai_audio_model: str = "whisper-1"
    lyrics_audio_fallback_max_seconds: int = 500
    lyrics_audio_direct_download: bool = True
    openai_audio_max_upload_mb: int = 24
    youtube_transcript_proxy_http_url: str | None = None
    youtube_transcript_proxy_https_url: str | None = None
    webshare_proxy_username: str | None = None
    webshare_proxy_password: str | None = None
    webshare_proxy_locations: str | None = None
    ytdlp_proxy_url: str | None = None
    youtube_api_key: str | None = None
    youtube_auto_link_max_tracks: int = 50
    youtube_auto_link_concurrency: int = 4
    lyrics_context_extract_max_chars: int = 15000
    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_redirect_uri: str | None = None
    google_calendar_id: str = "primary"
    spotify_client_id: str | None = None
    spotify_client_secret: str | None = None
    aws_endpoint_url_s3: str | None = None
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    aws_region: str | None = None
    avatar_bucket: str = "artists-avator"

    # Some integrations (for example twscrape's TWS_HTTP_BACKEND) read their
    # own environment variables directly. They must not prevent app settings
    # from loading when present in a local dotenv file.
    model_config = SettingsConfigDict(
        env_file=(".env", ".env.catalog"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator(
        "discord_bot_token",
        "database_url",
        "new_database_url",
        "new_catalog_instance_id",
        "api_key",
        "discord_guild_id",
        "public_base_url",
        "x_bearer_token",
        "twscrape_auth_token",
        "twscrape_ct0",
        "openai_api_key",
        "youtube_transcript_proxy_http_url",
        "youtube_transcript_proxy_https_url",
        "webshare_proxy_username",
        "webshare_proxy_password",
        "webshare_proxy_locations",
        "ytdlp_proxy_url",
        "youtube_api_key",
        "google_client_id",
        "google_client_secret",
        "google_redirect_uri",
        "spotify_client_id",
        "spotify_client_secret",
        "aws_endpoint_url_s3",
        "aws_access_key_id",
        "aws_secret_access_key",
        "aws_region",
        mode="before",
    )
    @classmethod
    def empty_string_to_none(cls, value):
        """Railway/.env의 빈 문자열 값을 Optional 필드에서 None처럼 다루게 합니다."""
        if value == "":
            return None
        return value

    @property
    def cors_allowed_origin_list(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.cors_allowed_origins.split(",")
            if origin.strip()
        ]


settings = Settings()
