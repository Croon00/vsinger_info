import type { Live } from '@/api/types'
import { normalize } from '@/lib/search'

export type SongSort = 'most' | 'least' | 'recent' | 'oldest'
export interface SongStatistic {
  key: string
  title: string
  artist: string
  searchText: string
  count: number
  lastPerformedAt: string | null
  rank: number
}
export interface ArtistStatistic {
  key: string
  name: string
  count: number
  percentage: number
}

// Preserve punctuation in identity keys: different songs must not be merged
// merely because their search-normalized labels happen to match.
const identity = (value: string) =>
  value.normalize('NFKC').trim().replace(/\s+/g, ' ').toLowerCase()
const timestamp = (value: string | null) => (value ? Date.parse(value) : NaN)
const compareTitle = (a: SongStatistic, b: SongStatistic) =>
  a.title.localeCompare(b.title, 'ja') || a.artist.localeCompare(b.artist, 'ja')

export function artistStatistics(lives: Live[]) {
  const songs = new Map<string, SongStatistic>()
  const artists = new Map<string, ArtistStatistic>()
  let performances = 0
  for (const live of lives) {
    for (const performance of live.performances) {
      performances++
      const artistKey = identity(performance.original_artist)
      const key = JSON.stringify([identity(performance.song_title), artistKey])
      const date = Number.isFinite(Date.parse(live.broadcast_at)) ? live.broadcast_at : null
      let song = songs.get(key)
      if (!song) {
        song = {
          key,
          title: performance.song_title || '곡명 미등록',
          artist: performance.original_artist || '아티스트 미등록',
          searchText: '',
          count: 0,
          lastPerformedAt: null,
          rank: 0,
        }
        songs.set(key, song)
      }
      song.count++
      song.searchText += ` ${normalize(
        [
          performance.song_title,
          performance.song_title_ko,
          performance.original_artist,
          performance.original_artist_ko,
        ]
          .filter(Boolean)
          .join(' '),
      )}`
      if (date && (!song.lastPerformedAt || timestamp(date) > timestamp(song.lastPerformedAt)))
        song.lastPerformedAt = date
      if (artistKey) {
        const artist = artists.get(artistKey) ?? {
          key: artistKey,
          name: performance.original_artist,
          count: 0,
          percentage: 0,
        }
        artist.count++
        artists.set(artistKey, artist)
      }
    }
  }
  const rankedSongs = [...songs.values()].sort((a, b) => b.count - a.count || compareTitle(a, b))
  for (const [i, song] of rankedSongs.entries()) {
    song.rank = i > 0 && rankedSongs[i - 1]!.count === song.count ? rankedSongs[i - 1]!.rank : i + 1
  }
  const rankedArtists = [...artists.values()]
    .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name, 'ja'))
    .map((artist) => ({
      ...artist,
      percentage: performances ? (artist.count / performances) * 100 : 0,
    }))
  return {
    archives: lives.length,
    archivesWithSetlist: lives.filter((live) => live.performances.length > 0).length,
    performances,
    uniqueSongs: songs.size,
    uniqueArtists: artists.size,
    songs: rankedSongs,
    artists: rankedArtists,
  }
}

export function filterAndSortSongs(songs: SongStatistic[], query: string, sort: SongSort) {
  const q = normalize(query.trim())
  return songs
    .filter((song) => !q || song.searchText.includes(q))
    .sort((a, b) => {
      if (sort === 'most' || sort === 'least') {
        const difference = sort === 'most' ? b.count - a.count : a.count - b.count
        return difference || compareTitle(a, b)
      }
      // Undated archives always follow dated records in either date order.
      if (!a.lastPerformedAt && b.lastPerformedAt) return 1
      if (a.lastPerformedAt && !b.lastPerformedAt) return -1
      const difference = timestamp(a.lastPerformedAt) - timestamp(b.lastPerformedAt)
      return (sort === 'recent' ? -difference : difference) || compareTitle(a, b)
    })
}
