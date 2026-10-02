"""Link Spotify recordings to songs through ISRC -> MusicBrainz work (plan step 5, Spotify ISRC).

``export`` (READ ONLY on the catalog) looks every active recording's ISRC up in
MusicBrainz (recording search ``isrc:``, 25 ISRCs a request), then the works those
recordings perform (work search ``rid:``, 20 recordings a request), and writes
migrations/catalog/recording-song-links-N.json plus the review file
db-migration/reports/recording-songs/review-N.md. MusicBrainz responses are cached per
ISRC / recording in the same git-ignored directory, so a re-export sends no requests.

Per recording, in this order:

  1. its MusicBrainz work is stored on a song (song_external_ids musicbrainz_work)
     -> link to that song (``mb_work``). A work in manual ``split_works`` links only
     when the recording shares an artist with the song.
  2. otherwise an active song whose title or alias equals the recording title (version
     tail such as ``- Live`` / ``(Instrumental)`` / ``-TV ver.-`` removed) or the work
     title, AND that shares an artist with the recording (``title_artist``) or with the
     work's composer/lyricist (``title_writer``), exactly one of them -> link; the work
     ID is attached to that song when it has none.
  3. a same-title song without a shared artist (cover or homonym), several candidate
     songs, or several works -> review, not linked by default.
  4. no candidate -> a NEW song, grouped by work, else by title with overlapping
     artists. Only recordings credited to a catalog-visible artist create songs;
     uncredited recordings (other artists' tracks on our artists' own albums) only take
     step 1. A group made only of covers (``Cover`` / ``カバー`` / ``原曲`` in the title,
     or MusicBrainz marks the performance as a cover) creates no song -- the original
     artist is unknown here -- and goes to review. Stage talk (``MC1``) is skipped.

A MusicBrainz work is used only when its title matches the recording title (or the
title of the song already storing it); MusicBrainz sometimes links the wrong work.
Title comparison drops punctuation and symbols (``tight``) and never stores the result.

Artist spellings for writers are native names and aliases only (a Latin-name match put
ハチ on HACHI songs before).

``review-import`` folds the edited review file back into the decision file (no DB).
``apply`` dry-runs; ``apply --apply`` writes new songs, their credits and work IDs,
attached work IDs and recordings.song_id in ONE transaction with a catalog_imports
receipt and catalog_changes rows. Rows changed since export abort the whole run; a
second apply is ``already_committed``. Titles, credits and ISRCs of recordings are
never changed. MusicBrainz core data is CC0.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
import unicodedata
import uuid
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.integrations.song_catalogs import (MBID, MusicBrainzClient, recording_from_musicbrainz,  # noqa: E402
                                            work_from_musicbrainz)
from app.services.song_candidates import loose  # noqa: E402

POLICY = "recording-song-links-v1"
NAMESPACE = uuid.UUID("4c1f7a52-9b3e-4d80-8e21-6a5d0c9b7f13")
LOCK_ID = 731064951
REPORTS = ROOT / "db-migration" / "reports" / "recording-songs"
DECISIONS = ROOT / "migrations" / "catalog" / "recording-song-links-{n}.json"
MANUAL_FILES = [ROOT / "migrations" / "catalog" / "song-master-manual-2.json"]
ISRC_BATCH, RID_BATCH, MB_LIMIT = 25, 20, 100
LANGUAGES = {"jpn": "ja", "eng": "en"}
PENDING_ONLY = ("forms", "work", "writer_ids", "cover", "hints")

_VERSION_WORDS = re.compile(
    r"(?i)(?:\b(?:ver(?:sion)?|mix|remix|edit|instrumental|inst|off\s*vocal|acoustic|live\d*|remaster(?:ed)?|tv|size|"
    r"short|full|cover|feat|ft|prod|a\s*cappella|acapella|piano|orchestra|arrange(?:d)?|karaoke|demo|intro|"
    r"self|first\s*take|unplugged|re-?recorded?|[+-]?\d*\s*key)\b|ライブ|弾き語り|アコースティック|カバー|リミックス|インスト|バージョン|原曲)")
_PAREN_TAIL = re.compile(r"\s*[\(\[（【［]([^\(\)\[\]（）【】［］]*)[\)\]）】］]\s*$")
_DASH_TAIL = re.compile(r"\s+[-‐–—－]\s+([^-‐–—－]+)$")
_WRAP_TAIL = re.compile(r"\s*[-‐–—~〜～－]([^-‐–—~〜～－]+)[-‐–—~〜～－]\s*$")
_AT_TAIL = re.compile(r"(?i)\s+at\s+(\S.*)$")
_KEY_TAIL = re.compile(r"(?i)\s*([+\-－]\s*\d+\s*key)\s*$")
_FEAT_TAIL = re.compile(r"(?i)\s+(?:feat\.?|ft\.)\s*\S.*$")
_COVER = re.compile(r"(?i)\bcover\b|カバー|歌ってみた|原曲")
_SEPARATOR = re.compile(r"\s+[-‐–—－]\s+")
# Stage talk and album interludes are tracks, not songs.
_NOT_SONG = re.compile(r"(?i)^(?:mc|talk|トーク|intro|outro|interlude|overture|se)\s*\d*$")

_spec = importlib.util.spec_from_file_location("migrate_catalog", ROOT / "scripts" / "migrate_catalog.py")
migrate_catalog = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migrate_catalog)


def rows(conn, query, params=None):
    return conn.cursor(row_factory=dict_row).execute(query, params)


def base_title(title: str) -> str:
    """Recording title without trailing version labels (``X - Live``, ``X (Instrumental)``, ``X -TV ver.-``,
    ``X at <event> LIVE``)."""
    text = title.strip()
    while True:
        before = text
        for pattern in (_PAREN_TAIL, _DASH_TAIL, _WRAP_TAIL, _AT_TAIL, _KEY_TAIL):
            match = pattern.search(text)
            if match and _VERSION_WORDS.search(match.group(1)) and text[:match.start()].strip():
                text = text[:match.start()].strip()
        match = _FEAT_TAIL.search(text)
        if match and text[:match.start()].strip():
            text = text[:match.start()].strip()
        if text == before:
            return text


def tight(value: str | None) -> str:
    """``loose`` without punctuation and symbols (``命に嫌われている。`` meets ``命に嫌われている``);
    falls back to ``loose`` for a title made only of symbols. Comparison only, never stored."""
    text = loose(value)
    stripped = "".join(c for c in text if not unicodedata.category(c).startswith(("P", "S")))
    return stripped or text


def title_forms(title: str) -> set[str]:
    """Comparison forms of a recording or work title: the version-less title and, for
    ``X - <event>``, the part before the first spaced dash."""
    base = base_title(title)
    forms = {tight(base)}
    parts = _SEPARATOR.split(base, maxsplit=1)
    if len(parts) == 2 and parts[0].strip():
        forms.add(tight(parts[0]))
    return {f for f in forms if f}


def is_cover(title: str) -> bool:
    return bool(_COVER.search(title))


# --------------------------------------------------------------------------- state

def load_state(conn) -> dict:
    identity = rows(conn, "SELECT id::text AS id, schema_version FROM catalog_instance").fetchone()
    artists = {r["id"]: {**r, "spellings": set()} for r in rows(conn, """
        SELECT id, name_native, show_in_catalog FROM artists WHERE archived_at IS NULL""")}
    for a in artists.values():
        a["spellings"].add(loose(a["name_native"]))
    for r in rows(conn, "SELECT artist_id, alias FROM artist_aliases"):
        if r["artist_id"] in artists:
            artists[r["artist_id"]]["spellings"].add(loose(r["alias"]))
    songs = {r["id"]: {**r, "artists": [], "aliases": [], "works": []} for r in rows(conn, """
        SELECT s.id, s.version, s.title_native FROM songs s WHERE s.archived_at IS NULL
          AND NOT EXISTS (SELECT 1 FROM song_merges m WHERE m.source_song_id=s.id)""")}
    for r in rows(conn, "SELECT song_id, artist_id FROM song_artists ORDER BY song_id, position, id"):
        if r["song_id"] in songs:
            songs[r["song_id"]]["artists"].append(r["artist_id"])
    for r in rows(conn, "SELECT song_id, alias FROM song_aliases"):
        if r["song_id"] in songs:
            songs[r["song_id"]]["aliases"].append(r["alias"])
    stored_works = {}
    for r in rows(conn, "SELECT song_id, external_id FROM song_external_ids WHERE provider='musicbrainz_work'"):
        stored_works[r["external_id"]] = r["song_id"]
        if r["song_id"] in songs:
            songs[r["song_id"]]["works"].append(r["external_id"])
    recordings = {r["id"]: {**r, "artists": []} for r in rows(conn, """
        SELECT r.id, r.version, r.title_native, r.song_id,
          (SELECT e.external_id FROM recording_external_ids e WHERE e.recording_id=r.id AND e.platform='isrc') isrc
        FROM recordings r WHERE r.archived_at IS NULL""")}
    for r in rows(conn, "SELECT recording_id, artist_id FROM recording_artists ORDER BY recording_id, position, id"):
        if r["recording_id"] in recordings:
            recordings[r["recording_id"]]["artists"].append(r["artist_id"])
    return {"catalog_instance_id": identity["id"], "artists": artists, "songs": songs,
            "stored_works": stored_works, "recordings": recordings}


# --------------------------------------------------------------------------- MusicBrainz

class Lookups:
    """ISRC -> MusicBrainz recordings -> works, cached per ISRC and per recording ID."""

    def __init__(self, cache_path: Path, client: MusicBrainzClient | None = None):
        self.cache_path = cache_path
        self.cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
        self.cache.setdefault("isrc", {})
        self.cache.setdefault("rid", {})
        self.client = client

    @property
    def requests(self) -> int:
        return self.client.http.requests if self.client else 0

    def _mb(self) -> MusicBrainzClient:
        if self.client is None:
            self.client = MusicBrainzClient()
        return self.client

    def _search(self, path: str, field: str, ids: list[str], items_key: str) -> list[dict]:
        data = self._mb().http.get(path, {"query": " OR ".join(f"{field}:{i}" for i in ids),
                                          "limit": MB_LIMIT, "fmt": "json"})
        items = data.get(items_key)
        if not isinstance(items, list):
            raise RuntimeError(f"malformed MusicBrainz {items_key} response")
        if int(data.get("count") or 0) > len(items):
            if len(ids) == 1:
                raise RuntimeError(f"MusicBrainz returned more than {MB_LIMIT} {items_key} for {ids[0]}")
            half = len(ids) // 2
            return self._search(path, field, ids[:half], items_key) + self._search(path, field, ids[half:], items_key)
        return items

    def isrc_recordings(self, isrcs: list[str]) -> dict[str, list[dict]]:
        missing = sorted({i for i in isrcs if i not in self.cache["isrc"]})
        for start in range(0, len(missing), ISRC_BATCH):
            chunk = missing[start:start + ISRC_BATCH]
            found = defaultdict(list)
            for item in self._search("/ws/2/recording", "isrc", chunk, "recordings"):
                try:
                    recording = recording_from_musicbrainz(item)
                except ValueError:
                    continue
                for isrc in item.get("isrcs") or []:
                    if isrc in chunk:
                        found[isrc].append({"id": recording.external_id, "title": recording.title,
                                            "credit": recording.credit})
            for isrc in chunk:
                self.cache["isrc"][isrc] = found.get(isrc, [])
            self.save()
        return {i: self.cache["isrc"].get(i, []) for i in isrcs}

    def recording_works(self, rids: list[str]) -> dict[str, list[dict]]:
        missing = sorted({r for r in rids if r not in self.cache["rid"] and re.fullmatch(MBID, r)})
        for start in range(0, len(missing), RID_BATCH):
            chunk = missing[start:start + RID_BATCH]
            found = defaultdict(list)
            for item in self._search("/ws/2/work", "rid", chunk, "works"):
                try:
                    work = work_from_musicbrainz(item)
                except ValueError:
                    continue
                entry = {"id": work.external_id, "title": work.title, "language": work.language,
                         "names": sorted({n.value for n in work.names}),
                         "writers": [{"name": a.name, "role": a.role} for a in work.artists]}
                for rid in set(work.recording_ids) & set(chunk):
                    found[rid].append(entry)
            for rid in chunk:
                self.cache["rid"][rid] = found.get(rid, [])
            self.save()
        return {r: self.cache["rid"].get(r, []) for r in rids}

    def recording_is_cover(self, rid: str) -> bool:
        """Whether a MusicBrainz recording performs a work as a cover (performance relation
        attribute ``cover``). Search results omit relation attributes, so this is a lookup."""
        cache = self.cache.setdefault("cover", {})
        if rid not in cache:
            data = self._mb().http.get(f"/ws/2/recording/{rid}", {"inc": "work-rels", "fmt": "json"})
            cache[rid] = any(r.get("type") == "performance" and "cover" in (r.get("attributes") or [])
                             for r in data.get("relations") or [] if isinstance(r, dict))
            self.save()
        return cache[rid]

    def save(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.cache_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.cache, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.cache_path)

    def close(self) -> None:
        if self.client:
            self.client.close()


def lookup_all(state: dict, lookups: Lookups) -> dict[int, dict]:
    """recording id -> {"mb_recordings": [...], "works": [...]} (works deduplicated by id)."""
    isrcs = sorted({r["isrc"] for r in state["recordings"].values() if r["isrc"]})
    by_isrc = lookups.isrc_recordings(isrcs)
    rids = sorted({m["id"] for v in by_isrc.values() for m in v})
    by_rid = lookups.recording_works(rids)
    result = {}
    for rec_id, rec in state["recordings"].items():
        mb = by_isrc.get(rec["isrc"], []) if rec["isrc"] else []
        works = {}
        for m in mb:
            for w in by_rid.get(m["id"], []):
                works.setdefault(w["id"], w)
        result[rec_id] = {"mb_recordings": [m["id"] for m in mb], "works": list(works.values())}
    return result


# --------------------------------------------------------------------------- plan

def split_works(manual_files=MANUAL_FILES) -> set[str]:
    found = set()
    for path in manual_files:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            found |= {w["external_id"] for w in data.get("split_works", []) if w.get("provider") == "musicbrainz_work"}
    return found


class _Groups:
    """Union-find over new-song groups."""

    def __init__(self):
        self.parent = {}

    def find(self, x):
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        self.parent[self.find(a)] = self.find(b)


def plan(state: dict, found: dict[int, dict], splits: set[str] | None = None,
         covers: dict[int, bool] | None = None) -> dict:
    """Pure: turn the catalog state and MusicBrainz lookups into a decision file.

    ``covers`` marks recordings MusicBrainz records as a cover performance (looked up only
    for recordings that would otherwise create a song, see ``export``)."""
    splits, covers = splits or set(), covers or {}
    songs, artists = state["songs"], state["artists"]
    song_forms = {}
    by_title = defaultdict(set)
    for song_id, song in songs.items():
        forms = {tight(v) for v in [song["title_native"], *song["aliases"]]} | \
                {tight(base_title(v)) for v in [song["title_native"], *song["aliases"]]}
        song_forms[song_id] = {f for f in forms if f}
        for f in song_forms[song_id]:
            by_title[f].add(song_id)
    by_spelling = defaultdict(set)
    for artist_id, a in artists.items():
        for s in a["spellings"]:
            if s:
                by_spelling[s].add(artist_id)
    work_song = {w: s for w, s in state["stored_works"].items() if s in songs}

    def writer_ids(work) -> list[int]:
        ids = []
        for writer in (work or {}).get("writers", []):
            match = by_spelling.get(loose(writer["name"]), set())
            if len(match) == 1 and next(iter(match)) not in ids:
                ids.append(next(iter(match)))
        return ids

    def work_forms(work) -> set[str]:
        return set().union(*(title_forms(n) for n in [work["title"], *work["names"]]))

    def song_brief(song_id):
        song = songs[song_id]
        return {"song_id": song_id, "title": song["title_native"],
                "artists": [artists[a]["name_native"] for a in song["artists"] if a in artists]}

    links, review, skipped, pending_new = [], [], [], []
    untrusted = 0
    for rec_id in sorted(state["recordings"]):
        rec = state["recordings"][rec_id]
        if rec["song_id"] is not None:
            continue
        info = found.get(rec_id, {"mb_recordings": [], "works": []})
        rec_artists = set(rec["artists"])
        forms = title_forms(rec["title_native"])
        cover = is_cover(rec["title_native"]) or covers.get(rec_id, False)
        visible = any(artists[a]["show_in_catalog"] for a in rec["artists"] if a in artists)
        # A work is trusted for this recording only when a title matches: the work's own, or
        # the title of the song that already stores it. MusicBrainz sometimes links a
        # recording to the wrong work (a B-side, a medley part).
        trusted = [w for w in info["works"]
                   if forms & work_forms(w) or (w["id"] in work_song and forms & song_forms[work_song[w["id"]]])]
        untrusted += len(trusted) < len(info["works"])
        entry = {"recording_id": rec_id, "version": rec["version"], "title": rec["title_native"], "isrc": rec["isrc"],
                 "artist_ids": rec["artists"],
                 "artists": [artists[a]["name_native"] for a in rec["artists"] if a in artists],
                 "mb_recordings": info["mb_recordings"],
                 "works": [{"id": w["id"], "title": w["title"], "trusted": w in trusted,
                            "writers": sorted({x["name"] for x in w["writers"]})} for w in info["works"]]}
        if len(trusted) > 1:
            targets = {work_song.get(w["id"]) for w in trusted}
            if len(targets) == 1 and None not in targets:
                links.append({**entry, "song_id": targets.pop(), "basis": "mb_work", "attach_work": None})
            elif rec_artists and visible:
                review.append({**entry, "reason": "several_works",
                               "candidates": [song_brief(s) for s in sorted(t for t in targets if t)]})
            else:
                skipped.append({"recording_id": rec_id, "reason": "uncredited" if not rec_artists else "hidden_artist"})
            continue
        work = trusted[0] if trusted else None
        if work and work["id"] in work_song:
            song_id = work_song[work["id"]]
            if work["id"] in splits and not set(songs[song_id]["artists"]) & rec_artists:
                review.append({**entry, "reason": "split_work", "candidates": [song_brief(song_id)]})
            else:
                links.append({**entry, "song_id": song_id, "basis": "mb_work", "attach_work": None})
            continue
        if not rec_artists:
            skipped.append({"recording_id": rec_id, "reason": "uncredited"})
            continue
        candidates = set().union(*(by_title.get(f, set()) for f in forms | (work_forms(work) if work else set())))
        writers = set(writer_ids(work))
        by_artist = {s for s in candidates if set(songs[s]["artists"]) & rec_artists}
        by_writer = {s for s in candidates if set(songs[s]["artists"]) & writers}
        strong = by_artist | by_writer
        basis = None
        if len(strong) == 1:
            song_id = next(iter(strong))
            basis = "title_artist" if song_id in by_artist else "title_writer"
        elif not strong and cover and len(candidates) == 1:
            # "X - Cover": the only song titled X is the covered original.
            song_id, basis = next(iter(candidates)), "cover_title"
        if basis:
            if work and songs[song_id]["works"]:
                review.append({**entry, "reason": "song_has_other_work", "candidates": [song_brief(song_id)]})
            else:
                links.append({**entry, "song_id": song_id, "basis": basis, "attach_work": work["id"] if work else None})
        elif not visible:
            # Artists hidden from the catalog only take unambiguous links to existing songs.
            skipped.append({"recording_id": rec_id, "reason": "hidden_artist"})
        elif strong:
            review.append({**entry, "reason": "several_songs", "candidates": [song_brief(s) for s in sorted(strong)]})
        elif candidates:
            review.append({**entry, "reason": "title_only", "candidates": [song_brief(s) for s in sorted(candidates)]})
        elif not forms:
            skipped.append({"recording_id": rec_id, "reason": "empty_title"})
        elif _NOT_SONG.match(base_title(rec["title_native"])):
            skipped.append({"recording_id": rec_id, "reason": "not_song"})
        else:
            # Songs titled like an untrusted work: shown with a cover so the reviewer can pick one.
            hints = set().union(*(by_title.get(f, set()) for w in info["works"] if w not in trusted for f in work_forms(w)))
            pending_new.append({**entry, "forms": forms, "work": work, "writer_ids": writer_ids(work), "cover": cover,
                                "hints": sorted(hints)})

    # A work may be attached to one song only, and a song gets at most one attached work.
    attach = defaultdict(set)
    for link in links:
        if link["attach_work"]:
            attach[link["attach_work"]].add(link["song_id"])
    per_song = defaultdict(set)
    for work_id, song_ids in attach.items():
        for s in song_ids:
            per_song[s].add(work_id)
    for link in links:
        w = link["attach_work"]
        if w and (len(attach[w]) > 1 or len(per_song[link["song_id"]]) > 1):
            link["attach_work"] = None
            link["attach_conflict"] = True
    attached = {link["attach_work"]: link["song_id"] for link in links if link["attach_work"]}
    # Other versions of an attached work (a title the song does not carry) follow it.
    still_new = []
    for p in pending_new:
        if p["work"] and p["work"]["id"] in attached:
            links.append({k: v for k, v in p.items() if k not in PENDING_ONLY}
                         | {"song_id": attached[p["work"]["id"]], "basis": "mb_work_attached", "attach_work": None})
        else:
            still_new.append(p)
    pending_new = still_new

    # One work -> one song; otherwise group by title when the artists overlap.
    groups = _Groups()
    by_key = defaultdict(list)
    for n, p in enumerate(pending_new):
        groups.find(n)
        if p["work"]:
            by_key[("work", p["work"]["id"])].append(n)
        for form in p["forms"]:
            by_key[("title", form)].append(n)
    for (kind, _), members in by_key.items():
        for i, a in enumerate(members):
            for b in members[i + 1:]:
                if kind == "work" or set(pending_new[a]["artist_ids"]) & set(pending_new[b]["artist_ids"]):
                    groups.union(a, b)
    # A version recording (``X - Live``) with no work by another singer joins the only
    # same-title group that has a work: a live cover. Its singer is not credited.
    def rebuild():
        found_groups = defaultdict(list)
        for n in range(len(pending_new)):
            found_groups[groups.find(n)].append(n)
        return found_groups

    grouped_ids = rebuild()
    by_form = defaultdict(set)
    for root, members in grouped_ids.items():
        for n in members:
            for form in pending_new[n]["forms"]:
                by_form[form].add(root)
    for form, roots in sorted(by_form.items()):
        roots = {groups.find(r) for r in roots}
        work_roots = {r for r in roots if any(pending_new[n]["work"] for n in grouped_ids.get(r, []))}
        if len(work_roots) != 1:
            continue
        target = next(iter(work_roots))
        changed = False
        for root in roots - work_roots:
            members = grouped_ids.get(root, [])
            if members and all(not pending_new[n]["work"] and pending_new[n]["title"] != base_title(pending_new[n]["title"])
                               for n in members):
                for n in members:
                    pending_new[n]["cover"] = True
                groups.union(root, target)
                changed = True
        if changed:
            grouped_ids = rebuild()
    grouped = {root: [pending_new[n] for n in members] for root, members in grouped_ids.items()}
    title_groups = defaultdict(set)
    for root, members in grouped.items():
        for p in members:
            for form in p["forms"]:
                title_groups[form].add(root)

    new_songs = []
    for root, members in sorted(grouped.items(), key=lambda item: min(p["recording_id"] for p in item[1])):
        same_title = any(len(title_groups[f]) > 1 for p in members for f in p["forms"])
        originals = [p for p in members if not p["cover"]]
        if not originals:
            # Only cover recordings: the original artist is unknown here, so no song is made
            # in the singer's name.
            review.extend({**{k: v for k, v in p.items() if k not in PENDING_ONLY},
                           "reason": "cover_unknown", "candidates": [song_brief(s) for s in p["hints"]]} for p in members)
            continue
        works = {p["work"]["id"]: p["work"] for p in members if p["work"]}
        work_titles = {tight(base_title(n)) for w in works.values() for n in [w["title"], *w["names"]]}
        plain = [p["title"] for p in originals if p["title"] == base_title(p["title"])
                 and (not works or tight(p["title"]) in work_titles)]
        if plain:
            title = Counter(plain).most_common(1)[0][0]
        elif len(works) == 1:
            title = base_title(next(iter(works.values()))["title"])
        else:
            title = Counter(base_title(p["title"]) for p in originals).most_common(1)[0][0]
        counts = Counter(a for p in originals for a in p["artist_ids"])
        ordered = [a for p in members for a in p["writer_ids"]]
        credit = list(dict.fromkeys(ordered + [a for a, _ in sorted(counts.items(), key=lambda x: (-x[1], x[0]))]))
        languages = {LANGUAGES.get(w["language"]) for w in works.values()}
        new_songs.append({
            "ref": f"n{min(p['recording_id'] for p in members)}", "title_native": title,
            "language_code": languages.pop() if len(languages) == 1 else None,
            "artist_ids": credit, "artists": [artists[a]["name_native"] for a in credit],
            "external_ids": [{"provider": "musicbrainz_work", "external_id": w} for w in sorted(works)],
            "work_titles": sorted({w["title"] for w in works.values()}),
            "writers": sorted({x["name"] for w in works.values() for x in w["writers"]}),
            "recordings": [{"recording_id": p["recording_id"], "version": p["version"], "title": p["title"],
                            "isrc": p["isrc"]} for p in sorted(members, key=lambda p: p["recording_id"])],
            "flags": (["several_works"] if len(works) > 1 else []) + (["has_cover"] if len(originals) < len(members) else []) +
                     (["same_title"] if same_title else [])})
    links.sort(key=lambda link: link["recording_id"])
    review.sort(key=lambda r: r["recording_id"])

    summary = {
        "recordings": len(state["recordings"]),
        "already_linked": sum(1 for r in state["recordings"].values() if r["song_id"] is not None),
        "with_mb_recording": sum(1 for v in found.values() if v["mb_recordings"]),
        "with_mb_work": sum(1 for v in found.values() if v["works"]),
        "untrusted_work_recordings": untrusted,
        "links": len(links), "links_by_basis": dict(Counter(link["basis"] for link in links)),
        "linked_songs": len({link["song_id"] for link in links}),
        "attach_works": len({link["attach_work"] for link in links if link["attach_work"]}),
        "new_songs": len(new_songs), "new_song_recordings": sum(len(s["recordings"]) for s in new_songs),
        "new_songs_with_work": sum(1 for s in new_songs if s["external_ids"]),
        "review": len(review), "review_by_reason": dict(Counter(r["reason"] for r in review)),
        "skipped": dict(Counter(s["reason"] for s in skipped))}
    return {"policy": POLICY, "catalog_instance_id": state["catalog_instance_id"], "summary": summary,
            "links": links, "new_songs": new_songs, "review": review, "skipped": skipped}


# --------------------------------------------------------------------------- review file

def _cell(value) -> str:
    return str(value).replace("|", "／").replace("\n", " ") if value not in (None, "") else "-"


def _songs_cell(candidates) -> str:
    return "; ".join(f"{c['song_id']} {c['title']} / {'·'.join(c['artists']) or '-'}" for c in candidates) or "-"


def _works_cell(works) -> str:
    return "; ".join(w["title"] + (f" ({'·'.join(w['writers'])})" if w.get("writers") else "")
                     + ("" if w.get("trusted", True) else " [제목 불일치, 안 씀]") for w in works) or "-"


BASIS = {"mb_work": "MB work가 이 곡에 저장됨", "mb_work_attached": "같은 MB work의 다른 녹음이 이 곡에 연결됨",
         "title_artist": "제목 + 같은 가수", "title_writer": "제목 + MB 작곡·작사가 곡 명의",
         "cover_title": "커버 표기 + 같은 제목의 곡 1곡", "user_review": "사용자 검수"}
REASONS = {"title_only": "같은 제목의 다른 아티스트 곡(커버 또는 동명곡)", "several_songs": "후보 곡 여러 개",
           "several_works": "MB work 여러 개(메들리 등)", "song_has_other_work": "후보 곡에 다른 MB work가 있음",
           "split_work": "예외로 나눈 곡(가수가 다름)", "cover_unknown": "커버인데 원곡이 DB에 없음"}


def render_review(decisions: dict, path: str) -> str:
    s = decisions["summary"]
    lines = [
        "# 녹음 → 곡 연결 검수", "",
        f"결정 파일: `{path}`. 녹음 {s['recordings']}개 중 ISRC로 MusicBrainz 녹음을 찾은 것 {s['with_mb_recording']}개, "
        f"그중 work가 있는 것 {s['with_mb_work']}개.", "",
        "- `결정` 칸: `song:<곡 id>`는 그 곡에 연결, `new`는 새 곡, `new:<ref>`는 2번 표의 그 새 곡에 합침, `-`는 연결하지 않음.",
        "- 2번 표는 `곡 제목` 칸을 고치면 그 제목으로 만든다. 명의는 이 파일에서 고치지 않는다(필요하면 알려 주면 따로 반영).",
        "- 3번 표는 기본이 `-`(연결 안 함)다. 나머지 행은 그대로 두면 승인으로 본다.",
        "- MusicBrainz work는 녹음 제목과 맞을 때만 쓴다. 맞지 않는 work는 `[제목 불일치, 안 씀]`으로 표시한다.", "",
        f"## 1. 기존 곡 연결 ({s['links']}개 녹음, {s['linked_songs']}곡)", "",
        "근거: " + ", ".join(f"`{k}` {v}" for k, v in BASIS.items() if k != "user_review") +
        ". `+work`는 그 곡에 MB work ID도 붙인다는 뜻이다.", "",
        "| 녹음 id | 녹음 제목 | 녹음 명의 | 결정 | 곡 | 근거 |", "| --- | --- | --- | --- | --- | --- |"]
    for link in decisions["links"]:
        song = link.get("song") or {}
        basis = link["basis"] + (" +work" if link.get("attach_work") else "")
        lines.append(f"| {link['recording_id']} | {_cell(link['title'])} | {_cell('·'.join(link['artists']))} | "
                     f"song:{link['song_id']} | {_cell(song.get('title'))} / {_cell('·'.join(song.get('artists', [])))} | {basis} |")
    lines += ["", f"## 2. 새 곡 ({s['new_songs']}곡, 녹음 {s['new_song_recordings']}개)", "",
              "명의는 MB 작곡·작사가 중 우리 DB 아티스트(원어 이름·별칭 일치)를 먼저, 그다음 커버가 아닌 녹음의 가수 순이다. "
              "`(커버 포함)`은 커버 녹음도 같은 곡으로 묶였다는 뜻이며, 커버 가수는 명의에 넣지 않는다.", "",
              "| ref | 곡 제목 | 명의 | 결정 | 녹음 | MusicBrainz work (작곡·작사) |", "| --- | --- | --- | --- | --- | --- |"]
    for song in decisions["new_songs"]:
        recs = ", ".join(str(r["recording_id"]) + (f" {r['title']}" if r["title"] != song["title_native"] else "")
                         for r in song["recordings"])
        work = "; ".join(song["work_titles"]) + (f" ({'·'.join(song['writers'])})" if song.get("writers") else "")
        work += (" (work 여러 개)" if "several_works" in song["flags"] else "") + \
                (" (커버 포함)" if "has_cover" in song["flags"] else "") + \
                (" (같은 제목의 다른 새 곡 있음)" if "same_title" in song["flags"] else "")
        lines.append(f"| {song['ref']} | {_cell(song['title_native'])} | {_cell('·'.join(song['artists']))} | new | "
                     f"{_cell(recs)} | {_cell(work.strip())} |")
    lines += ["", f"## 3. 검수 필요 ({s['review']}개 녹음)", "",
              "사유: " + ", ".join(f"`{k}` {v}" for k, v in REASONS.items()) + ".", "",
              "| 녹음 id | 녹음 제목 | 녹음 명의 | 결정 | 후보 곡 | 사유 | MusicBrainz work (작곡·작사) |",
              "| --- | --- | --- | --- | --- | --- | --- |"]
    for r in decisions["review"]:
        lines.append(f"| {r['recording_id']} | {_cell(r['title'])} | {_cell('·'.join(r['artists']))} | - | "
                     f"{_cell(_songs_cell(r['candidates']))} | {r['reason']} | {_cell(_works_cell(r['works']))} |")
    lines += ["", "## 제외 (적용하지 않음)", "",
              "- `uncredited`: 우리 아티스트 명의가 없는 녹음(본인 명의 앨범의 다른 가수 곡). 저장된 MB work가 있을 때만 1번 표로 간다.",
              "- `hidden_artist`: 카탈로그 표시를 끈 아티스트 녹음. 기존 곡과 확실히 맞을 때만 1번 표로 간다.", ""]
    lines += [f"- {k}: {v}개" for k, v in sorted(s["skipped"].items())]
    return "\n".join(lines) + "\n"


def read_review(path: Path) -> dict[str, dict[str, list[str]]]:
    sections, current = {}, None
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if line.startswith("## "):
            current = line[3:4]
            sections[current] = {}
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if current in ("1", "2", "3") and len(cells) >= 6 and re.fullmatch(r"n?\d+", cells[0]):
            sections[current][cells[0]] = cells
    return sections


def apply_review(decisions: dict, sections: dict[str, dict[str, list[str]]], state_songs: set[int] | None = None):
    """Fold the user's edits into the decision file. Rows missing from the file are dropped."""
    changes = []
    links, new_songs, review = [], [], []
    by_ref = {}
    for song in decisions["new_songs"]:
        cells = sections.get("2", {}).get(song["ref"])
        if cells is None:
            changes.append({"ref": song["ref"], "change": "drop", "reason": "not in review"})
            continue
        if cells[3] in ("-", ""):
            changes.append({"ref": song["ref"], "change": "drop"})
            continue
        song = {**song, "recordings": list(song["recordings"])}
        if cells[1] not in ("-", "") and cells[1] != _cell(song["title_native"]):
            changes.append({"ref": song["ref"], "change": "title", "from": song["title_native"], "to": cells[1]})
            song["title_native"] = cells[1]
        new_songs.append(song)
        by_ref[song["ref"]] = song

    def route(entry, decision, section):
        rec_id = entry["recording_id"]
        if decision in ("-", ""):
            return None
        match = re.fullmatch(r"song:(\d+)", decision)
        if match:
            song_id = int(match.group(1))
            if state_songs is not None and song_id not in state_songs:
                raise ValueError(f"recording {rec_id}: song {song_id} does not exist")
            return {"link": song_id}
        match = re.fullmatch(r"new:(n\d+)", decision)
        if match and match.group(1) in by_ref:
            return {"join": match.group(1)}
        if decision == "new":
            return {"new": True}
        raise ValueError(f"recording {rec_id} (section {section}): unknown decision {decision!r}")

    def place(entry, target, basis):
        rec = {"recording_id": entry["recording_id"], "version": entry["version"], "title": entry["title"],
               "isrc": entry["isrc"]}
        if "link" in target:
            links.append({**{k: entry[k] for k in ("recording_id", "version", "title", "isrc", "artists",
                                                   "mb_recordings", "works")},
                          "song_id": target["link"], "basis": basis, "attach_work": None})
        elif "join" in target:
            by_ref[target["join"]]["recordings"].append(rec)
        else:
            ref = f"n{entry['recording_id']}"
            song = {"ref": ref, "title_native": base_title(entry["title"]), "language_code": None,
                    "artist_ids": entry.get("artist_ids") or [], "artists": entry["artists"], "external_ids": [],
                    "work_titles": [], "recordings": [rec], "flags": ["user_review"]}
            new_songs.append(song)
            by_ref[ref] = song

    for link in decisions["links"]:
        cells = sections.get("1", {}).get(str(link["recording_id"]))
        if cells is None:
            changes.append({"recording_id": link["recording_id"], "change": "drop", "reason": "not in review"})
            continue
        decision = cells[3]
        if decision == f"song:{link['song_id']}":
            links.append(link)
            continue
        target = route(link, decision, "1")
        changes.append({"recording_id": link["recording_id"], "change": decision, "from": f"song:{link['song_id']}"})
        if target:
            place(link, target, "user_review")
    for entry in decisions["review"]:
        cells = sections.get("3", {}).get(str(entry["recording_id"]))
        target = route(entry, cells[3], "3") if cells else None
        if target:
            changes.append({"recording_id": entry["recording_id"], "change": cells[3], "from": "review"})
            place(entry, target, "user_review")
        else:
            review.append(entry)
    return {**decisions, "links": links, "new_songs": new_songs, "review": review,
            "user_review": changes, "reviewed": True}, changes


