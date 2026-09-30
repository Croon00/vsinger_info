import type { Album, Track } from '@/api/types'
import { formatDate, formatTrackLength } from '@/lib/dates'

/** A release belongs to exactly one group; appears-on wins over the album type. */
export type ReleaseGroup = 'album' | 'single' | 'appears'
export type ReleaseFilter = 'all' | ReleaseGroup

export const RELEASE_FILTERS: { value: ReleaseFilter; label: string }[] = [
  { value: 'all', label: '전체' },
  { value: 'album', label: '앨범' },
  { value: 'single', label: '싱글' },
  { value: 'appears', label: '참여' },
]
export const RELEASES_PAGE_SIZE = 24
export const HERO_PREVIEW_TRACKS = 5

const TYPE_LABELS: Record<string, string> = {
  album: '앨범',
  single: '싱글',
  ep: 'EP',
  compilation: '컴필레이션',
  other: '기타',
}

export function releaseTypeLabel(type: string) {
  return TYPE_LABELS[type] ?? '발매'
}

export function releaseGroup(album: Pick<Album, 'album_type' | 'is_primary'>): ReleaseGroup {
  if (album.is_primary === false) return 'appears'
  return album.album_type === 'single' || album.album_type === 'ep' ? 'single' : 'album'
}

export function releaseFilter(value: unknown): ReleaseFilter {
  return value === 'album' || value === 'single' || value === 'appears' ? value : 'all'
}

export function releaseCounts(albums: Album[]): Record<ReleaseFilter, number> {
  const counts = { all: albums.length, album: 0, single: 0, appears: 0 }
  for (const album of albums) counts[releaseGroup(album)]++
  return counts
}

export function filterReleases(albums: Album[], filter: ReleaseFilter) {
  return filter === 'all' ? albums : albums.filter((album) => releaseGroup(album) === filter)
}

/** The listing is newest first, so the first own release is the latest one. */
export function latestPrimaryRelease(albums: Album[]) {
  return albums.find((album) => album.is_primary !== false)
}

function trackCount(album: Album) {
  return album.tracks_loaded === false ? (album.total_tracks ?? 0) : album.tracks.length
}

/**
 * Card caption: year · type (· N tracks). Appears-on releases store only the credited
 * tracks, so their stored count is not the album's track count and is left out.
 */
export function releaseCardMeta(album: Album) {
  const year = /^\d{4}/.test(album.release_date) ? album.release_date.slice(0, 4) : ''
  const type = releaseTypeLabel(album.album_type)
  if (album.is_primary === false) return [year, `참여 ${type}`].filter(Boolean).join(' · ')
  const count = trackCount(album)
  return [year, type, count > 1 ? `${count}곡` : ''].filter(Boolean).join(' · ')
}

/** Total running time, or '' when any track length is unknown. */
export function releaseLength(tracks: Track[]) {
  const lengths = tracks.map((track) => track.duration_ms ?? 0)
  if (!lengths.length || lengths.some((ms) => ms <= 0)) return ''
  const total = lengths.reduce((sum, ms) => sum + ms, 0)
  if (lengths.length === 1) return formatTrackLength(total)
  const minutes = Math.max(1, Math.round(total / 60000))
  if (minutes < 60) return `${minutes}분`
  return minutes % 60 ? `${Math.floor(minutes / 60)}시간 ${minutes % 60}분` : `${minutes / 60}시간`
}

/** Detail caption: date (· N tracks · length). Only own releases have a full tracklist. */
export function releaseDetailMeta(album: Album) {
  const own = album.is_primary !== false
  return [
    formatDate(album.release_date),
    own && album.tracks.length > 1 ? `${album.tracks.length}곡` : '',
    own ? releaseLength(album.tracks) : '',
  ]
    .filter(Boolean)
    .join(' · ')
}

export function releaseLinkLabel(url: string) {
  try {
    return new URL(url).hostname === 'open.spotify.com' ? 'Spotify에서 열기' : '공식 릴리스'
  } catch {
    return '공식 릴리스'
  }
}

export function discGroups(tracks: Track[]) {
  const discs = new Map<number, Track[]>()
  for (const track of tracks) {
    const disc = track.disc_number ?? 1
    discs.set(disc, [...(discs.get(disc) ?? []), track])
  }
  return [...discs].map(([disc, items]) => ({ disc, tracks: items }))
}

export function isCurrentArtist(artist: { id?: number }, artistIds: number[]) {
  return artist.id != null && artistIds.includes(artist.id)
}

export function performsOn(track: Track, artistIds: number[]) {
  return (track.artists ?? []).some((artist) => isCurrentArtist(artist, artistIds))
}

/** Performer line is shown only when it names someone besides this artist. */
export function showsCredits(track: Track, artistIds: number[]) {
  const artists = track.artists ?? []
  return artists.length > 0 && !artists.every((artist) => isCurrentArtist(artist, artistIds))
}

/** A release mixes performers when a credited track does not include this artist. */
export function isMixedRelease(tracks: Track[], artistIds: number[]) {
  return tracks.some((track) => (track.artists?.length ?? 0) > 0 && !performsOn(track, artistIds))
}

export function lyricsKey(track: Track) {
  return String(track.lyrics_id ?? track.song_id ?? track.id)
}
