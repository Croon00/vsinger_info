import { describe, expect, it } from 'vitest'
import type { Live, Performance } from '@/api/types'
import { artistStatistics, filterAndSortSongs } from '@/lib/artist-statistics'

const song = (
  id: number,
  title: string,
  artist: string,
  extra: Partial<Performance> = {},
): Performance => ({
  id,
  song_title: title,
  original_artist: artist,
  start_seconds: id * 30,
  ...extra,
})
const live = (id: number, date: string, performances: Performance[]): Live => ({
  id,
  artist_id: 1,
  broadcast_at: date,
  performances,
  title: '',
  title_ko: '',
  video_id: '',
  duration_seconds: 600,
  source_url: '',
})
const archives = [
  live(1, '2025-01-01T00:00:00Z', [
    song(1, 'Same', 'A'),
    song(2, 'Same', 'B'),
    song(3, 'Other', 'A'),
  ]),
  live(2, '2025-03-01T00:00:00Z', [
    song(4, 'Ｓａｍｅ', 'a', { song_title_ko: '같은 곡', original_artist_ko: '가수 에이' }),
    song(5, 'Same', 'A'),
  ]),
  live(3, '2025-04-01T00:00:00Z', []),
]

describe('artist setlist statistics', () => {
  it('counts each performance, merges normalized identities and separates different original artists', () => {
    const stats = artistStatistics(archives)
    expect([
      stats.archives,
      stats.archivesWithSetlist,
      stats.performances,
      stats.uniqueSongs,
      stats.uniqueArtists,
    ]).toEqual([3, 2, 5, 3, 2])
    expect(stats.songs[0]).toMatchObject({
      title: 'Same',
      artist: 'A',
      count: 3,
      rank: 1,
      lastPerformedAt: '2025-03-01T00:00:00Z',
    })
    expect(stats.artists.map((a) => [a.name, a.count, a.percentage])).toEqual([
      ['A', 4, 80],
      ['B', 1, 20],
    ])
    expect(stats.songs.slice(1).map((s) => s.rank)).toEqual([2, 2])
  })
  it('filters translated labels and full-width text without changing the overall ranks', () => {
    const { songs } = artistStatistics(archives)
    for (const query of ['같은 곡', '가수 에이', 'ＳＡＭＥ']) {
      expect(filterAndSortSongs(songs, query, 'most')[0]).toMatchObject({ title: 'Same', rank: 1 })
    }
    expect(filterAndSortSongs(songs, 'no match', 'most')).toEqual([])
  })
  it('supports four sort orders using the last performance, with missing dates last', () => {
    const { songs } = artistStatistics([...archives, live(4, 'invalid', [song(6, 'Undated', 'C')])])
    expect(filterAndSortSongs(songs, '', 'most')[0]?.count).toBe(3)
    expect(filterAndSortSongs(songs, '', 'least')[0]?.count).toBe(1)
    expect(filterAndSortSongs(songs, '', 'recent')[0]?.lastPerformedAt).toBe('2025-03-01T00:00:00Z')
    expect(filterAndSortSongs(songs, '', 'oldest')[0]?.lastPerformedAt).toBe('2025-01-01T00:00:00Z')
    for (const sort of ['recent', 'oldest'] as const)
      expect(filterAndSortSongs(songs, '', sort).at(-1)?.title).toBe('Undated')
  })
  it('retains every artist and uses all performances as the percentage denominator', () => {
    const stats = artistStatistics([
      live(
        1,
        '2026-01-01',
        Array.from({ length: 12 }, (_, i) => song(i, `Song ${i}`, `Artist ${i}`)),
      ),
    ])
    expect(stats.uniqueArtists).toBe(12)
    expect(stats.artists).toHaveLength(12)
    expect(stats.artists[0]?.percentage).toBeCloseTo(100 / 12)
    expect(stats.artists.reduce((total, a) => total + a.percentage, 0)).toBeCloseTo(100)
  })
  it('returns finite empty statistics and preserves punctuation in song identities', () => {
    expect(artistStatistics([])).toMatchObject({
      archives: 0,
      performances: 0,
      uniqueSongs: 0,
      uniqueArtists: 0,
      songs: [],
      artists: [],
    })
    const stats = artistStatistics([
      live(1, '2026-01-01', [song(1, 'A-B', 'C'), song(2, 'AB', 'C')]),
    ])
    expect(stats.uniqueSongs).toBe(2)
  })
})