# --------------------------------------------------------------------------- apply

def manifest(decisions: dict) -> str:
    body = {"policy": decisions["policy"], "catalog_instance_id": decisions["catalog_instance_id"],
            "links": [{k: link[k] for k in ("recording_id", "version", "song_id", "attach_work")} for link in decisions["links"]],
            "new_songs": [{k: s[k] for k in ("ref", "title_native", "language_code", "artist_ids", "external_ids", "recordings")}
                          for s in decisions["new_songs"]]}
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def preallocate(conn, count: int) -> list[int]:
    if not count:
        return []
    return [r[0] for r in conn.execute(
        "SELECT nextval(pg_get_serial_sequence('public.songs','id')) FROM generate_series(1,%s)", (count,))]


def verify(conn, decisions: dict, *, lock: bool) -> None:
    links, new_songs = decisions["links"], decisions["new_songs"]
    planned = [(link["recording_id"], link["version"]) for link in links] + \
              [(r["recording_id"], r["version"]) for s in new_songs for r in s["recordings"]]
    ids = [p[0] for p in planned]
    if len(set(ids)) != len(ids):
        raise RuntimeError("A recording is planned twice; re-export")
    current = {r["id"]: r for r in rows(conn, "SELECT id, version, song_id, archived_at FROM recordings WHERE id=ANY(%s)"
                                        + (" ORDER BY id FOR UPDATE" if lock else ""), (ids,))}
    for rec_id, version in planned:
        row = current.get(rec_id)
        if row is None or row["archived_at"] or row["version"] != version or row["song_id"] is not None:
            raise RuntimeError(f"Recording {rec_id} changed since export; re-export")
    targets = sorted({link["song_id"] for link in links})
    alive = {r["id"] for r in rows(conn, """SELECT s.id FROM songs s WHERE s.id=ANY(%s) AND s.archived_at IS NULL
        AND NOT EXISTS (SELECT 1 FROM song_merges m WHERE m.source_song_id=s.id)""" + (" FOR SHARE" if lock else ""),
                                   (targets,))}
    if set(targets) - alive:
        raise RuntimeError(f"Songs archived or merged since export: {sorted(set(targets) - alive)}; re-export")
    works = [link["attach_work"] for link in links if link["attach_work"]]
    works = list(dict.fromkeys(works)) + [x["external_id"] for s in new_songs for x in s["external_ids"]]
    if len(set(works)) != len(works) or conn.execute(
            "SELECT count(*) FROM song_external_ids WHERE provider='musicbrainz_work' AND external_id=ANY(%s)",
            (works,)).fetchone()[0]:
        raise RuntimeError("A MusicBrainz work is already stored or planned twice; re-export")
    credit_ids = sorted({a for s in new_songs for a in s["artist_ids"]})
    if any(not s["artist_ids"] for s in new_songs) or conn.execute(
            "SELECT count(*) FROM artists WHERE id=ANY(%s) AND archived_at IS NULL", (credit_ids,)).fetchone()[0] != len(credit_ids):
        raise RuntimeError("A new song has no credit or a credited artist is missing; re-export")


