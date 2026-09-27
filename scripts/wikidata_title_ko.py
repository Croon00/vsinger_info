"""Korean song titles from Wikidata, found through stored external IDs (plan step 6).

``export`` (READ ONLY on the catalog) looks up the Wikidata items that carry a song's
stored VocaDB song ID (P11100) or MusicBrainz work ID (P435) -- an ID match, never a
name search -- and writes migrations/catalog/title-ko-wikidata-N.json:

  * the item's QID for song_external_ids (provider 'wikidata') when no song owns it yet,
  * its Korean label as ``title_ko`` when the song has none, the label contains Hangul
    and differs from the native title (a Latin label like "Lemon" is not a Korean title).
    Labels that only spell the Japanese reading in Hangul (reviewed list in
    migrations/catalog/title-ko-wikidata-manual-N.json) become Korean song aliases instead.

A song whose IDs point at different items, or an item reached from several songs, is
listed as a conflict and left alone. SPARQL responses are cached in git-ignored
db-migration/reports/wikidata/. Wikidata is CC0; the QID and label are kept as evidence.

``apply`` dry-runs the file; ``apply --apply`` writes it in ONE transaction with a
catalog_imports receipt and one catalog_changes row per song. Rows changed since export
abort the whole run and a second apply is a no-op.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
import time
import unicodedata
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import httpx
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[1]
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

POLICY = "song-title-ko-wikidata-v1"
NAMESPACE = uuid.UUID("7e2b9c4a-1d63-4f08-a5e7-3b8c0d6f2a91")
CACHE_DIR = ROOT / "db-migration" / "reports" / "wikidata"
DECISIONS = ROOT / "migrations" / "catalog" / "title-ko-wikidata-{n}.json"
MANUAL = ROOT / "migrations" / "catalog" / "title-ko-wikidata-manual-{n}.json"
ENDPOINT = "https://query.wikidata.org/sparql"
USER_AGENT = "schedule_music-song-master/0.1 (song catalog research; https://github.com/)"
PROPERTIES = {"vocadb": "P11100", "musicbrainz_work": "P435"}
BATCH = 150
HANGUL = re.compile(r"[\uac00-\ud7a3]")
QID = re.compile(r"^Q[1-9][0-9]*$")
# Korean Wikipedia-style disambiguation after the title: "謎 -> 나조 (코마츠 미호의 싱글)".
DISAMBIGUATION = re.compile(r"\s*\((?:[^()]*\s)?[^()]*(?:싱글|노래|곡|앨범|음반)\)\s*$")

_spec = importlib.util.spec_from_file_location("migrate_catalog", ROOT / "scripts" / "migrate_catalog.py")
migrate_catalog = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migrate_catalog)


def alias_key(value: str) -> str:
    """song_aliases.normalized_alias, as the admin schema generates it."""
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def rows(conn, query, params=None):
    return conn.cursor(row_factory=dict_row).execute(query, params)


def load_state(conn) -> dict:
    songs = {r["id"]: {**r, "external": []} for r in rows(conn, """
        SELECT s.id, s.version, s.title_native, s.title_ko FROM songs s
        WHERE s.archived_at IS NULL AND NOT EXISTS (SELECT 1 FROM song_merges m WHERE m.source_song_id=s.id)""")}
    wikidata = {}
    for r in rows(conn, "SELECT song_id, provider, external_id FROM song_external_ids"):
        if r["provider"] == "wikidata":
            wikidata[r["external_id"]] = r["song_id"]
        elif r["song_id"] in songs and r["provider"] in PROPERTIES:
            songs[r["song_id"]]["external"].append((r["provider"], r["external_id"]))
    identity = rows(conn, "SELECT id::text AS id FROM catalog_instance").fetchone()["id"]
    return {"catalog_instance_id": identity, "songs": songs, "wikidata": wikidata}


def sparql(ids: list[str], prop: str) -> str:
    values = " ".join(json.dumps(i) for i in ids)
    return f"""SELECT ?item ?id ?ko ?ja ?en WHERE {{
  VALUES ?id {{ {values} }}
  ?item wdt:{prop} ?id .
  OPTIONAL {{ ?item rdfs:label ?ko FILTER(LANG(?ko) = "ko") }}
  OPTIONAL {{ ?item rdfs:label ?ja FILTER(LANG(?ja) = "ja") }}
  OPTIONAL {{ ?item rdfs:label ?en FILTER(LANG(?en) = "en") }}
}}"""


class Wikidata:
    """SPARQL lookups by external ID with an on-disk cache and a polite pace."""

    def __init__(self, cache_path: Path, *, transport=None, interval: float = 1.0):
        self.cache_path = cache_path
        self.cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
        self.http = httpx.Client(headers={"User-Agent": USER_AGENT, "Accept": "application/sparql-results+json"},
                                 timeout=60, transport=transport)
        self.interval, self.requests, self._last = interval, 0, 0.0

    def lookup(self, provider: str, ids: list[str]) -> dict[str, list[dict]]:
        """external id -> [{qid, ko, ja, en}] for every Wikidata item carrying it."""
        found: dict[str, list[dict]] = defaultdict(list)
        missing = [i for i in ids if f"{provider}:{i}" not in self.cache]
        for start in range(0, len(missing), BATCH):
            chunk = missing[start:start + BATCH]
            data = self._query(sparql(chunk, PROPERTIES[provider]))
            got: dict[str, dict] = {}
            for b in data["results"]["bindings"]:
                qid = b["item"]["value"].rsplit("/", 1)[-1]
                entry = got.setdefault(f"{b['id']['value']}|{qid}", {"id": b["id"]["value"], "qid": qid})
                for lang in ("ko", "ja", "en"):
                    if lang in b:
                        entry[lang] = b[lang]["value"]
            for i in chunk:
                self.cache[f"{provider}:{i}"] = [
                    {k: v for k, v in e.items() if k != "id"} for e in got.values() if e["id"] == i]
            self.save()
        for i in ids:
            found[i] = self.cache.get(f"{provider}:{i}", [])
        return found

    def _query(self, query: str) -> dict:
        for attempt in range(4):
            wait = self._last + self.interval - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            self.requests += 1
            try:
                response = self.http.post(ENDPOINT, data={"query": query})
            except httpx.TransportError:
                if attempt == 3:
                    raise
                time.sleep(5 * (attempt + 1))
                continue
            if response.status_code in (429, 500, 502, 503, 504) and attempt < 3:
                time.sleep(min(float(response.headers.get("Retry-After") or 10 * (attempt + 1)), 120))
                continue
            response.raise_for_status()
            return response.json()
        raise RuntimeError("Wikidata query failed")

    def save(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.cache_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.cache, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.cache_path)

    def close(self) -> None:
        self.http.close()


def korean_title(label: str | None, title_native: str) -> str | None:
    """The Korean label as a title: disambiguation dropped, Hangul required, not the native title."""
    text = DISAMBIGUATION.sub("", (label or "").strip()).strip()
    return text if HANGUL.search(text) and text != title_native else None


def plan(state: dict, found: dict[tuple[str, str], list[dict]], manual: dict | None = None) -> dict:
    """Pure: turn the ID lookups into a decision file.

    ``manual["reading_only"]`` lists Korean labels that only spell the Japanese reading
    in Hangul; they become Korean song aliases instead of ``title_ko``.
    """
    reading_only = {(m["title_native"], m["label"]) for m in (manual or {}).get("reading_only", [])}
    by_song: dict[int, dict[str, dict]] = defaultdict(dict)
    for song_id, song in state["songs"].items():
        for ext in song["external"]:
            for item in found.get(ext, []):
                by_song[song_id].setdefault(item["qid"], {**item, "via": []})["via"].append(list(ext))
    owners: dict[str, list[int]] = defaultdict(list)
    for song_id, items in by_song.items():
        for qid in items:
            owners[qid].append(song_id)
    decisions, conflicts = [], []
    for song_id in sorted(by_song):
        song, items = state["songs"][song_id], by_song[song_id]
        if len(items) > 1:
            conflicts.append({"song_id": song_id, "reason": "IDs point at different Wikidata items", "qids": sorted(items)})
            continue
        (qid, item), = items.items()
        stored = state["wikidata"].get(qid)
        if len(owners[qid]) > 1 or (stored and stored != song_id) or not QID.match(qid):
            conflicts.append({"song_id": song_id, "qid": qid, "reason": "item reached from several songs or owned by another",
                              "songs": sorted(set(owners[qid]) | ({stored} if stored else set()))})
            continue
        # A reading-only label is a search alias whether or not the song already has a title_ko
        # (a later title_ko round must not drop the reviewed alias); other labels only fill an
        # empty title_ko.
        label = korean_title(item.get("ko"), song["title_native"])
        title_ko = alias_ko = None
        if label and (song["title_native"], label) in reading_only:
            alias_ko = label if label != song["title_ko"] else None
        elif song["title_ko"] is None:
            title_ko = label
        add_qid = stored is None
        if not (title_ko or alias_ko or add_qid):
            continue
        decisions.append({"song_id": song_id, "version": song["version"], "title_native": song["title_native"],
                          "wikidata": qid if add_qid else None, "title_ko": title_ko, "alias_ko": alias_ko,
                          "evidence": {"qid": qid, "via": item["via"], "labels": {k: item.get(k) for k in ("ko", "ja", "en")}}})
    summary = {"songs_with_item": len(by_song), "decisions": len(decisions),
               "title_ko": sum(1 for d in decisions if d["title_ko"]),
               "alias_ko": sum(1 for d in decisions if d["alias_ko"]),
               "wikidata_ids": sum(1 for d in decisions if d["wikidata"]),
               "ko_label_not_hangul": sum(1 for s, items in by_song.items() for i in items.values()
                                          if i.get("ko") and not HANGUL.search(i["ko"])),
               "conflicts": len(conflicts)}
    return {"policy": POLICY, "catalog_instance_id": state["catalog_instance_id"], "summary": summary,
            "songs": decisions, "conflicts": conflicts}


def render_review(decisions: dict, path: str) -> str:
    """Markdown tables for the human review: Korean titles, Korean aliases, QID links."""
    def row(d, value):
        return f"| {d['song_id']} | {d['title_native']} | {value} | {d['evidence']['labels'].get('ko') or '-'} | {d['evidence']['qid']} |"
    head = "| song_id | 원제 | {} | Wikidata 한국어 라벨 | QID |\n| --- | --- | --- | --- | --- |"
    lines = ["# Wikidata 결과 검수", "", f"결정 파일: `{path}`.",
             "고치려면 제목·별칭 칸을 바꾸고, 빼려면 `-`로 바꾼다. QID 표에서 빼려면 QID 칸을 `-`로 바꾼다.", "",
             f"## 한국어 제목 ({sum(1 for d in decisions['songs'] if d['title_ko'])}곡)", "", head.format("제목")]
    lines += [row(d, d["title_ko"]) for d in decisions["songs"] if d["title_ko"]]
    lines += ["", f"## 한국어 별칭 ({sum(1 for d in decisions['songs'] if d.get('alias_ko'))}곡, 제목이 아니라 검색용 별칭)", "",
              head.format("별칭")]
    lines += [row(d, d["alias_ko"]) for d in decisions["songs"] if d.get("alias_ko")]
    lines += ["", f"## Wikidata ID 연결 ({sum(1 for d in decisions['songs'] if d['wikidata'])}곡)", "", head.format("일본어 라벨")]
    lines += [row(d, d["evidence"]["labels"].get("ja") or "-") for d in decisions["songs"] if d["wikidata"]]
    if decisions["conflicts"]:
        lines += ["", "## 적용하지 않는 충돌", ""] + [f"- {json.dumps(c, ensure_ascii=False)}" for c in decisions["conflicts"]]
    return "\n".join(lines) + "\n"


def read_review(path: Path) -> dict[str, dict[int, list[str]]]:
    """{section: {song_id: cells}} from an edited review file."""
    sections, current = {}, None
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if line.startswith("## "):
            current = line[3:].split(" (")[0].strip()
            sections[current] = {}
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if current and len(cells) == 5 and cells[0].isdigit():
            sections[current][int(cells[0])] = cells
    return sections


def apply_review(decisions: dict, sections: dict[str, dict[int, list[str]]]) -> tuple[dict, list[dict]]:
    """Fold the user's edits into the decision file; returns (decisions, changes seen)."""
    titles, aliases, links = (sections.get(k, {}) for k in ("한국어 제목", "한국어 별칭", "Wikidata ID 연결"))
    changes, kept = [], []
    for d in decisions["songs"]:
        d = dict(d)
        for key, table, section in (("title_ko", titles, "한국어 제목"), ("alias_ko", aliases, "한국어 별칭")):
            if d.get(key) and section in sections and d["song_id"] not in table:
                # Not shown to the user in the reviewed file, so not approved.
                changes.append({"song_id": d["song_id"], "field": key, "from": d[key], "to": None, "reason": "not in review"})
                d[key] = None
            elif d.get(key) and d["song_id"] in table:
                edited = table[d["song_id"]][2]
                value = None if edited in ("-", "") else edited
                if value != d[key]:
                    changes.append({"song_id": d["song_id"], "field": key, "from": d[key], "to": value})
                    d[key] = value
        if d["wikidata"] and d["song_id"] in links and links[d["song_id"]][4] in ("-", ""):
            changes.append({"song_id": d["song_id"], "field": "wikidata", "from": d["wikidata"], "to": None})
            d["wikidata"] = None
        if d["title_ko"] or d.get("alias_ko") or d["wikidata"]:
            kept.append(d)
    return {**decisions, "songs": kept, "user_review": changes}, changes


