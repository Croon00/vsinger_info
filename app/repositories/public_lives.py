"""Persist verified public event-page observations in the catalog concert tables."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone

from app.db.catalog_session import catalog_runtime_session
from app.integrations.live_site_pages import PublicLive

_CHANNEL_OWNER = {
    "virtual_kaf": ("花譜", "KAF"),
    "RIM_virtual": ("理芽", "RIM"),
    "KOKO__virtual": ("幸祜", "KOKO"),
    "harusaruhi": ("春猿火", "Harusaruhi"),
    "isekaijoucho": ("ヰ世界情緒", "Isekaijoucho"),
}


def _artist_rows(conn) -> list[dict]:
    return [dict(row) for row in conn.exec_driver_sql("""
        SELECT a.id, a.name_native, a.name_ko, a.name_latin,
               COALESCE(array_agg(DISTINCT aa.alias) FILTER (WHERE aa.alias IS NOT NULL), '{}') aliases
        FROM artists a LEFT JOIN artist_aliases aa ON aa.artist_id = a.id
        WHERE a.archived_at IS NULL AND a.show_in_catalog
        GROUP BY a.id
    """).mappings().all()]


def _contains_alias(text: str, alias: str) -> bool:
    alias = alias.strip()
    if len(alias) < 2:
        return False
    if re.fullmatch(r"[A-Za-z0-9 ]+", alias):
        return bool(re.search(rf"(?<![A-Za-z0-9]){re.escape(alias)}(?![A-Za-z0-9])", text, re.I))
    return alias.casefold() in text.casefold()


def artist_ids_for_event(rows: list[dict], channel: str, event: PublicLive) -> list[int]:
    owner_names = _CHANNEL_OWNER.get(channel, ())
    owner_ids = [
        row["id"] for row in rows
        if any(_contains_alias(" ".join(filter(None, (row["name_native"], row["name_ko"], row["name_latin"], *row["aliases"]))), name)
               for name in owner_names)
    ]
    # For agency-wide channels, use the event title and its event-specific excerpt.
    # Never match against the channel page, which contains unrelated recommendations.
    text = f"{event.title} {event.excerpt}"
    matches = [
        row["id"] for row in rows
        if any(_contains_alias(text, name) for name in
               (row["name_native"], row["name_ko"], row["name_latin"], *row["aliases"]) if name)
    ]
    return list(dict.fromkeys([*owner_ids, *matches]))


def save_public_live(event: PublicLive, artist_ids: list[int]) -> bool:
    """Insert once by canonical detail URL; update changed facts without repeat alerts."""
    if not artist_ids:
        return False
    facts = {
        "title": event.title,
        "event_date": event.event_date.isoformat(),
        "starts_at": event.starts_at.isoformat() if event.starts_at else None,
        "event_format": event.event_format,
        "venue": event.venue,
        "source_url": event.source_url,
        "ticket_url": event.ticket_url,
    }
    content = json.dumps(facts, ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    status = "completed" if event.event_date < datetime.now(timezone(timedelta(hours=9))).date() else "scheduled"
    with catalog_runtime_session() as session:
        conn = session.connection()
        # Handles multiple Railway replicas and repeated channel appearances.
        conn.exec_driver_sql("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (event.source_url,))
        current = conn.exec_driver_sql("""
            SELECT c.id, c.status, d.content_hash, d.source_metadata->>'collector' AS collector FROM concerts c
            JOIN source_documents d ON d.id = c.source_document_id
            WHERE d.source_url = %s AND c.archived_at IS NULL
            ORDER BY c.id LIMIT 1
        """, (event.source_url,)).mappings().first()
        if current and current["collector"] != "public-live-sites":
            # A human-curated concert may cite the same page. Do not overwrite it.
            return False
        unchanged = bool(current and current["content_hash"] == digest)
        document_id = None if unchanged else conn.exec_driver_sql("""
            INSERT INTO source_documents
              (source_kind, source_url, external_id, captured_at, content_text, content_hash, source_metadata)
            VALUES ('official_page', %s, %s, %s, %s, %s, %s::jsonb)
            RETURNING id
        """, (
            event.source_url, event.source_url.rstrip("/").rsplit("/", 1)[-1], datetime.now(timezone.utc),
            event.excerpt or event.title, digest, json.dumps({"collector": "public-live-sites"}),
        )).mappings().one()["id"]
        values = (
            event.title, event.event_format, event.event_date, event.starts_at,
            "Asia/Tokyo" if event.starts_at else None,
            "datetime" if event.starts_at else "date", event.venue, document_id,
        )
        if unchanged:
            concert_id = current["id"]
            if current["status"] != status:
                conn.exec_driver_sql("UPDATE concerts SET status=%s WHERE id=%s", (status, concert_id))
        elif current:
            concert_id = current["id"]
            conn.exec_driver_sql("""
                UPDATE concerts SET title=%s, event_format=%s, event_date=%s,
                    starts_at=%s, timezone_name=%s, time_precision=%s, venue=%s,
                    source_document_id=%s, status=%s
                WHERE id=%s
            """, (*values, status, concert_id))
        else:
            concert_id = conn.exec_driver_sql("""
                INSERT INTO concerts
                  (title,event_format,event_date,starts_at,timezone_name,time_precision,venue,
                   source_document_id,status)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
            """, (*values, status)).mappings().one()["id"]
        for position, artist_id in enumerate(artist_ids):
            conn.exec_driver_sql("""
                INSERT INTO concert_artists (concert_id,artist_id,position)
                VALUES (%s,%s,%s) ON CONFLICT (concert_id,artist_id) DO NOTHING
            """, (concert_id, artist_id, position))
        conn.exec_driver_sql("""
            DELETE FROM concert_artists
            WHERE concert_id=%s AND artist_id <> ALL(%s::integer[])
        """, (concert_id, artist_ids))
        if event.ticket_url:
            ticket = conn.exec_driver_sql("""
                SELECT id FROM concert_ticket_windows
                WHERE concert_id=%s AND label='Official ticket page' ORDER BY id LIMIT 1
            """, (concert_id,)).mappings().first()
            if ticket:
                conn.exec_driver_sql("UPDATE concert_ticket_windows SET url=%s WHERE id=%s", (event.ticket_url, ticket["id"]))
            else:
                conn.exec_driver_sql("""
                    INSERT INTO concert_ticket_windows (concert_id,label,url)
                    VALUES (%s,'Official ticket page',%s)
                """, (concert_id, event.ticket_url))
        return current is None


def catalog_artist_rows() -> list[dict]:
    with catalog_runtime_session() as session:
        return _artist_rows(session.connection())
