import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mapArtist, mapEvent, mapLive, matchArtist, safeUrl, videoId } from '@/api/backend'
import { calendarEvents, formatDate } from '@/lib/dates'
import { clampTime } from '@/lib/youtube'

const rawArtist = {
  id: 42,
  name: 'HACHI',
  display_name: 'HACHI (Hachi)',
  name_aliases: ['ハチ'],
  related_artist_ids: [42, 99],
  sources: [],
}
const artist = mapArtist(rawArtist)
const rawPerformance = {
  id: 1,
  archive_id: 700,
  artist_name: 'HACHI',
  song_title: 'Song',
  original_artist: 'Band',
  start_seconds: 75,
  youtube_url: 'https://youtu.be/abcdefghijk',
  performed_on: '2026-09-20',
}
const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })
afterEach(() => vi.unstubAllGlobals())

describe('backend boundary mapping', () => {
  it('never presents display names as Korean or supplies mock birthdays', () => {
    expect(artist.display_name).toBe('')
    expect(artist.aliases).toContain('ハチ')
    expect(calendarEvents([{ ...artist, id: 5 }], [], 2026)).toEqual([])
    expect(matchArtist('ハチ', [artist])?.id).toBe(42)
    expect(matchArtist('HACHI', [artist, { ...artist, id: 43 }])).toBeUndefined()
  })
  it('validates external URLs and parses supported YouTube URLs', () => {
    expect(safeUrl('javascript:alert(1)')).toBe('')
    expect(videoId('https://youtube.com/live/abcdefghijk?t=20')).toBe('abcdefghijk')
    expect(videoId('https://youtube.com.evil.test/watch?v=abcdefghijk')).toBe('')
  })
  it('preserves unknown dates and durations without preventing timestamp seeks', () => {
    const live = mapLive({
      id: 700,
      youtube_url: 'https://youtu.be/abcdefghijk',
      artist_name: 'unmatched',
    })
    expect(live.artist_id).toBeNull()
    expect(live.broadcast_at).toBe('')
    expect(clampTime(75, live.duration_seconds)).toBe(75)
    expect(formatDate('')).toBe('날짜 미정')
    expect(formatDate('2020')).toBe('2020년')
    expect(formatDate('2020-04')).toBe('2020년 4월')
  })
  it('includes only reviewed, dated, identified offline events', () => {
    const row = {
      id: 80,
      artist_id: 99,
      title: 'Concert',
      starts_at: '2026-09-20T18:00:00+09:00',
      status: 'ready',
      event_type: 'live_event',
      event_format: 'onsite',
    }
    expect(mapEvent(row, [artist])?.artist_id).toBe(42)
    expect(mapEvent({ ...row, starts_at: '2026-09-20T18:00:00' }, [artist])?.starts_at).toBe(
      '2026-09-20',
    )
    expect(formatDate('2026-09-20', { hour: '2-digit', minute: '2-digit' })).not.toMatch(
      /12:00|00:00/,
    )
    for (const patch of [
      { status: 'needs_review' },
      { event_format: 'unknown' },
      { event_format: 'online' },
      { starts_at: 'invalid' },
      { artist_id: null },
      { event_type: 'ticket' },
    ])
      expect(mapEvent({ ...row, ...patch }, [artist])).toBeNull()
  })
})

describe('real API requests', () => {
  beforeEach(() => vi.resetModules())
  it('uses a single paged OR search and preserves unresolved singers', async () => {
    const calls: string[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (path: string) => {
        calls.push(path)
        if (path === '/api/v2/artists') return json([rawArtist])
        expect(new URL(path, 'http://localhost').searchParams.get('q')).toBe('Band')
        return json({
          items: [rawPerformance, { ...rawPerformance, id: 2, artist_name: 'Guest' }],
          total: 52,
          offset: 0,
          limit: 50,
        })
      }),
    )
    const { backendApi } = await import('@/api/backend')
    const result = await backendApi.search('Band')
    expect(result.total).toBe(52)
    expect(result.performances[1].artist.id).toBeNull()
    expect(result.performances[0].live.video_id).toBe('abcdefghijk')
    expect(calls).toHaveLength(2)
  })
  it('loads only a page of archive summaries, without requesting complete setlists', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (path: string) => {
        expect(path).toBe('/api/v2/artists/42/lives?offset=6&limit=6')
        return json({
          items: [{ id: 7, artist_id: 42, artist_name: 'HACHI', youtube_url: '' }],
          total: 200,
          offset: 6,
          limit: 6,
        })
      }),
    )
    const { backendApi } = await import('@/api/backend')
    const page = await backendApi.livePage(42, 6, 6)
    expect(page.total).toBe(200)
    expect(page.items[0].artist_id).toBe(42)
    expect(page.items[0].performances).toEqual([])
  })
  it('shares concurrent reads, isolates subscriber abort and retries failed requests', async () => {
    let complete!: (r: Response) => void
    const fetcher = vi.fn(
      () =>
        new Promise<Response>((resolve) => {
          complete = resolve
        }),
    )
    vi.stubGlobal('fetch', fetcher)
    const { cachedRead } = await import('@/api/read-cache')
    const controller = new AbortController()
    const cancelled = cachedRead('/api/v2/artists', controller.signal).catch((e) => e.name)
    const survivor = cachedRead('/api/v2/artists')
    controller.abort()
    complete(json([rawArtist]))
    expect(await cancelled).toBe('AbortError')
    expect(await survivor).toHaveLength(1)
    expect(fetcher).toHaveBeenCalledTimes(1)
    await cachedRead('/api/v2/artists')
    expect(fetcher).toHaveBeenCalledTimes(1)
    fetcher.mockImplementation(async () => json({}, 503))
    await expect(cachedRead('/failure')).rejects.toMatchObject({ status: 503 })
    await expect(cachedRead('/failure')).rejects.toMatchObject({ status: 503 })
    expect(fetcher).toHaveBeenCalledTimes(3)
  })
  it('maps Spotify string IDs to numeric lyrics IDs, not interchangeable IDs', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (path: string) =>
        path.includes('/spotify/albums/')
          ? json({
              id: 'album-x',
              name: 'Release',
              album_type: 'single',
              total_tracks: 1,
              tracks: [
                {
                  id: 'spotify-track-x',
                  name: 'Song',
                  disc_number: 1,
                  track_number: 1,
                  duration_ms: 123000,
                },
              ],
            })
          : json([{ spotify_track_id: 'spotify-track-x', song_id: 987, has_lyrics: true }]),
      ),
    )
    const { backendApi } = await import('@/api/backend')
    const album = await backendApi.album('album-x', 42)
    expect(album.tracks[0]).toMatchObject({
      id: 'spotify-track-x',
      song_id: 987,
      has_lyrics: true,
      duration: '02:03',
    })
  })
  it('distinguishes missing Spotify linkage, authentication and HTML fallback', async () => {
    const { request } = await import('@/api/http')
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => json({}, 409)),
    )
    await expect(request('/api/spotify/artists/42/discography')).rejects.toMatchObject({
      status: 409,
    })
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => json({}, 401)),
    )
    await expect(request('/api/artists')).rejects.toMatchObject({ status: 401 })
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () => new Response('<html>SPA</html>', { headers: { 'Content-Type': 'text/html' } }),
      ),
    )
    await expect(request('/api/artists')).rejects.toMatchObject({ status: 502 })
  })
})