def manifest(decisions: dict) -> str:
    body = {k: decisions[k] for k in ("policy", "catalog_instance_id", "songs")}
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def apply(conn, decisions: dict, *, write: bool) -> dict:
    identity = rows(conn, "SELECT id::text AS id, schema_version FROM catalog_instance").fetchone()
    if identity["schema_version"] != "catalog-v2" or identity["id"] != decisions["catalog_instance_id"]:
        raise RuntimeError("Decision file was exported from a different catalog")
    if decisions.get("policy") != POLICY:
        raise RuntimeError("Unexpected decision file policy")
    digest = manifest(decisions)
    operation_id = uuid.uuid5(NAMESPACE, identity["id"] + ":" + digest)
    if write:
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (731064923,))
    if conn.execute("SELECT 1 FROM catalog_imports WHERE operation_id=%s", (operation_id,)).fetchone():
        return {"status": "already_committed", "manifest_hash": digest}
    items = decisions["songs"]
    current = {r["id"]: r for r in rows(conn, "SELECT id, version, title_ko, archived_at FROM songs WHERE id=ANY(%s)"
                                         + (" FOR UPDATE" if write else ""), ([d["song_id"] for d in items],))}
    for d in items:
        row = current.get(d["song_id"])
        if row is None or row["archived_at"] or row["version"] != d["version"] or (d["title_ko"] and row["title_ko"]):
            raise RuntimeError(f"Song {d['song_id']} changed since export; re-export")
    qids = [d["wikidata"] for d in items if d["wikidata"]]
    if len(set(qids)) != len(qids) or conn.execute(
            "SELECT count(*) FROM song_external_ids WHERE provider='wikidata' AND external_id=ANY(%s)", (qids,)).fetchone()[0]:
        raise RuntimeError("A Wikidata ID is already stored or assigned twice; re-export")
    aliases = [{"song_id": d["song_id"], "alias": d["alias_ko"], "normalized_alias": alias_key(d["alias_ko"])}
               for d in items if d.get("alias_ko")]
    if aliases and conn.execute("""SELECT count(*) FROM song_aliases a JOIN jsonb_to_recordset(%s::jsonb)
            x(song_id integer,normalized_alias text) ON a.song_id=x.song_id AND a.normalized_alias=x.normalized_alias""",
            (Jsonb(aliases),)).fetchone()[0]:
        raise RuntimeError("A Korean alias is already stored; re-export")
    summary = {"songs": len(items), "title_ko": sum(1 for d in items if d["title_ko"]), "alias_ko": len(aliases),
               "wikidata_ids": len(qids)}
    if not write:
        return {"status": "would_commit", "manifest_hash": digest, **summary}
    titles = [{"id": d["song_id"], "version": d["version"], "title_ko": d["title_ko"]} for d in items if d["title_ko"]]
    if titles:
        changed = conn.execute("""UPDATE songs s SET title_ko=x.title_ko
            FROM jsonb_to_recordset(%s::jsonb) x(id integer,version integer,title_ko text)
            WHERE s.id=x.id AND s.version=x.version AND s.title_ko IS NULL""", (Jsonb(titles),)).rowcount
        if changed != len(titles):
            raise RuntimeError("Songs changed during apply")
    if aliases:
        conn.execute("""INSERT INTO song_aliases(song_id,alias,normalized_alias,locale,source)
            SELECT x.song_id,x.alias,x.normalized_alias,'ko','wikidata'
            FROM jsonb_to_recordset(%s::jsonb) x(song_id integer,alias text,normalized_alias text)""", (Jsonb(aliases),))
    if qids:
        conn.execute("""INSERT INTO song_external_ids(song_id,provider,external_id)
            SELECT x.song_id,'wikidata',x.qid FROM jsonb_to_recordset(%s::jsonb) x(song_id integer,qid text)""",
                     (Jsonb([{"song_id": d["song_id"], "qid": d["wikidata"]} for d in items if d["wikidata"]]),))
    import_id = conn.execute("""INSERT INTO catalog_imports(operation_id,catalog_instance_id,manifest_hash,source_kind,
            result_mapping,result_summary) VALUES (%s,%s,%s,'batch_import',%s,%s) RETURNING id""",
        (operation_id, identity["id"], digest, Jsonb([{"entity_type": "songs", "id": d["song_id"]} for d in items]),
         Jsonb({"kind": POLICY, **summary}))).fetchone()[0]
    changes = [{"entity_id": d["song_id"],
                "before_data": {"title_ko": None} if d["title_ko"] else {"wikidata": None},
                "after_data": {**({"title_ko": d["title_ko"]} if d["title_ko"] else {}),
                               **({"alias_ko": d["alias_ko"]} if d.get("alias_ko") else {}),
                               **({"wikidata": d["wikidata"]} if d["wikidata"] else {})},
                "provenance": {"policy": POLICY, "source": "wikidata", "license": "CC0", **d["evidence"]}} for d in items]
    conn.execute("""INSERT INTO catalog_changes(import_id,entity_type,entity_id,action,before_data,after_data,provenance)
        SELECT %s,'songs',x.entity_id,'update',x.before_data,x.after_data,x.provenance
        FROM jsonb_to_recordset(%s::jsonb) x(entity_id integer,before_data jsonb,after_data jsonb,provenance jsonb)""",
                 (import_id, Jsonb(changes)))
    return {"status": "committed", "manifest_hash": digest, "import_id": import_id, **summary}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("export", help="Look up Wikidata and write the decision file (read-only DB access)")
    sub.add_parser("review-import", help="Fold the edited review file into the decision file (no DB access)")
    run = sub.add_parser("apply", help="Dry-run the decision file; --apply writes it")
    run.add_argument("--apply", action="store_true")
    parser.add_argument("--round", type=int, default=1)
    args = parser.parse_args()
    path = Path(str(DECISIONS).format(n=args.round))
    review_path = CACHE_DIR / f"review-{args.round}.md"
    if args.command == "review-import":
        decisions, changes = apply_review(json.loads(path.read_text(encoding="utf-8")), read_review(review_path))
        path.write_text(json.dumps(decisions, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(json.dumps({"file": str(path.relative_to(ROOT)), "changes": changes, "songs": len(decisions["songs"])},
                         ensure_ascii=False, indent=2))
        return 0
    writing = args.command == "apply" and args.apply
    with psycopg.connect(migrate_catalog.load_connection(), connect_timeout=20) as conn:
        migrate_catalog.configure_transaction(conn, read_only=not writing)
        if args.command == "export":
            state = load_state(conn)
            conn.rollback()
            client = Wikidata(CACHE_DIR / "id-lookups.json")
            try:
                by_provider = defaultdict(set)
                for song in state["songs"].values():
                    for provider, ext in song["external"]:
                        by_provider[provider].add(ext)
                found = {}
                for provider, ids in by_provider.items():
                    for ext, items in client.lookup(provider, sorted(ids)).items():
                        found[(provider, ext)] = items
            finally:
                client.close()
            manual_path = MANUAL.with_name(MANUAL.name.format(n=args.round))
            manual = json.loads(manual_path.read_text(encoding="utf-8")) if manual_path.exists() else {}
            decisions = plan(state, found, manual)
            decisions["exported_at"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            decisions["requests"] = client.requests
            path.write_text(json.dumps(decisions, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            review_path.write_text(render_review(decisions, str(path.relative_to(ROOT))), encoding="utf-8")
            print(json.dumps({"file": str(path.relative_to(ROOT)), "requests": client.requests,
                              "looked_up": {p: len(i) for p, i in by_provider.items()}, **decisions["summary"]},
                             ensure_ascii=False, indent=2))
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
