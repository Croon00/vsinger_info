import { describe, expect, it } from 'vitest'
import type { Artist } from '@/api/types'
import { sortArtists } from '@/lib/artist-sort'
const rows = [
  { id: 1, name: 'Zulu', display_name: '가수', roman: 'Zulu', youtube_channel_created_at: '2022-01-01', youtube_subscriber_count: 10 },
  { id: 2, name: 'Beta', display_name: '나비', roman: 'Beta', youtube_channel_created_at: '2020-01-01', youtube_subscriber_count: 100 },
  { id: 3, name: 'Alpha', display_name: '다솜', roman: 'Alpha', youtube_channel_created_at: null, youtube_subscriber_count: 0 },
  { id: 4, name: 'Delta', display_name: '라온', roman: 'Delta', youtube_subscriber_count: null },
] as Artist[]
const ids = (rows: Artist[]) => rows.map((a) => a.id)
describe('artist sort', () => {
  it('uses Korean names before native and romanized names', () => {
    expect(ids(sortArtists(rows, 'name'))).toEqual([1, 2, 3, 4])
  })
  it('sorts channel creation dates oldest first and leaves unknowns last', () => {
    expect(ids(sortArtists(rows, 'channel-created'))).toEqual([2, 1, 3, 4])
  })
  it('sorts subscribers descending, keeps zero before unknown, and ignores favorites', () => {
    expect(ids(sortArtists(rows, 'subscribers', new Set([4])))).toEqual([2, 1, 3, 4])
  })
  it('preserves the default favorite order without mutating source data', () => {
    expect(ids(sortArtists(rows, '', new Set([1])))).toEqual([1, 3, 2, 4])
    expect(ids(rows)).toEqual([1, 2, 3, 4])
  })
})
