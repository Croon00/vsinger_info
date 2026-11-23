"""Evidence-only original uploads; no model calls or name-only catalog merges."""
from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

from app.integrations.youtube_cover_rules import is_cover_title
from app.services.recording_youtube_match import choose, normal, versions, title_matches

POLICY = 'youtube-original-evidence-3'
ORIGINAL = re.compile(r'\boriginal\b(?!\s*(?:music\s*)?(?:MV|video)\b)|オリジナル(?:楽曲|曲|ソング)|오리지널\s*곡', re.I)
EXCLUDED = re.compile(r'歌枠|歌配信|カラオケ配信|耐久|切り抜き|reaction|踊ってみた|弾いてみた|演奏してみた|'
                      r'\blive\s+(?:video|performance|at)\b|ライブ映像|'
                      r'teaser|trailer|ティザー|トレーラー|予告|告知|XFD|crossfade|ダイジェスト|#shorts|short[\s._-]*ver|1\s*chorus|ワンコーラス|MV公開中|GB素材|'
                      r'self[\s_-]*cover|セルフ[\s・_-]*カバー|셀프\s*커버', re.I)
ORIGINAL_TAG = re.compile(r'(?<!\w)#(?:original(?:song|music)?|オリジナル(?:曲|楽曲)|오리지널곡)(?![A-Za-z])', re.I)
COVER_TAG = re.compile(r'(?<!\w)#(?:cover(?:song)?|歌ってみた|カバー)(?![A-Za-z])', re.I)
VOCAL = re.compile(r'^\s*[・●◆◇★☆■□▶▷◎\-＊*]*\s*'
    r'(?:vocals?|歌唱|歌|唄|ボーカル|singer|artist|アーティスト)'
    r'(?!\s+(?:editor|edit|mix|direction|recording)\b)'
    r'(?:\s*[&＆/・]\s*(?:movie|動画|music|lyrics?|作詞|作曲|絵|illustration|animation|映像))*'
    r'(?:\s*[:：\-–—]\s*|\s+)(.+)$', re.I)


class OriginalDecision(BaseModel):
    model_config = ConfigDict(extra='forbid')
    status: Literal['new_original', 'link_recording', 'review_required', 'not_eligible']
    reason: str
    title: str | None = None
    artist_ids: list[int] = Field(default_factory=list)
    recording_id: int | None = None
    recording_version: int | None = None


def eligible(video) -> bool:
    if video.published_at is None or video.published_at > datetime.now(UTC):
        return False
    if video.availability not in ('public', 'unlisted') or is_cover_title(video.title) or EXCLUDED.search(video.title):
        return False
    if video.duration_seconds is None or video.duration_seconds < 90:
        return False
    if (video.started_at or video.scheduled) and not video.ended_at:
        return False
    # Completed MV premieres may have streaming metadata, actual streams must
    # not become original recordings just because their description cites one.
    if video.started_at and not re.search(r'music\s*video|\bMV\b|オリジナル|original', video.title, re.I):
        return False
    return not versions(video.title)


def decide(video, scope) -> OriginalDecision:
    if not eligible(video):
        return OriginalDecision(status='not_eligible', reason='non_song_or_version_or_unavailable')
    owners = scope['owners']
    if not owners:
        return OriginalDecision(status='review_required', reason='registered_owner_required')
    # Existing releases can establish identity even when the upload title says
    # neither "original" nor "official". Use the established version/duration
    # matcher, and never overwrite an existing link or merge by a name alone.
    matched = [r for r in scope['recordings'] if choose(r, [video.model_dump(mode='json')])['status'] == 'matched']
    if matched:
        if len(matched) != 1:
            return OriginalDecision(status='review_required', reason='multiple_release_matches')
        recording = matched[0]
        if recording['official_video_id'] not in (None, video.id):
            return OriginalDecision(status='review_required', reason='existing_official_video_preserved')
        return OriginalDecision(status='link_recording', reason='registered_release_title_version_duration',
                                recording_id=recording['id'], recording_version=recording['version'])
    # Official/MV alone is not original-song evidence. New recordings need an
    # explicit original statement AND exact registered vocal identity.
    if COVER_TAG.search(video.description) or re.search(r'^\s*(?:本家(?:様)?|原曲)\s*[:：→]', video.description, re.M):
        return OriginalDecision(status='review_required', reason='description_cover_marker')
    stated = bool(ORIGINAL.search(video.title) or ORIGINAL_TAG.search(video.description))
    if not stated:
        for line in video.description.splitlines()[:20]:
            if re.match(r'^\s*(?:本作は|この曲は|This\s+is\s+(?:my|our|an?)\s+)?(?:オリジナル(?:楽曲|曲)|original\s+song)', line, re.I):
                quotes = re.findall(r'[「『“"]([^」』”"]+)[」』”"]', line)
                aliases = [alias for owner in owners for alias in owner['aliases']]
                if any(title_matches(title, video.title, aliases) for title in quotes):
                    stated = True
                    break
    if not stated:
        return OriginalDecision(status='review_required', reason='original_evidence_required')
    credited = set()
    credit_lines = [m[1] for line in video.description.splitlines() if (m := VOCAL.match(line))]
    for value in credit_lines:
        # Preserve unknown collaborators for review instead of attributing all
        # vocals to the channel owner. No fuzzy or substring name matching.
        value = re.sub(r'https?://\S+', '', value).strip()
        parenthetical = re.fullmatch(r'(.+?)\s*[（(](.+)[）)]', value)
        if parenthetical:
            prefix, suffix = parenthetical.groups()
            exact = [owner for owner in owners if normal(prefix) in {normal(a) for a in owner['aliases'] if a}]
            if len(exact) == 1:
                owner = exact[0]
                alternatives = {normal(a) for a in owner['aliases'] if a}
                group_members = owner.get('kind') == 'group' and not re.search(r'\bfeat|\bguest|\bwith\b|コラボ', suffix, re.I)
                if normal(suffix) in alternatives or group_members:
                    credited.add(owner['id'])
                    continue
        parts = re.split(r'\s*[&＆×、,／/]\s*', value)
        for part in parts:
            found = [o['id'] for o in owners if normal(part) in {normal(alias) for alias in o['aliases'] if alias}]
            if len(found) != 1:
                return OriginalDecision(status='review_required', reason='unresolved_vocal_credit')
            credited.add(found[0])
    if not credited:
        return OriginalDecision(status='review_required', reason='explicit_vocal_credit_required')
    quotes = re.findall(r'[「『“"]([^」』”"]+)[」』”"]', video.title)
    title = quotes[0] if len(quotes) == 1 else video.title
    return OriginalDecision(status='new_original', reason='explicit_original_and_registered_vocal',
                            title=title, artist_ids=sorted(credited))