def apply(conn, decisions: dict, *, write: bool) -> dict:
    identity = rows(conn, "SELECT id::text AS id, schema_version FROM catalog_instance").fetchone()
    revisions = {r["version"] for r in rows(conn, "SELECT version FROM catalog_schema_migrations")}
    if identity["schema_version"] != "catalog-v2" or not {"004", "005"} <= revisions:
        raise RuntimeError("Catalog must be catalog-v2 with revisions 004 and 005 applied")
    if identity["id"] != decisions["catalog_instance_id"] or decisions.get("policy") != POLICY:
        raise RuntimeError("Decision file was exported from a different catalog or policy")
    digest = manifest(decisions)
    operation_id = uuid.uuid5(NAMESPACE, identity["id"] + ":" + digest)
    if write:
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_ID,))
    if conn.execute("SELECT 1 FROM catalog_imports WHERE operation_id=%s", (operation_id,)).fetchone():
        return {"status": "already_committed", "manifest_hash": digest}
    verify(conn, decisions, lock=write)
    links, new_songs = decisions["links"], decisions["new_songs"]
    attach = {}
    for link in links:
        if link["attach_work"]:
            attach.setdefault(link["attach_work"], link["song_id"])
    summary = {"links": len(links), "linked_songs": len({link["song_id"] for link in links}),
               "attach_works": len(attach), "new_songs": len(new_songs),
               "new_song_recordings": sum(len(s["recordings"]) for s in new_songs),
               "new_song_works": sum(len(s["external_ids"]) for s in new_songs)}
    if not write:
        return {"status": "would_commit", "manifest_hash": digest, **summary}

    song_ids = dict(zip([s["ref"] for s in new_songs], preallocate(conn, len(new_songs))))
    if new_songs:
        inserted = conn.execute("""INSERT INTO songs(id,title_native,language_code) OVERRIDING SYSTEM VALUE
            SELECT x.id,x.title_native,x.language_code
            FROM jsonb_to_recordset(%s::jsonb) x(id integer,title_native text,language_code text)""",
            (Jsonb([{"id": song_ids[s["ref"]], "title_native": s["title_native"], "language_code": s["language_code"]}
                    for s in new_songs]),)).rowcount
        if inserted != len(new_songs):
            raise RuntimeError("song insert count mismatch")
        conn.execute("""INSERT INTO song_artists(song_id,artist_id,position)
            SELECT x.song_id,x.artist_id,x.position FROM jsonb_to_recordset(%s::jsonb) x(song_id integer,artist_id integer,position integer)""",
            (Jsonb([{"song_id": song_ids[s["ref"]], "artist_id": a, "position": n}
                    for s in new_songs for n, a in enumerate(s["artist_ids"])]),))
    external = [{"song_id": song_ids[s["ref"]], "external_id": x["external_id"]} for s in new_songs for x in s["external_ids"]] + \
               [{"song_id": song_id, "external_id": work} for work, song_id in attach.items()]
    if external:
        conn.execute("""INSERT INTO song_external_ids(song_id,provider,external_id)
            SELECT x.song_id,'musicbrainz_work',x.external_id FROM jsonb_to_recordset(%s::jsonb) x(song_id integer,external_id text)""",
                     (Jsonb(external),))
    updates = [{"id": link["recording_id"], "version": link["version"], "song_id": link["song_id"]} for link in links] + \
              [{"id": r["recording_id"], "version": r["version"], "song_id": song_ids[s["ref"]]}
               for s in new_songs for r in s["recordings"]]
    if updates:
        changed = conn.execute("""UPDATE recordings r SET song_id=x.song_id
            FROM jsonb_to_recordset(%s::jsonb) x(id integer,version integer,song_id integer)
            WHERE r.id=x.id AND r.version=x.version AND r.song_id IS NULL""", (Jsonb(updates),)).rowcount
        if changed != len(updates):
            raise RuntimeError("Recordings changed during apply")

    import_id = conn.execute("""INSERT INTO catalog_imports(operation_id,catalog_instance_id,manifest_hash,source_kind,
            result_mapping,result_summary) VALUES (%s,%s,%s,'batch_import',%s,%s) RETURNING id""",
        (operation_id, identity["id"], digest,
         Jsonb([{"entity_type": "songs", "ref": r, "id": i} for r, i in song_ids.items()]),
         Jsonb({"kind": POLICY, **summary}))).fetchone()[0]
    changes = []
    for s in new_songs:
        changes.append({"entity_type": "songs", "entity_id": song_ids[s["ref"]], "action": "create", "before_data": None,
                        "after_data": {"title_native": s["title_native"], "language_code": s["language_code"],
                                       "artist_ids": s["artist_ids"], "external_ids": s["external_ids"]},
                        "provenance": {"policy": POLICY, "ref": s["ref"], "source": "spotify_recordings",
                                       "recordings": [r["recording_id"] for r in s["recordings"]],
                                       "isrcs": [r["isrc"] for r in s["recordings"]], "work_titles": s["work_titles"],
                                       "flags": s["flags"]}})
    for work, song_id in attach.items():
        changes.append({"entity_type": "songs", "entity_id": song_id, "action": "update",
                        "before_data": {"musicbrainz_work": None}, "after_data": {"musicbrainz_work": work},
                        "provenance": {"policy": POLICY, "source": "musicbrainz", "license": "CC0",
                                       "via_recordings": [link["recording_id"] for link in links if link["attach_work"] == work]}})
    for link in links:
        changes.append({"entity_type": "recordings", "entity_id": link["recording_id"], "action": "update",
                        "before_data": {"song_id": None}, "after_data": {"song_id": link["song_id"]},
                        "provenance": {"policy": POLICY, "basis": link["basis"], "isrc": link["isrc"],
                                       "mb_recordings": link["mb_recordings"], "works": [w["id"] for w in link["works"]]}})
    for s in new_songs:
        for r in s["recordings"]:
            changes.append({"entity_type": "recordings", "entity_id": r["recording_id"], "action": "update",
                            "before_data": {"song_id": None}, "after_data": {"song_id": song_ids[s["ref"]]},
                            "provenance": {"policy": POLICY, "basis": "new_song", "ref": s["ref"], "isrc": r["isrc"]}})
    conn.execute("""INSERT INTO catalog_changes(import_id,entity_type,entity_id,action,before_data,after_data,provenance)
        SELECT %s,x.entity_type,x.entity_id,x.action,x.before_data,x.after_data,x.provenance
        FROM jsonb_to_recordset(%s::jsonb) x(entity_type text,entity_id integer,action text,before_data jsonb,
             after_data jsonb,provenance jsonb)""", (import_id, Jsonb(changes)))
    return {"status": "committed", "manifest_hash": digest, "import_id": import_id, **summary}


