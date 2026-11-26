"""Manual lyrics editor contract for one original recording."""
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, TypeAdapter, field_validator


class LyricsEdit(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    version: int | None = Field(ge=1, strict=True)
    original_lyrics: str = Field(min_length=1, max_length=12000)
    translation_ko: str = Field(default="", max_length=12000)
    pronunciation_ko: str = Field(default="", max_length=12000)
    lyrics_source_url: str | None = Field(default=None, max_length=2048)

    @field_validator("original_lyrics", "translation_ko", "pronunciation_ko")
    @classmethod
    def normalize_lines(cls, value: str) -> str:
        value = value.replace("\r\n", "\n").replace("\r", "\n")
        if any(ord(char) < 32 and char not in "\n\t" for char in value):
            raise ValueError("가사에 사용할 수 없는 문자가 있습니다.")
        return value if value.strip() else ""

    @field_validator("original_lyrics")
    @classmethod
    def require_text(cls, value: str) -> str:
        if not value:
            raise ValueError("원문 가사를 입력해 주세요.")
        return value

    @field_validator("lyrics_source_url")
    @classmethod
    def validate_source(cls, value: str | None) -> str | None:
        url = (value or "").strip()
        if not url:
            return None
        parsed = TypeAdapter(HttpUrl).validate_python(url)
        if not url.startswith(("https://", "http://")) or any(char.isspace() for char in url) or parsed.username or parsed.password:
            raise ValueError("공개 가능한 HTTP 또는 HTTPS 출처 주소를 입력해 주세요.")
        return url
