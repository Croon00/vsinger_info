import type { YouTubeLiveArchive } from '@/api/types'
import { searchKey } from './archiveFilters'

export type SongStatOccurrence = {
  archiveId: number; youtubeUrl: string; videoTitle: string | null
  broadcastAt: string | null; publishedAt: string | null; startSeconds: number; timestampText: string
}
export type SongStat = {
  title: string; titleKo: string | null; originalArtist: string | null; originalArtistKo: string | null
  tjNumbers: string[]
  count: number; occurrences: SongStatOccurrence[]
  artistCandidates: Record<string, { originalArtist: string; originalArtistKo: string | null; count: number }>
}

function normalizeSongTitle(value: string): string {
  let title = value
    .normalize('NFKC')
    .replace(/[\u200B-\u200D\uFEFF]/gu, ' ')
    .replace(/\s+/gu, ' ')
    .trim()

  // 댓글/셋리스트에서 흔히 붙는 표기를 제거한다. 실제 곡명은 표시용으로 유지한다.
  title = title
    .replace(/^\s*[「『【［(（]\s*/u, '')
    .replace(/\s*[」』】］)）]\s*$/u, '')
    .replace(/\s*[（(［\[]\s*(?:cover|\u6b4c\u3063\u3066\u307f\u305f|\u30ab\u30d0\u30fc|\u5f3e\u304d\u8a9e\u308a|acoustic(?:\s+(?:ver(?:sion)?|version))?|original|\u30aa\u30ea\u30b8\u30ca\u30eb)\s*[）)］\]]\s*$/iu, '')
    .replace(/\s*(?:[-\u2013\u2014|\uff5c/\uff0f:\uff1a]\s*|\s+)(?:cover|\u6b4c\u3063\u3066\u307f\u305f|\u30ab\u30d0\u30fc|\u5f3e\u304d\u8a9e\u308a|acoustic(?:\s+(?:ver(?:sion)?|version))?|original|\u30aa\u30ea\u30b8\u30ca\u30eb)\s*$/iu, '')

  return stripSetlistAttribution(title).trim()
}

const PERFORMANCE_NOTE = /(?:cover|\u6b4c\u3063\u3066\u307f\u305f|\u30ab\u30d0\u30fc|\u5f3e\u304d\u8a9e\u308a|\u30d4\u30a2\u30ce|\u30ae\u30bf\u30fc|acoustic|live|\u97f3\u6e90|inst(?:rumental)?|original|\u30aa\u30ea\u30b8\u30ca\u30eb)/iu
const JAPANESE_TEXT = /[\p{Script=Hiragana}\p{Script=Katakana}\p{Script=Han}]/u

function stripSetlistAttribution(value: string): string {
  let title = value

  // Drop a trailing performance note, but never parentheses that are part of
  // the actual title unless they clearly describe a cover/arrangement.
  while (true) {
    const match = title.match(/\s*[\uff08(]\s*([^\uff09)]{1,80})\s*[\uff09)]\s*$/u)
    if (!match || !PERFORMANCE_NOTE.test(match[1])) break
    title = title.slice(0, match.index).trim()
  }

  // Setlists frequently append the original artist or singer after a slash.
  // Strip it when it is explicitly a performance label, or when a Latin title
  // has a Japanese credit (for example, `rain stops, good-bye / \u306b\u304aP`).
  const slashMatch = title.match(/^(?<song>.+?)\s*[/\uff0f|\uff5c]\s*(?<credit>[^/\uff0f|\uff5c]{1,40})$/u)
  if (slashMatch?.groups) {
    const { song, credit } = slashMatch.groups
    if (PERFORMANCE_NOTE.test(credit) || (/[A-Za-z]/u.test(song) && JAPANESE_TEXT.test(credit))) {
      title = song.trim()
    }
  }

  return title
}

function songStatsKey(title: string): string {
  return searchKey(title)
}

