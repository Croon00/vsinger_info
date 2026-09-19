"""Import vetted VSinger profile seed data into the local PostgreSQL database.

The importer never deletes artists or sources. It updates one unambiguous existing
artist by name, or creates a new artist when no match exists. Run with --dry-run
first; --apply performs the transaction.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.core.db import get_connection, init_db
from app.core.artist_identity import artist_name_aliases, display_artist_name, name_key


DEFAULT_SEED = Path("data/seeds/vsinger_profiles.seed.json")


def load_seed(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    artists = payload.get("artists")
    if not isinstance(artists, list):
        raise ValueError("Seed file must contain an 'artists' list.")
    live_events = payload.get("live_events", [])
    if not isinstance(live_events, list):
        raise ValueError("Seed file 'live_events' must be a list when present.")
    return payload


def find_matching_artists(conn: Any, item: dict[str, Any]) -> list[dict[str, Any]]:
    """Return candidates matching the canonical or display name within the agency."""
    return list(conn.execute(
        """
        SELECT id, name, display_name, agency
        FROM artists
        WHERE (regexp_replace(LOWER(name), '[[:space:]_]', '', 'g') = ANY(%s)
            OR LOWER(COALESCE(display_name, '')) = LOWER(%s))
          AND (agency IS NULL OR LOWER(agency) = LOWER(%s))
        ORDER BY id
        """,
        ([name_key(alias) for alias in artist_name_aliases(item['name'])], item["display_name"], item["agency"]),
    ).fetchall())


def upsert_profile(conn: Any, item: dict[str, Any], apply: bool) -> str:
    item = {**item, 'display_name': display_artist_name(item['name'], item['display_name'], item['agency'])}
    matches = find_matching_artists(conn, item)
    if len(matches) > 1:
        ids = ", ".join(str(row["id"]) for row in matches)
        return f"SKIP {item['display_name']}: ambiguous existing artists ({ids})"

    if matches:
        artist_id = matches[0]["id"]
        action = f"UPDATE #{artist_id} {item['display_name']}"
        if apply:
            conn.execute(
                """
                UPDATE artists
                SET display_name = %s,
                    artist_kind = %s,
                    agency = %s,
                    profile_intro = %s,
                    debut_date = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (
                    item["display_name"], item.get("artist_kind", "vtuber"), item["agency"],
                    item.get("profile_intro"), item.get("debut_date"), artist_id,
                ),
            )
    else:
        action = f"CREATE {item['display_name']}"
        if apply:
            row = conn.execute(
                """
                INSERT INTO artists (name, display_name, artist_kind, agency, profile_intro, debut_date)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    item["name"], item["display_name"], item.get("artist_kind", "vtuber"),
                    item["agency"], item.get("profile_intro"), item.get("debut_date"),
                ),
            ).fetchone()
            artist_id = row["id"]
        else:
            artist_id = None

    x_username = item.get("x_username")
    if apply and x_username and artist_id is not None:
        conn.execute(
            """
            INSERT INTO artist_sources (artist_id, source_type, label, value, is_active)
            VALUES (%s, 'x', 'Official X', %s, TRUE)
            ON CONFLICT (artist_id, source_type, value) DO UPDATE
            SET label = EXCLUDED.label, is_active = TRUE, updated_at = CURRENT_TIMESTAMP
            """,
            (artist_id, x_username),
        )
    return action


def find_artist_id_for_event(conn: Any, profile: dict[str, Any]) -> int | None:
    matches = find_matching_artists(conn, profile)
    return int(matches[0]["id"]) if len(matches) == 1 else None


def upsert_live_event(conn: Any, item: dict[str, Any], profile_by_key: dict[str, dict[str, Any]], apply: bool) -> str:
    profile = profile_by_key.get(item["artist_key"])
    if profile is None:
        return f"SKIP {item['title']}: artist_key not found"
    artist_id = find_artist_id_for_event(conn, profile)
    if artist_id is None:
        return f"SKIP {item['title']}: artist is ambiguous or missing"
    existing = conn.execute(
        "SELECT id FROM event_candidates WHERE artist_id = %s AND title = %s AND starts_at = %s",
        (artist_id, item["title"], item["starts_at"]),
    ).fetchone()
    values = (
        item.get("event_type", "live_event"), item.get("event_format", "unknown"), item["title"],
        item["starts_at"], item.get("venue"), item.get("price_text"), item.get("capacity_text"),
        item.get("source_url"), item.get("raw_text"), json.dumps(item.get("setlist", []), ensure_ascii=False),
        json.dumps(item.get("merchandise", []), ensure_ascii=False), item.get("status", "ready"),
    )
    if existing:
        if apply:
            conn.execute(
                """
                UPDATE event_candidates
                SET event_type = %s, event_format = %s, title = %s, starts_at = %s, venue = %s,
                    price_text = %s, capacity_text = %s, source_url = %s, raw_text = %s,
                    setlist_json = %s, merchandise_json = %s, status = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (*values, existing["id"]),
            )
        return f"UPDATE EVENT #{existing['id']} {item['title']}"
    if apply:
        conn.execute(
            """
            INSERT INTO event_candidates (
                artist_id, event_type, event_format, title, starts_at, venue, price_text, capacity_text,
                source_url, raw_text, setlist_json, merchandise_json, status
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (artist_id, *values),
        )
    return f"CREATE EVENT {item['title']}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Import VSinger profile seed data.")
    parser.add_argument("--seed", type=Path, default=DEFAULT_SEED, help="Path to the JSON seed file.")
    parser.add_argument("--apply", action="store_true", help="Write changes. Without it the command is a dry run.")
    parser.add_argument("--dry-run", action="store_true", help="Explicitly preview changes without writing.")
    args = parser.parse_args()
    seed = load_seed(args.seed)
    artists = seed["artists"]
    live_events = seed["live_events"]
    profile_by_key = {item["artist_key"]: item for item in artists}

    apply = args.apply and not args.dry_run
    if apply:
        init_db()
    with get_connection() as conn:
        results = [upsert_profile(conn, item, apply) for item in artists]
        event_results = [upsert_live_event(conn, item, profile_by_key, apply) for item in live_events]
        if apply:
            conn.commit()

    print(f"{'Imported' if apply else 'Dry run'}: {len(results)} profiles, {len(event_results)} live events")
    for result in results:
        print(result)
    for result in event_results:
        print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
