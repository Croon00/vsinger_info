"""Conservative title/version decisions for explicit discography video linking."""
import re
import unicodedata
from functools import lru_cache


@lru_cache(maxsize=65536)
def normal(value):
    return ''.join(c for c in unicodedata.normalize('NFKC', value).casefold() if c.isalnum())


@lru_cache(maxsize=65536)
def versions(value):
    value = unicodedata.normalize('NFKC', value).casefold()
    groups = [('instrumental', r'instrumental|off[ -]?vocal|カラオケ|インスト'),
              ('live', r'live[ -]?ver|ライブ[版音源]|生演奏'),
              ('acoustic', r'acoustic|アコースティック|弾き語り'),
              ('piano', r'piano\s*(?:ver|version|cover)|ピアノ(?:版|バージョン|アレンジ)'),
              ('remix', r'remix|リミックス'), ('short', r'short[ -]?ver|shorts|ショート')]
    return frozenset(name for name, pattern in groups if re.search(pattern, value))


def title_matches(track, video, aliases):
    featured = re.search(r'\b(?:feat|ft)\.?\s*([^()（）/|【】]+)', track, re.I)
    key = normal(track[:featured.start()] + track[featured.end():] if featured else track)
    if featured:
        names = re.split(r'[,、&×]|\s+x\s+', featured.group(1))
        if any(normal(name) not in normal(video) for name in names if normal(name)):
            return False
    if not key or key not in normal(video):
        return False
    title = unicodedata.normalize('NFKC', video)
    if versions(track) != versions(video):
        return False
    if normal(title) == key:
        return True
    # Complete quoted title or a complete slash/pipe-delimited field, never a substring.
    fields = re.findall(r'[「『“"]([^」』”"]+)[」』”"]', title)
    fields += re.split(r'\s+[—–-]\s+|[/／|｜]', title)
    labels = r'official\s*(music\s*video|mv|audio|video|visualizer)|music\s*video|original\s*song|オリジナル(?:曲)?|歌ってみた|cover(?:ed)?(?:\s+by)?|MV|Audio|Lyric(?:s)?\s*video|にじさんじ|ホロライブ|hololive|オリジナルMV|公式'
    for field in fields + [title]:
        if featured:
            field = re.sub(r'\b(?:feat|ft)\.?\s*[^()（）/|【】]+', '', field, flags=re.I)
        field = re.sub(r'【[^】]*】|\[[^\]]*\]', '', field)
        for alias in sorted(aliases, key=len, reverse=True):
            if alias:
                field = re.sub(re.escape(alias), '', field, flags=re.I)
        field = re.sub(labels, '', field, flags=re.I)
        field = field.strip(' \t-–—:/／|｜()（）「」『』"')
        if normal(field) == key:
            return True
    return False


def choose(recording, videos):
    if any(re.search(r'live\s*album|live\s+at\b|ライブ(?:アルバム|音源)|concert\s*recording',
                     album, re.I) for album in recording.get('albums', [])):
        return dict(status='unresolved',reason='live_release_requires_version_review')
    candidates = []
    for video in videos:
        if video['channel_id'] not in recording['channels']:
            continue
        if video.get('availability') not in ('public', 'unlisted'):
            continue
        if (video.get('started_at') or video.get('scheduled')) and not video.get('ended_at'):
            continue
        mv = bool(re.search(r'(?<![A-Za-z])MV(?![A-Za-z])|original\s*mv|music\s*video|ミュージックビデオ', video['title'], re.I))
        official_song = bool(re.search(r'\bofficial\b|\boriginal\b|オリジナル', video['title'], re.I))
        distributed = 'Provided to YouTube by' in video.get('description', '')
        # Completed MV premieres may have liveStreamingDetails; singing archives do too.
        if video.get('started_at') and not (mv or distributed or official_song):
            continue
        seconds = video.get('duration_seconds')
        duration = (recording.get('duration_ms') or 0) / 1000
        if not seconds or not duration or abs(seconds-duration) > max(30, duration*.2):
            continue
        if not title_matches(recording['title_native'], video['title'], recording['aliases']):
            continue
        if re.search(r'歌枠|歌配信|カラオケ配信|耐久|切り抜き|reaction|踊ってみた|弾いてみた|演奏してみた|teaser|trailer|予告|告知|XFD|crossfade', video['title'], re.I):
            continue
        # Prefer a full MV, then a distributed audio, then a verified full song upload.
        rank = 2 if mv else (1 if distributed else 0)
        candidates.append((rank, video))
    if not candidates:
        return dict(status='unresolved', reason='no_verified_title_version_and_artist_match')
    highest = max(rank for rank, _ in candidates)
    best = {video['id']: video for rank, video in candidates if rank == highest}
    if len(best) != 1:
        return dict(status='unresolved', reason='multiple_verified_candidates', candidates=list(best))
    return dict(status='matched', video=next(iter(best.values())), reason='registered_owner_title_version_duration')
