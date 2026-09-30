import { describe, expect, it } from 'vitest'
import type { Album, Track } from '@/api/types'
import { formatTrackLength } from '@/lib/dates'
import {
  discGroups,
  filterReleases,
  isMixedRelease,
  latestPrimaryRelease,
  lyricsKey,
  releaseCardMeta,
  releaseCounts,
  releaseDetailMeta,
  releaseFilter,
  releaseGroup,
  releaseLength,
  releaseLinkLabel,
  showsCredits,
  performsOn,
} from '@/lib/discography'

const album = (overrides: Partial<Album>): Album => ({
  id: '1',
  artist_id: 42,
  name: 'Release',
  album_type: 'single',
  release_date: '2026-03-25',
  image_url: '',
  total_tracks: 1,
  tracks_loaded: false,
  tracks: [],
  source_url: '',
  is_sample: false,
  is_primary: true,
  ...overrides,
})
const track = (overrides: Partial<Track>): Track => ({
  id: 1,
  title: 'Track',
  title_ko: '',
  duration: '',
  has_lyrics: false,
  ...overrides,
})
const HACHI = { id: 42, name: 'HACHI', name_ko: '' }
const KMNZ = { id: 7, name: 'KMNZ', name_ko: '' }
const guest = { name: 'Batsu', name_ko: '' }

describe('release grouping', () => {
  const listing = [
    album({ id: 'amber', album_type: 'single', release_date: '2026-03-25' }),
    album({ id: 'revealia', album_type: 'album', total_tracks: 13, release_date: '2026-02-11' }),
    album({ id: 'freq', album_type: 'album', total_tracks: 1, is_primary: false }),
    album({ id: 'notes', album_type: 'compilation', total_tracks: 6, is_primary: false }),
    album({ id: 'ep', album_type: 'ep', total_tracks: 4 }),
  ]
  it('puts appears-on releases in their own group regardless of album type', () => {
    expect(listing.map(releaseGroup)).toEqual(['single', 'album', 'appears', 'appears', 'single'])
    expect(releaseCounts(listing)).toEqual({ all: 5, album: 1, single: 2, appears: 2 })
    expect(filterReleases(listing, 'appears').map((a) => a.id)).toEqual(['freq', 'notes'])
    expect(filterReleases(listing, 'all')).toBe(listing)
  })
  it('treats an unknown or missing group query as all', () => {
    expect(['album', 'single', 'appears'].map(releaseFilter)).toEqual(['album', 'single', 'appears'])
    expect([undefined, '', 'ep', ['single']].map(releaseFilter)).toEqual(['all', 'all', 'all', 'all'])
  })
  it('picks the newest own release for the hero', () => {
    const newestIsGuest = [album({ id: 'guest', is_primary: false }), ...listing]
    expect(latestPrimaryRelease(newestIsGuest)?.id).toBe('amber')
    expect(latestPrimaryRelease([album({ is_primary: false })])).toBeUndefined()
  })
})

describe('release captions', () => {
  it('shows the stored track count only for own multi-track releases', () => {
    expect(releaseCardMeta(album({ album_type: 'single' }))).toBe('2026 · 싱글')
    expect(releaseCardMeta(album({ album_type: 'album', total_tracks: 13 }))).toBe(
      '2026 · 앨범 · 13곡',
    )
    expect(
      releaseCardMeta(album({ album_type: 'album', total_tracks: 1, is_primary: false })),
    ).toBe('2026 · 참여 앨범')
    // Mock albums carry their tracks instead of total_tracks.
    const loaded = album({ tracks_loaded: undefined, total_tracks: undefined })
    loaded.tracks = [track({ id: 1 }), track({ id: 2 })]
    expect(releaseCardMeta(loaded)).toBe('2026 · 싱글 · 2곡')
    expect(releaseCardMeta(album({ release_date: '' }))).toBe('싱글')
  })
  it('formats track and total lengths like a music player', () => {
    expect(formatTrackLength(217800)).toBe('3:37')
    expect(formatTrackLength(123000)).toBe('2:03')
    expect(formatTrackLength(3723000)).toBe('1:02:03')
    expect(releaseLength([track({ duration_ms: 217800 })])).toBe('3:37')
    expect(releaseLength([track({ duration_ms: 1600000 }), track({ duration_ms: 1598916 })])).toBe(
      '53분',
    )
    expect(releaseLength([track({ duration_ms: 3600000 }), track({ duration_ms: 720000 })])).toBe(
      '1시간 12분',
    )
    expect(releaseLength([track({ duration_ms: 1800000 }), track({ duration_ms: 1800000 })])).toBe(
      '1시간',
    )
    expect(releaseLength([track({ duration_ms: 200000 }), track({})])).toBe('')
    expect(releaseLength([])).toBe('')
  })
  it('omits count and length from the detail of appears-on releases', () => {
    const tracks = [track({ id: 1, duration_ms: 200000 }), track({ id: 2, duration_ms: 100000 })]
    expect(releaseDetailMeta(album({ tracks }))).toBe('2026년 3월 25일 · 2곡 · 5분')
    expect(releaseDetailMeta(album({ tracks: [tracks[0]] }))).toBe('2026년 3월 25일 · 3:20')
    expect(releaseDetailMeta(album({ tracks, is_primary: false }))).toBe('2026년 3월 25일')
  })
  it('names the release link after its host', () => {
    expect(releaseLinkLabel('https://open.spotify.com/album/abc')).toBe('Spotify에서 열기')
    expect(releaseLinkLabel('https://linkco.re/t3pG1pgu')).toBe('공식 릴리스')
    expect(releaseLinkLabel('not a url')).toBe('공식 릴리스')
  })
})

describe('tracklist', () => {
  it('groups by disc only when the release has several discs', () => {
    const tracks = [
      track({ id: 1, disc_number: 1, track_number: 1 }),
      track({ id: 2, disc_number: 1, track_number: 2 }),
      track({ id: 3, disc_number: 2, track_number: 1 }),
    ]
    expect(discGroups(tracks).map((g) => [g.disc, g.tracks.map((t) => t.id)])).toEqual([
      [1, [1, 2]],
      [2, [3]],
    ])
    expect(discGroups([track({ id: 9 })])).toEqual([{ disc: 1, tracks: [track({ id: 9 })] }])
  })
  it('hides performers that are only this artist and marks mixed releases', () => {
    const ids = [42]
    const own = track({ artists: [HACHI] })
    const duet = track({ artists: [KMNZ, HACHI] })
    const other = track({ artists: [KMNZ, guest] })
    const unknown = track({ artists: [] })
    expect([own, duet, other, unknown].map((t) => showsCredits(t, ids))).toEqual([
      false,
      true,
      true,
      false,
    ])
    expect([own, duet, other].map((t) => performsOn(t, ids))).toEqual([true, true, false])
    expect(isMixedRelease([own, duet, unknown], ids)).toBe(false)
    expect(isMixedRelease([own, other], ids)).toBe(true)
    // Related IDs of the same artist count as this artist.
    expect(showsCredits(track({ artists: [{ id: 99, name: 'HACHI', name_ko: '' }] }), [42, 99])).toBe(
      false,
    )
  })
  it('keys lyrics by recording, then song, then track', () => {
    expect(lyricsKey(track({ id: 3, song_id: 2, lyrics_id: 1 }))).toBe('1')
    expect(lyricsKey(track({ id: 3, song_id: 2 }))).toBe('2')
    expect(lyricsKey(track({ id: 3 }))).toBe('3')
  })
})
