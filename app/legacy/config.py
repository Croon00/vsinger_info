"""Configuration available only to explicitly imported legacy Google helpers."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class LegacyGoogleSettings(BaseSettings):
    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_redirect_uri: str | None = None
    google_calendar_id: str = "primary"
    public_base_url: str | None = None

    model_config = SettingsConfigDict(extra="ignore")


settings = LegacyGoogleSettings()