# --------------------------------------------------------------------------- CLI

def cover_lookups(decisions: dict, found: dict[int, dict], lookups: Lookups) -> dict[int, bool]:
    """For every would-be new song that has a MusicBrainz work, ask MusicBrainz whether its
    most original-looking recording (no version tail first) is a cover; a cover marks the
    whole group, which shares that work."""
    covers = {}
    for song in decisions["new_songs"]:
        if not song["external_ids"]:
            continue
        ordered = sorted(song["recordings"], key=lambda r: (r["title"] != base_title(r["title"]), r["recording_id"]))
        rep = next((r for r in ordered if found.get(r["recording_id"], {}).get("mb_recordings")), None)
        if rep and lookups.recording_is_cover(found[rep["recording_id"]]["mb_recordings"][0]):
            covers.update({r["recording_id"]: True for r in song["recordings"]})
    return covers


def export(conn, lookups: Lookups) -> dict:
    state = load_state(conn)
    conn.rollback()
    found = lookup_all(state, lookups)
    splits = split_works()
    covers = cover_lookups(plan(state, found, splits), found, lookups)
    decisions = plan(state, found, splits, covers)
    decisions["summary"]["mb_covers"] = len(covers)
    for link in decisions["links"]:
        song = state["songs"][link["song_id"]]
        link["song"] = {"title": song["title_native"],
                        "artists": [state["artists"][a]["name_native"] for a in song["artists"] if a in state["artists"]]}
    decisions["exported_at"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    decisions["requests"] = lookups.requests
    return decisions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--round", type=int, default=1)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("export", help="Look up MusicBrainz and write the decision + review files (read-only DB access)")
    sub.add_parser("review-import", help="Fold the edited review file into the decision file (no DB access)")
    run = sub.add_parser("apply", help="Dry-run the decision file; --apply writes it")
    run.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    path = Path(str(DECISIONS).format(n=args.round))
    review_path = REPORTS / f"review-{args.round}.md"
    if args.command == "review-import":
        edited = REPORTS / f"review-{args.round}.user-edited.md"
        edited.write_text(review_path.read_text(encoding="utf-8"), encoding="utf-8")
        decisions, changes = apply_review(json.loads(path.read_text(encoding="utf-8")), read_review(review_path))
        path.write_text(json.dumps(decisions, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(json.dumps({"file": str(path.relative_to(ROOT)), "changes": changes, "links": len(decisions["links"]),
                          "new_songs": len(decisions["new_songs"])}, ensure_ascii=False, indent=2))
        return 0
    writing = args.command == "apply" and args.apply
    with psycopg.connect(migrate_catalog.load_connection(), connect_timeout=20) as conn:
        migrate_catalog.configure_transaction(conn, read_only=not writing)
        if args.command == "export":
            lookups = Lookups(REPORTS / "musicbrainz.json")
            try:
                decisions = export(conn, lookups)
            finally:
                lookups.close()
            path.write_text(json.dumps(decisions, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            REPORTS.mkdir(parents=True, exist_ok=True)
            review_path.write_text(render_review(decisions, str(path.relative_to(ROOT))), encoding="utf-8")
            print(json.dumps({"file": str(path.relative_to(ROOT)), "review_file": str(review_path.relative_to(ROOT)),
                              "requests": decisions["requests"], **decisions["summary"]}, ensure_ascii=False, indent=2))
            return 0
        decisions = json.loads(path.read_text(encoding="utf-8"))
        result = apply(conn, decisions, write=writing)
        if writing:
            conn.commit()
        else:
            conn.rollback()
            result["mode"] = "dry-run"
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
