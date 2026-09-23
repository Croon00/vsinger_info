from __future__ import annotations
from datetime import date, datetime
from pathlib import Path
from typing import Any
import hashlib
import json
import re
import unicodedata
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pydantic import ConfigDict, Field, ValidationError, create_model
from .contracts import Ref

RESOURCES = json.loads(
    Path(__file__).with_name("resources.json").read_text(encoding="utf-8")
)
TYPES = {
    "TEXT": str,
    "INTEGER": int,
    "SMALLINT": int,
    "BOOLEAN": bool,
    "DATE": date,
    "TIMESTAMPTZ": datetime,
    "JSONB": dict,
}
MODELS = {}
for name, resource in RESOURCES.items():
    for partial in (False, True):
        fields = {}
        for f in resource["fields"]:
            typ = TYPES[f["type"]]
            if f.get("reference"):
                typ = typ | Ref
            if f["nullable"]:
                typ = typ | None
            default = None if partial or f["nullable"] else ...
            if "default" in f:
                default = f["default"]
            fields[f["name"]] = (typ, default)
        MODELS[name, partial] = create_model(
            name + ("Patch" if partial else "Create"),
            __config__=ConfigDict(extra="forbid"),
            **fields,
        )


class DomainError(Exception):
    def __init__(self, message, status=422):
        super().__init__(message)
        self.status = status


def canonical(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    )


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def validate(name: str, data: dict, partial=False) -> dict:
    if name not in RESOURCES:
        raise DomainError("지원하지 않는 자료 종류입니다.")
    try:
        result = (
            MODELS[name, partial]
            .model_validate(data)
            .model_dump(mode="json", by_alias=True, exclude_unset=partial)
        )
    except ValidationError as exc:
        errors = [
            str(e["loc"][0]) + ": " + e["msg"] for e in exc.errors(include_input=False)
        ]
        raise DomainError(" / ".join(errors)) from None
    for f in RESOURCES[name]["fields"]:
        key = f["name"]
        if key not in result:
            continue
        value = result[key]
        if value is None:
            if not f["nullable"]:
                raise DomainError(key + ": 필수 값입니다.")
            continue
        if isinstance(value, dict) and "$ref" in value:
            continue
        if isinstance(value, str) and not value.strip():
            raise DomainError(key + ": 빈 문자열은 사용할 수 없습니다.")
        if "options" in f and value not in f["options"]:
            raise DomainError(key + ": 허용되지 않은 값입니다.")
        if f.get("reference") and (not isinstance(value, int) or value <= 0):
            raise DomainError(key + ": 올바른 연결을 선택하세요.")
        if f["type"] == "TIMESTAMPTZ" and datetime.fromisoformat(value).tzinfo is None:
            raise DomainError(key + ": 시간대(+09:00 등)를 포함하세요.")
        if (key == "url" or key.endswith("_url")) and not re.match(
            r"^https?://[^\s]+$", value
        ):
            raise DomainError(key + ": http 또는 https 주소를 입력하세요.")
        if (
            key in {"position", "duration_ms", "duration_seconds", "start_seconds"}
            and value < 0
        ):
            raise DomainError(key + ": 0 이상이어야 합니다.")
        if key in {"ordinal", "disc_number", "track_number"} and value < 1:
            raise DomainError(key + ": 1 이상이어야 합니다.")
    if partial:
        return result
    if name == "artists":
        m, d = result.get("birthday_month"), result.get("birthday_day")
        if (m is None) != (d is None):
            raise DomainError("생일 월과 일을 함께 입력하세요.")
        if m is not None:
            try:
                date(2000, m, d)
            except ValueError:
                raise DomainError("존재하지 않는 생일입니다.") from None
        if result.get("theme_color") and not re.fullmatch(
            r"#[0-9a-fA-F]{6}", result["theme_color"]
        ):
            raise DomainError("상징색은 #RRGGBB 형식입니다.")
    if (
        name == "external_accounts"
        and result["platform"] in {"website", "fanclub"}
        and result["collection_enabled"]
    ):
        raise DomainError("공식 사이트·팬클럽은 수집 대상으로 설정할 수 없습니다.")
    if name == "artist_group_members":
        if result["group_id"] == result["member_id"]:
            raise DomainError("자기 자신을 멤버로 연결할 수 없습니다.")
        if (
            result.get("joined_on")
            and result.get("left_on")
            and result["left_on"] < result["joined_on"]
        ):
            raise DomainError("탈퇴일이 가입일보다 빠릅니다.")
    if name == "videos" and not re.fullmatch(
        r"[A-Za-z0-9_-]{11}", result["platform_video_id"]
    ):
        raise DomainError("YouTube 영상 ID는 11자리입니다.")
    if (
        name == "performances"
        and result.get("end_seconds") is not None
        and result["end_seconds"] <= result["start_seconds"]
    ):
        raise DomainError("종료 시점은 시작 시점보다 뒤여야 합니다.")
    if name == "concerts":
        precision = result["time_precision"]
        start = result.get("starts_at")
        end = result.get("ends_at")
        day = result.get("event_date")
        zone = result.get("timezone_name")
        try:
            tz = ZoneInfo(zone) if zone else None
        except (ZoneInfoNotFoundError, ValueError):
            raise DomainError("올바른 IANA 시간대를 입력하세요.") from None
        if precision == "unknown" and any([start, end, day]):
            raise DomainError("날짜 미정이면 날짜/시간을 비워 주세요.")
        if precision == "date" and (not day or start or end):
            raise DomainError("날짜만 아는 공연은 날짜만 입력하세요.")
        if precision == "datetime":
            if not all([day, start, tz]):
                raise DomainError(
                    "정확한 공연 시각에는 날짜·시작 시각·시간대가 필요합니다."
                )
            if datetime.fromisoformat(start).astimezone(tz).date().isoformat() != day:
                raise DomainError("공연 날짜와 현지 시작일이 다릅니다.")
            if end and datetime.fromisoformat(end) <= datetime.fromisoformat(start):
                raise DomainError("종료 시각이 시작보다 빠릅니다.")
    if name == "concert_ticket_windows":
        if not any(
            result.get(k)
            for k in ("label", "url", "opens_at", "closes_at", "price_text")
        ):
            raise DomainError("티켓 정보를 입력하세요.")
        if (
            result.get("opens_at")
            and result.get("closes_at")
            and datetime.fromisoformat(result["closes_at"])
            < datetime.fromisoformat(result["opens_at"])
        ):
            raise DomainError("예매 종료가 시작보다 빠릅니다.")
    if name == "albums":
        y, m, d = [
            result.get(k) for k in ("release_year", "release_month", "release_day")
        ]
        if (m is not None and y is None) or (d is not None and m is None):
            raise DomainError("발매 연·월·일을 순서대로 입력하세요.")
        if y is not None:
            try:
                date(y, m if m is not None else 1, d if d is not None else 1)
            except ValueError:
                raise DomainError("올바른 발매일을 입력하세요.") from None
    if (
        name == "source_documents"
        and not result.get("content_text")
        and not result.get("source_metadata")
    ):
        raise DomainError("원문 또는 메타데이터를 입력하세요.")
    return result


def generated(name, data):
    result = dict(data)
    if name == "artist_aliases":
        result["normalized_alias"] = " ".join(
            unicodedata.normalize("NFKC", result["alias"]).casefold().split()
        )
    if name == "source_documents":
        result["content_hash"] = digest(
            {
                "text": result.get("content_text"),
                "metadata": result.get("source_metadata"),
            }
        )
    return result
