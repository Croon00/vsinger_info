"""Korean song title candidates for review (plan step 6, after Wikidata).

``prepare`` (READ ONLY on the catalog) picks the most sung songs that still have no
``title_ko`` and a non-Latin native title, skips songs the Wikidata decision file already
titles, and writes research inputs plus a conventions sample (existing title_ko values)
to git-ignored db-migration/reports/title-ko/round-N/.

``export`` merges the research outputs into migrations/catalog/title-ko-candidates-N.json
with one ``decision`` per song for the user to review: ``accept`` (a sourced Korean title:
official Korean release, Korean Wikipedia, established Korean usage), ``review`` (only a
translation proposal, or weak evidence) or ``skip``. Nothing is written to the catalog.

``apply`` dry-runs the reviewed file; ``apply --apply`` writes only ``accept`` rows into
empty ``title_ko`` in ONE transaction with a catalog_imports receipt and one
catalog_changes row per song (basis and sources as provenance). Rows changed since
export abort the whole run and a second apply is a no-op.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import random
import re
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.core.song_keys import ascii_latin  # noqa: E402

POLICY = "song-title-ko-candidates-v1"
NAMESPACE = uuid.UUID("3f9a2c61-8b4e-4d17-9e05-c7a1b6d82f40")
REPORT_DIR = ROOT / "db-migration" / "reports" / "title-ko"
DECISIONS = ROOT / "migrations" / "catalog" / "title-ko-candidates-{n}.json"
MANUAL = ROOT / "migrations" / "catalog" / "title-ko-candidates-manual-{n}.json"
WIKIDATA = ROOT / "migrations" / "catalog" / "title-ko-wikidata-1.json"
SOURCED = {"official_korean_release", "ko_wikipedia", "korean_usage"}
DECISION_VALUES = {"accept", "review", "skip"}
HANGUL = re.compile(r"[\uac00-\ud7a3]")
REVIEW_MARKS = re.compile(r"^[\u2714\u25c7\u270e]\s*")

_spec = importlib.util.spec_from_file_location("migrate_catalog", ROOT / "scripts" / "migrate_catalog.py")
migrate_catalog = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migrate_catalog)


def rows(conn, query, params=None):
    return conn.cursor(row_factory=dict_row).execute(query, params)


def load_songs(conn) -> list[dict]:
    return rows(conn, """
        SELECT s.id, s.version, s.title_native, s.title_latin, s.title_ko, s.language_code,
               (SELECT count(*) FROM performances p WHERE p.song_id=s.id AND p.archived_at IS NULL) AS performances,
               coalesce((SELECT jsonb_agg(jsonb_build_object('name', a.name_native, 'name_ko', a.name_ko) ORDER BY sa.position, sa.id)
                         FROM song_artists sa JOIN artists a ON a.id=sa.artist_id WHERE sa.song_id=s.id), '[]') AS artists,
               coalesce((SELECT jsonb_agg(e.provider || ':' || e.external_id ORDER BY e.provider)
                         FROM song_external_ids e WHERE e.song_id=s.id), '[]') AS external_ids,
               coalesce((SELECT jsonb_agg(al.alias) FROM song_aliases al WHERE al.song_id=s.id AND al.locale='ko'), '[]') AS ko_aliases
        FROM songs s
        WHERE s.archived_at IS NULL AND NOT EXISTS (SELECT 1 FROM song_merges m WHERE m.source_song_id=s.id)
        ORDER BY performances DESC, s.id""").fetchall()


def wikidata_titles() -> dict[int, dict]:
    """Songs the (not necessarily applied) Wikidata decision file already covers."""
    if not WIKIDATA.exists():
        return {}
    data = json.loads(WIKIDATA.read_text(encoding="utf-8"))
    return {d["song_id"]: d for d in data["songs"]}


def select(songs: list[dict], wikidata: dict[int, dict], top: int) -> list[dict]:
    picked = []
    for s in songs:
        if s["title_ko"] or ascii_latin(s["title_native"]) or (wikidata.get(s["id"]) or {}).get("title_ko"):
            continue
        reading = (wikidata.get(s["id"]) or {}).get("alias_ko")
        picked.append({"song_id": s["id"], "title_native": s["title_native"], "title_latin": s["title_latin"],
                       "artists": s["artists"], "performances": s["performances"], "external_ids": s["external_ids"],
                       "reading_in_hangul": reading or next(iter(s["ko_aliases"]), None)})
        if len(picked) == top:
            break
    return picked


def conventions(songs: list[dict], n: int = 60) -> list[dict]:
    titled = [{"title_native": s["title_native"], "title_ko": s["title_ko"]} for s in songs if s["title_ko"]]
    random.Random(7).shuffle(titled)
    return titled[:n]


def namu_evidence(found: dict | None, title_native: str) -> dict | None:
    """A Namu Wiki name counts only for this song, with the document title or a snippet
    that shows the Japanese title next to the Korean name."""
    if not found or not found.get("same_song") or not found.get("namu_title_ko") or not HANGUL.search(found["namu_title_ko"]):
        return None
    shown = found.get("where") == "document_title" or title_native in (found.get("evidence") or "")
    return {**found, "verified": shown}


def same_text(a: str | None, b: str | None) -> bool:
    return "".join((a or "").split()) == "".join((b or "").split())


def export(songs: list[dict], picked_inputs: list[dict], research: list[dict], manual: dict | None = None,
           namu: list[dict] | None = None) -> dict:
    """Pure: research outputs -> decision file. Validates every proposal against the input.

    ``manual["overrides"]`` replaces a proposal after the parent review (the research
    title is kept as an alternative); the song stays ``review`` unless it is sourced.
    ``namu`` (Namu Wiki names read from cached pages) comes first: a verified name that
    matches the proposal is ``accept``; a different one leads with the proposal as an
    alternative and stays ``review``.
    """
    overrides = {o["song_id"]: o for o in (manual or {}).get("overrides", [])}
    namu_by_song = {n["song_id"]: n for n in namu or []}
    user = (manual or {}).get("user_review") or {}
    user_titles = {t["song_id"]: t["title_ko"] for t in user.get("titles", [])}
    current = {s["id"]: s for s in songs}
    wanted = {i["song_id"]: i for i in picked_inputs}
    by_song = {}
    problems = []
    for r in research:
        if r.get("song_id") not in wanted or r["song_id"] in by_song:
            problems.append({"song_id": r.get("song_id"), "reason": "unknown or duplicate song in research"})
            continue
        by_song[r["song_id"]] = r
    items = []
    for song_id, source in wanted.items():
        song, r = current.get(song_id), by_song.get(song_id)
        if song is None or r is None:
            problems.append({"song_id": song_id, "reason": "song gone" if song is None else "no research output"})
            continue
        title = (r.get("title_ko") or "").strip() or None
        basis = r.get("basis")
        alternatives, note = list(r.get("alternatives") or []), r.get("note")
        if song_id in overrides:
            if title:
                alternatives.insert(0, {"title_ko": title, "where": "research proposal"})
            title, basis, note = overrides[song_id]["title_ko"], "translation", f"parent review: {overrides[song_id]['reason']}"
        if title and not HANGUL.search(title):
            title, basis = None, None
        sourced = basis in SOURCED and bool(r.get("sources"))
        decision = "accept" if title and sourced and r.get("confidence") == "high" else ("review" if title else "skip")
        confidence = r.get("confidence") if song_id not in overrides else "medium"
        sources = list(r.get("sources") or [])
        found = namu_evidence(namu_by_song.get(song_id), song["title_native"])
        namu_name = None
        if found:
            namu_name = found["namu_title_ko"]
            agrees = same_text(namu_name, title)
            if title and not agrees:
                alternatives.insert(0, {"title_ko": title, "where": "research/parent proposal"})
            title, basis, confidence = namu_name, "korean_usage", "high" if found["verified"] else "medium"
            sources = [found["url"], *sources]
            note = f"namu.wiki {found.get('where')}: {found.get('evidence')}" + ("" if agrees else " (differs from proposal)")
            decision = "accept" if found["verified"] and agrees else "review"
        if song_id in user_titles:
            # The user's own title from the review wins; what was proposed stays as an alternative.
            if title and not same_text(title, user_titles[song_id]):
                alternatives.insert(0, {"title_ko": title, "where": "proposal before user review"})
            title, basis, confidence = user_titles[song_id], "user_review", "high"
            note = f"user review {user.get('date')}" + (f"; {note}" if note else "")
            if title is None:
                decision = "skip"
        if user.get("approved") == "all" and title and HANGUL.search(title):
            decision = "accept"
        items.append({"song_id": song_id, "version": song["version"], "title_native": song["title_native"],
                      "artists": [a["name"] for a in source["artists"]], "performances": source["performances"],
                      "title_ko": title, "basis": basis, "confidence": confidence,
                      "alternatives": alternatives, "sources": sources, "namu": namu_name,
                      "note": note, "decision": decision})
    summary = {"songs": len(items), "accept": sum(i["decision"] == "accept" for i in items),
               "review": sum(i["decision"] == "review" for i in items), "skip": sum(i["decision"] == "skip" for i in items),
               "by_basis": {b: sum(1 for i in items if i["basis"] == b) for b in sorted({str(i["basis"]) for i in items})},
               "performances_accept": sum(i["performances"] for i in items if i["decision"] == "accept"),
               "problems": len(problems)}
    return {"policy": POLICY, "summary": summary, "items": items, "problems": problems}


BASIS_LABELS = {"translation": "번역", "korean_usage": "한국 사용례", "ko_wikipedia": "한국어 위키백과",
                "official_korean_release": "공식 한국 발매", "user_review": "사용자 검수", "reading": "발음 표기"}


def render_review(decisions: dict, path: str) -> str:
    """Markdown table for the human review, most sung first."""
    lines = ["# 한국어 제목 후보 검수", "",
             f"결정 파일: `{path}`. 바꿀 곡은 `song_id`와 원하는 제목을 알려 주면 반영한다.",
             "표시: ✔ 출처 있음(accept) · ◇ 나무위키 이름이 조사 후보와 다름 · ✎ 부모 검토로 수정(조사 제안은 대안)", "",
             "| # | song_id | 원제 | 아티스트 | 가창 | 후보 | 근거 | 대안 |", "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for n, i in enumerate(sorted(decisions["items"], key=lambda i: -i["performances"]), 1):
        mark = "✔ " if i["decision"] == "accept" else ("◇ " if i.get("namu") else
                ("✎ " if (i.get("note") or "").startswith("parent review") else ""))
        basis = BASIS_LABELS.get(i["basis"], i["basis"] or "-")
        if i.get("namu"):
            basis = "나무위키"
        alts = ", ".join(a.get("title_ko") or "" if isinstance(a, dict) else str(a) for a in i["alternatives"])
        lines.append(f"| {n} | {i['song_id']} | {i['title_native']} | {', '.join(i['artists'])} | {i['performances']} | "
                     f"{mark}{i['title_ko'] or '-'} | {basis} | {alts} |")
    return "\n".join(lines) + "\n"


def read_review(path: Path) -> dict[int, str | None]:
    """song_id -> title from the 후보 column of an edited review file ('-' or empty: no title)."""
    titles = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 8 and cells[1].isdigit():
            value = REVIEW_MARKS.sub("", cells[5]).strip()
            titles[int(cells[1])] = None if value in ("", "-") else value
    return titles


def review_edits(decisions: dict, titles: dict[int, str | None]) -> list[dict]:
    """The rows the user changed, as manual user_review titles (None drops the song)."""
    edits = []
    for item in decisions["items"]:
        if item["song_id"] in titles and not same_text(titles[item["song_id"]], item["title_ko"]):
            edits.append({"song_id": item["song_id"], "title_ko": titles[item["song_id"]], "was": item["title_ko"]})
    return edits


def manifest(decisions: dict) -> str:
    body = {"policy": decisions["policy"], "catalog_instance_id": decisions["catalog_instance_id"],
            "accept": [{k: i[k] for k in ("song_id", "version", "title_ko")} for i in decisions["items"] if i["decision"] == "accept"]}
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def apply(conn, decisions: dict, *, write: bool) -> dict:
    identity = rows(conn, "SELECT id::text AS id, schema_version FROM catalog_instance").fetchone()
    if identity["schema_version"] != "catalog-v2" or identity["id"] != decisions.get("catalog_instance_id"):
        raise RuntimeError("Decision file was exported from a different catalog")
    if decisions.get("policy") != POLICY:
        raise RuntimeError("Unexpected decision file policy")
    bad = [i["song_id"] for i in decisions["items"] if i["decision"] not in DECISION_VALUES
           or (i["decision"] == "accept" and not HANGUL.search(i.get("title_ko") or ""))]
    if bad:
        raise RuntimeError(f"Invalid decisions for songs {bad}: decision must be accept/review/skip, accept needs a Korean title")
    accepted = [i for i in decisions["items"] if i["decision"] == "accept"]
    digest = manifest(decisions)
    operation_id = uuid.uuid5(NAMESPACE, identity["id"] + ":" + digest)
    if write:
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (731064923,))
    if conn.execute("SELECT 1 FROM catalog_imports WHERE operation_id=%s", (operation_id,)).fetchone():
        return {"status": "already_committed", "manifest_hash": digest}
    current = {r["id"]: r for r in rows(conn, "SELECT id, version, title_ko, archived_at FROM songs WHERE id=ANY(%s)"
                                         + (" FOR UPDATE" if write else ""), ([i["song_id"] for i in accepted],))}
    for i in accepted:
        row = current.get(i["song_id"])
        if row is None or row["archived_at"] or row["version"] != i["version"] or row["title_ko"]:
            raise RuntimeError(f"Song {i['song_id']} changed since export; re-export")
    summary = {"accept": len(accepted), "review": sum(i["decision"] == "review" for i in decisions["items"]),
               "skip": sum(i["decision"] == "skip" for i in decisions["items"])}
    if not write:
        return {"status": "would_commit", "manifest_hash": digest, **summary}
    if accepted:
        changed = conn.execute("""UPDATE songs s SET title_ko=x.title_ko
            FROM jsonb_to_recordset(%s::jsonb) x(id integer,version integer,title_ko text)
            WHERE s.id=x.id AND s.version=x.version AND s.title_ko IS NULL""",
            (Jsonb([{"id": i["song_id"], "version": i["version"], "title_ko": i["title_ko"]} for i in accepted]),)).rowcount
        if changed != len(accepted):
            raise RuntimeError("Songs changed during apply")
    import_id = conn.execute("""INSERT INTO catalog_imports(operation_id,catalog_instance_id,manifest_hash,source_kind,
            result_mapping,result_summary) VALUES (%s,%s,%s,'correction',%s,%s) RETURNING id""",
        (operation_id, identity["id"], digest, Jsonb([{"entity_type": "songs", "id": i["song_id"]} for i in accepted]),
         Jsonb({"kind": POLICY, **summary}))).fetchone()[0]
    changes = [{"entity_id": i["song_id"], "before_data": {"title_ko": None}, "after_data": {"title_ko": i["title_ko"]},
                "provenance": {"policy": POLICY, "basis": i["basis"], "confidence": i["confidence"],
                               "sources": i["sources"], "reviewed": True}} for i in accepted]
    if changes:
        conn.execute("""INSERT INTO catalog_changes(import_id,entity_type,entity_id,action,before_data,after_data,provenance)
            SELECT %s,'songs',x.entity_id,'update',x.before_data,x.after_data,x.provenance
            FROM jsonb_to_recordset(%s::jsonb) x(entity_id integer,before_data jsonb,after_data jsonb,provenance jsonb)""",
                     (import_id, Jsonb(changes)))
    return {"status": "committed", "manifest_hash": digest, "import_id": import_id, **summary}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare", help="Write research inputs (read-only DB access)")
    prep.add_argument("--top", type=int, default=200)
    prep.add_argument("--chunks", type=int, default=5)
    sub.add_parser("export", help="Merge research outputs into the decision file (read-only DB access)")
    sub.add_parser("review-import", help="Record the user's edits of review.md and the approval in the manual file")
    run = sub.add_parser("apply", help="Dry-run the reviewed decision file; --apply writes the accepted titles")
    run.add_argument("--apply", action="store_true")
    parser.add_argument("--round", type=int, default=1)
    args = parser.parse_args()
    work = REPORT_DIR / f"round-{args.round}"
    path = Path(str(DECISIONS).format(n=args.round))
    if args.command == "review-import":
        # The user edited review.md and approved it: keep a copy, record the edits, approve all.
        edited = work / "review.md"
        (work / "review.user-edited.md").write_text(edited.read_text(encoding="utf-8-sig"), encoding="utf-8")
        edits = review_edits(json.loads(path.read_text(encoding="utf-8")), read_review(edited))
        manual_path = MANUAL.with_name(MANUAL.name.format(n=args.round))
        manual = json.loads(manual_path.read_text(encoding="utf-8")) if manual_path.exists() else {}
        user = manual.setdefault("user_review", {})
        titles = {t["song_id"]: t for t in user.get("titles", [])}
        titles.update({e["song_id"]: {"song_id": e["song_id"], "title_ko": e["title_ko"]} for e in edits})
        user.update(date=datetime.now(UTC).strftime("%Y-%m-%d"), approved="all",
                    titles=sorted(titles.values(), key=lambda t: t["song_id"]),
                    note="The user edited review.md and approved every row (review-import).")
        manual_path.write_text(json.dumps(manual, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"edits": edits, "manual": str(manual_path.relative_to(ROOT))}, ensure_ascii=False, indent=2))
        return 0
    writing = args.command == "apply" and args.apply
    with psycopg.connect(migrate_catalog.load_connection(), connect_timeout=20) as conn:
        migrate_catalog.configure_transaction(conn, read_only=not writing)
        if args.command in ("prepare", "export"):
            songs = load_songs(conn)
            catalog_id = rows(conn, "SELECT id::text AS id FROM catalog_instance").fetchone()["id"]
            conn.rollback()
            if args.command == "prepare":
                picked = select(songs, wikidata_titles(), args.top)
                work.mkdir(parents=True, exist_ok=True)
                size = -(-len(picked) // args.chunks)
                for n in range(args.chunks):
                    chunk = picked[n * size:(n + 1) * size]
                    if chunk:
                        (work / f"input-{n + 1}.json").write_text(json.dumps(chunk, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
                (work / "conventions.json").write_text(json.dumps(conventions(songs), ensure_ascii=False, indent=1) + "\n",
                                                       encoding="utf-8")
                print(json.dumps({"dir": str(work.relative_to(ROOT)), "songs": len(picked),
                                  "performances": sum(p["performances"] for p in picked)}, ensure_ascii=False, indent=2))
                return 0
            picked = [x for p in sorted(work.glob("input-*.json")) for x in json.loads(p.read_text(encoding="utf-8"))]
            research = [x for p in sorted(work.glob("output-*.json")) for x in json.loads(p.read_text(encoding="utf-8-sig"))]
            namu = [x for p in sorted(work.glob("namu-found-*.json")) for x in json.loads(p.read_text(encoding="utf-8-sig"))]
            manual_path = MANUAL.with_name(MANUAL.name.format(n=args.round))
            manual = json.loads(manual_path.read_text(encoding="utf-8")) if manual_path.exists() else {}
            decisions = {**export(songs, picked, research, manual, namu), "catalog_instance_id": catalog_id,
                         "exported_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")}
            path.write_text(json.dumps(decisions, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            (work / "review.md").write_text(render_review(decisions, str(path.relative_to(ROOT))), encoding="utf-8")
            print(json.dumps({"file": str(path.relative_to(ROOT)), "review": str((work / "review.md").relative_to(ROOT)),
                              **decisions["summary"]}, ensure_ascii=False, indent=2))
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