function cleanSongTitle(value: string): string | null {
  if (isBroadcastChapter(value)) return null
  const title = normalizeSongTitle(value)
  if (!title) return null
  const withoutIndex = title.replace(/^(?:#\s*)?(?:제\s*)?\d+\s*(?:곡목?|曲目?)?\s*(?:[.．:：\-—)]\s*)+/u, '').trim()
  return withoutIndex && !isBroadcastChapter(withoutIndex) ? withoutIndex : null
}

function isBroadcastChapter(value: string): boolean {
  if (/^\d+$/u.test(value.normalize('NFKC').trim())) return false
  const label = value.normalize('NFKC')
    .replace(/[\u200B-\u200D\uFE0E\uFE0F\uFEFF]/gu, '')
    .replace(/^(?:\s|\p{P}|\p{S}|\p{N})+/gu, '')
    .trim()
  // Emoji, kaomoji, and punctuation alone are not song titles.
  if (!/[\p{L}\p{N}]/u.test(label)) return true
  // Match whole chapter labels, allowing a translated label in parentheses.
  // Do not reject real titles just because they contain words like "start".
  const chapter = label.replace(/\s*\([^()]*\)\s*$/u, '')
    .replace(/[\s\p{P}\p{S}]+$/gu, '').trim()
  return /^(?:(?:配信|放送|歌枠|本編)?\s*(?:開始|終了)|スタート|お知らせ|告知|宣伝|雑談|休憩|待機(?:画面|時間)?|準備中|オープニング|エンディング|[ABC]\s*パート|(?:今週|来週|今月|来月)の(?:予定|スケジュール)|スケジュール|시작|방송\s*(?:시작|종료)|공지(?:사항)?|잡담|휴식|대기(?:화면)?|[ABC씨]\s*파트|(?:이번|다음)\s*(?:주|달)\s*(?:스케줄|일정)|start|stream\s*(?:start|end)|opening|ending|intro|outro|announcements?|schedule|(?:free\s*)?talk|break|waiting)$/iu.test(chapter)
}
function addSongStatArtistCandidate(song: SongStat, originalArtist: string | null, originalArtistKo: string | null): void {
  if (!originalArtist) return
  const key = songStatsKey(originalArtist)
  if (!key) return
  const candidate = song.artistCandidates[key]
  if (candidate) {
    candidate.count += 1
    candidate.originalArtistKo ||= originalArtistKo
  }
  else song.artistCandidates[key] = { originalArtist, originalArtistKo, count: 1 }
}
export function buildSongStats(archives: YouTubeLiveArchive[], search: string, sort: 'asc' | 'desc'): SongStat[] {
  const songs = new Map<string, SongStat>()
  for (const archive of archives) {
    const entries = archive.performances?.length
      ? archive.performances.map((performance) => ({
          title: performance.song_title,
          titleKo: performance.song_title_ko,
          originalArtist: performance.original_artist,
          originalArtistKo: performance.original_artist_ko,
          tjNumber: performance.tj_number,
          startSeconds: performance.start_seconds,
          timestampText: performance.timestamp_text,
        }))
      : (archive.setlist ?? []).map((entry) => ({
          title: entry.title, titleKo: null, originalArtist: null, originalArtistKo: null,
          tjNumber: '등록X',
          startSeconds: timestampToSeconds(entry.timestamp), timestampText: entry.timestamp,
        }))
    for (const entry of entries) {
      const title = cleanSongTitle(entry.title)
      if (!title) continue
      const key = songStatsKey(title)
      const song = songs.get(key)
      if (song) {
        song.count += 1
        song.occurrences.push({
          archiveId: archive.id, youtubeUrl: archive.youtube_url, videoTitle: archive.video_title,
          broadcastAt: archive.broadcast_at, publishedAt: archive.published_at,
          startSeconds: entry.startSeconds, timestampText: entry.timestampText,
        })
        // 같은 곡의 표기가 여러 개면, 보통 더 짧은 쪽이 주석이 덜 붙은 제목이다.
        if (title.length < song.title.length) {
          song.title = title
          song.titleKo = entry.titleKo || song.titleKo
        }
        song.titleKo ||= entry.titleKo
        if (/^\d+$/u.test(entry.tjNumber) && !song.tjNumbers.includes(entry.tjNumber)) song.tjNumbers.push(entry.tjNumber)
        addSongStatArtistCandidate(song, entry.originalArtist, entry.originalArtistKo)
      }
      else {
        const song: SongStat = {
          title,
          titleKo: entry.titleKo,
          originalArtist: entry.originalArtist,
          originalArtistKo: entry.originalArtistKo,
          tjNumbers: /^\d+$/u.test(entry.tjNumber) ? [entry.tjNumber] : [],
          count: 1,
          occurrences: [{
          archiveId: archive.id, youtubeUrl: archive.youtube_url, videoTitle: archive.video_title,
          broadcastAt: archive.broadcast_at, publishedAt: archive.published_at,
          startSeconds: entry.startSeconds, timestampText: entry.timestampText,
          }],
          artistCandidates: {},
        }
        addSongStatArtistCandidate(song, entry.originalArtist, entry.originalArtistKo)
        songs.set(key, song)
      }
    }
  }
  const query = searchKey(search)
  return [...songs.values()]
    .map((song) => {
      const primaryArtist = Object.values(song.artistCandidates)
        .sort((left, right) => right.count - left.count)[0]
      if (primaryArtist) {
        song.originalArtist = primaryArtist.originalArtist
        song.originalArtistKo = primaryArtist.originalArtistKo
      }
      return song
    })
    .filter((song) => !query || [song.title, song.titleKo, song.originalArtist, song.originalArtistKo].some(value => searchKey(value || '').includes(query)))
    .sort((left, right) => sort === 'asc'
      ? left.count - right.count || left.title.localeCompare(right.title)
      : right.count - left.count || left.title.localeCompare(right.title))
}

function timestampToSeconds(value: string): number {
  const parts = value.split(':').map((part) => Number(part.trim()))
  if (!parts.length || parts.some((part) => !Number.isFinite(part))) return 0
  return parts.reduce((total, part) => total * 60 + part, 0)
}
