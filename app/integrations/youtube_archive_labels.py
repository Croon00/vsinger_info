"""Fill missing archive labels once per distinct Japanese title or artist.

Run: python -m app.integrations.youtube_archive_labels
"""
import asyncio
import re
import unicodedata

from app.core.db import get_connection
from app.integrations.spotify_title_translation import (
    JAPANESE_TITLE_PATTERN, translate_japanese_titles, translate_japanese_artist_names,
)
from app.integrations.karaoke_lookup import split_song_credit


def clean_label(value: str) -> str:
    value = unicodedata.normalize('NFKC', value).strip()
    return re.sub(r'^(?:#\s*)?\d+\s*(?:[.．:：\-—)]\s*|\s+)', '', value).strip(' /／')


def label_key(value: str) -> str:
    return re.sub(r'[\W_]', '', clean_label(value).casefold())


def restore_setlist_credits(archive_ids: list[int] | None = None) -> int:
    """Recover explicitly credited artists from the saved source setlists."""
    with get_connection() as conn:
        archives = conn.execute(
            """SELECT id, setlist FROM youtube_live_archives
               WHERE (%s::integer[] IS NULL OR id = ANY(%s))""",
            (archive_ids, archive_ids),
        ).fetchall()
        performances = conn.execute(
            """SELECT id, archive_id, timestamp_text, song_title
               FROM youtube_song_performances
               WHERE NULLIF(TRIM(original_artist), '') IS NULL
                 AND (%s::integer[] IS NULL OR archive_id = ANY(%s))""",
            (archive_ids, archive_ids),
        ).fetchall()
        credits = {}
        for archive in archives:
            for entry in archive['setlist'] or []:
                title, artist = split_song_credit(entry.get('title', ''))
                if artist:
                    credits[(archive['id'], entry.get('timestamp'), label_key(title))] = artist
        updates = [(row['id'], credits[key]) for row in performances
                   if (key := (row['archive_id'], row['timestamp_text'], label_key(row['song_title']))) in credits]
        if updates:
            conn.execute("""UPDATE youtube_song_performances p SET original_artist = source.artist
                FROM unnest(%s::integer[], %s::text[]) AS source(id, artist)
                WHERE p.id = source.id AND NULLIF(TRIM(p.original_artist), '') IS NULL""",
                ([row_id for row_id, _ in updates], [artist for _, artist in updates]))
        conn.commit()
    return len(updates)


async def refresh_archive_labels(
    only_source: str | None = None,
    archive_ids: list[int] | None = None,
) -> dict[str, int]:
    """Fill missing Korean labels globally or for the supplied archive IDs."""
    print(f"Restored {restore_setlist_credits(archive_ids)} original artist credits", flush=True)
    result = {"translated_values": 0, "failed_batches": 0, "untranslated_values": 0}
    for source, target, translate in (
        ("song_title", "song_title_ko", translate_japanese_titles),
        ("original_artist", "original_artist_ko", translate_japanese_artist_names),
    ):
        if only_source is not None and source != only_source:
            continue
        # Column names are fixed above, never supplied by callers.
        with get_connection() as conn:
            conn.execute(f"""UPDATE youtube_song_performances p SET {target} = known.label
                FROM (SELECT {source} AS original, MIN({target}) AS label
                      FROM youtube_song_performances WHERE NULLIF(TRIM({target}), '') IS NOT NULL
                      GROUP BY {source}) known
                WHERE p.{source} = known.original AND NULLIF(TRIM(p.{target}), '') IS NULL
                  AND (%s::integer[] IS NULL OR p.archive_id = ANY(%s))""",
                (archive_ids, archive_ids),
            )
            known = conn.execute(f"SELECT {source} AS original, {target} AS label FROM youtube_song_performances WHERE NULLIF(TRIM({target}), '') IS NOT NULL").fetchall()
            if source == 'song_title':
                known += conn.execute("SELECT original_title AS original, title_ko AS label FROM songs WHERE title_ko IS NOT NULL UNION SELECT original_title AS original, title_ko AS label FROM spotify_track_title_translations WHERE title_ko IS NOT NULL").fetchall()
            rows = conn.execute(f"""SELECT p.{source} AS original, COUNT(*) AS uses
                FROM youtube_song_performances p JOIN youtube_live_archives y ON y.id = p.archive_id
                WHERE NULLIF(TRIM(p.{target}), '') IS NULL AND p.{source} IS NOT NULL
                  AND (y.duration_seconds IS NULL OR y.duration_seconds > 420)
                  AND (%s::integer[] IS NULL OR p.archive_id = ANY(%s))
                GROUP BY p.{source} ORDER BY uses DESC""",
                (archive_ids, archive_ids),
            ).fetchall()
            conn.commit()
        cached = {label_key(row['original']): clean_label(row['label']) for row in known if row['original'] and row['label']}
        groups = {}
        cached_updates = []
        with get_connection() as conn:
            for row in rows:
                original = row['original']
                if not JAPANESE_TITLE_PATTERN.search(original):
                    continue
                key = label_key(original)
                if key in cached:
                    cached_updates.append((original, cached[key]))
                else:
                    groups.setdefault(key, []).append(original)
            if cached_updates:
                conn.execute(f"""UPDATE youtube_song_performances p SET {target} = known.label
                    FROM unnest(%s::text[], %s::text[]) AS known(original, label)
                    WHERE p.{source} = known.original AND NULLIF(TRIM(p.{target}), '') IS NULL
                      AND (%s::integer[] IS NULL OR p.archive_id = ANY(%s))""",
                    (
                        [original for original, _ in cached_updates],
                        [label for _, label in cached_updates],
                        archive_ids,
                        archive_ids,
                    ),
                )
            conn.commit()
        values = list(groups.values())
        print(f"{source}: {len(values)} normalized values to translate", flush=True)
        semaphore = asyncio.Semaphore(6)

        async def batch(start: int) -> None:
            async with semaphore:
                aliases = {str(i): value for i, value in enumerate(values[start:start + 25])}
                originals = {key: clean_label(value[0]) for key, value in aliases.items()}
                try:
                    labels = await translate(list(originals.items()))
                    with get_connection() as conn:
                        for key, label in labels.items():
                            if key not in originals or not label.strip():
                                continue
                            conn.execute(f"""UPDATE youtube_song_performances SET {target} = %s
                                WHERE {source} = ANY(%s) AND NULLIF(TRIM({target}), '') IS NULL
                                  AND (%s::integer[] IS NULL OR archive_id = ANY(%s))""",
                                (label, aliases[key], archive_ids, archive_ids))
                        conn.commit()
                    result["translated_values"] += len(labels)
                    result["untranslated_values"] += len(originals) - len(labels)
                    print(f"{source}: batch {start // 25 + 1}/{(len(values) + 24) // 25} saved", flush=True)
                except Exception as exc:
                    result["failed_batches"] += 1
                    print(f"{source}: batch failed ({type(exc).__name__})", flush=True)

        await asyncio.gather(*(batch(start) for start in range(0, len(values), 25)))
    return result


if __name__ == "__main__":
    print(asyncio.run(refresh_archive_labels()))
