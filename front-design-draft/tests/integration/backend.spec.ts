import { test, expect } from '@playwright/test'

// Fixtures follow existing backend DTOs. These verify real-mode HTTP paths;
// they deliberately do not use the design mock worker or any running database.
test('real mode connects existing contracts, isolates Spotify errors and omits unsupported birthdays', async ({
  page,
}) => {
  const calls: string[] = []
  const artist = {
    id: 42,
    name: 'HACHI',
    display_name: 'HACHI',
    agency: 'RK Music',
    related_artist_ids: [42],
    name_aliases: ['HACHI'],
    sources: [],
  }
  let spotifyReady = false
  await page.route(/^http:\/\/localhost:5196\/api\//, async (route) => {
    const url = new URL(route.request().url())
    calls.push(url.pathname + url.search)
    let data: unknown = []
    let status = 200
    if (url.pathname === '/api/v2/artists') data = [artist]
    else if (url.pathname.endsWith('/statistics')) data = {
      archives: 200, archivesWithSetlist: 180, performances: 900, uniqueSongs: 1, uniqueArtists: 1,
      songs: [{ key: 'song', title: 'Aggregated song', artist: 'Band', searchText: 'Aggregated song Band', count: 900, lastPerformedAt: '2026-09-01T00:00:00Z', rank: 1 }],
      artists: [{ key: 'band', name: 'Band', count: 900, percentage: 100 }],
      activity: [{ month: '2026-08', count: 200 }],
    }
    else if (url.pathname === '/api/v2/artists/42/lives')
      data = [
        {
          id: 700,
          artist_name: 'HACHI',
          video_title: 'Real contract live',
          youtube_url: 'https://youtu.be/abcdefghijk',
          broadcast_at: '2026-09-20T12:00:00Z',
          performances: [
            { id: 701, song_title: 'Song', original_artist: 'Band', start_seconds: 75 },
          ],
        },
      ]
    else if (url.pathname.endsWith('/discography')) {
      status = spotifyReady ? 200 : 409
      data = spotifyReady
        ? [
            {
              id: 'album-x',
              name: 'Real release',
              album_type: 'single',
              release_date: '2020-04',
              total_tracks: 1,
            },
          ]
        : { detail: 'Needs Spotify match' }
    } else if (url.pathname === '/api/v2/spotify/albums/album-x')
      data = {
        id: 'album-x',
        name: 'Real release',
        album_type: 'single',
        release_date: '2020-04',
        total_tracks: 1,
        tracks: [
          {
            id: 'track-x',
            name: 'Real song',
            disc_number: 1,
            track_number: 1,
            duration_ms: 123000,
          },
        ],
      }
    else if (url.pathname === '/api/songs/lyrics/by-spotify-tracks')
      data = [{ spotify_track_id: 'track-x', song_id: 987, has_lyrics: true }]
    else if (url.pathname === '/api/songs/987/lyrics')
      data = {
        song_id: 987,
        original_title: 'Real song',
        artist_name: 'HACHI',
        original_lyrics: 'Contract fixture text',
        translation_ko: '',
        pronunciation_ko: '',
        needs_review: true,
        lyrics_source_type: 'caption',
      }
    else if (url.pathname === '/api/v2/search')
      data = [
        {
          id: 701,
          archive_id: 700,
          artist_name: 'HACHI',
          song_title: 'Song',
          original_artist: 'Band',
          start_seconds: 75,
          performed_on: '2026-09-20',
          video_title: 'Real contract live',
          youtube_url: 'https://youtu.be/abcdefghijk',
        },
      ]
    else if (url.pathname === '/api/v2/concerts')
      data = [
        {
          id: 80,
          artist_id: 42,
          title: 'Ready concert',
          event_type: 'live_event',
          event_format: 'onsite',
          status: 'ready',
          starts_at: '2026-09-20T18:00:00+09:00',
        },
        {
          id: 81,
          artist_id: 42,
          title: 'Unreviewed concert',
          event_type: 'live_event',
          event_format: 'unknown',
          status: 'needs_review',
          starts_at: '2026-09-20T18:00:00+09:00',
        },
      ]
    else throw new Error(`Unexpected API: ${url.pathname}`)
    if (['/api/v2/artists/42/lives', '/api/v2/search', '/api/v2/concerts'].includes(url.pathname)) {
      const items = data as unknown[]
      data = {
        items,
        total: items.length,
        offset: 0,
        limit: Number(url.searchParams.get('limit') ?? 50),
      }
    }
    await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) })
  })
  await page.goto('/artists/42')
  await expect(page.locator('h1')).toHaveText('HACHI')
  await expect(page.locator('.live-card')).toContainText('Real contract live')
  expect(calls.some((p) => p.includes('/spotify/'))).toBe(false)
  expect(calls.filter((p) => p === '/api/v2/artists')).toHaveLength(1)
  expect(await page.evaluate(() => navigator.serviceWorker.controller)).toBeNull()
  await page.getByRole('tab', { name: '통계', exact: true }).click()
  await expect(page.locator('.statistics-song-row')).toContainText('Aggregated song')
  await expect(page.locator('.statistics-count').first()).toContainText('900')
  expect(calls.filter(p => p.includes('/lives?'))).toHaveLength(1)
  expect(calls.some(p => p.includes('all_records'))).toBe(false)
  await page.getByRole('tab', { name: '오리곡' }).click()
  await expect(page.getByText('아직 Spotify 아티스트가 연결되지 않았습니다.')).toBeVisible()
  await expect(page.locator('h1')).toHaveText('HACHI')
  spotifyReady = true
  await page.getByRole('button', { name: '다시 시도' }).click()
  await expect(page.locator('.track-row')).toContainText('Real song')
  await expect(page.locator('.track-section')).toContainText('2020년 4월')
  await page.getByRole('button', { name: '가사', exact: true }).click()
  await expect(page.getByRole('dialog')).toContainText('Contract fixture text')
  expect(calls).toContain('/api/songs/987/lyrics')
  await page.goto('/search?q=Band')
  await expect(page.locator('.performance-result')).toHaveCount(1)
  await expect(page.locator('.performance-result')).toHaveAttribute('href', '/lives/700?t=75')
  await page.goto('/calendar?month=2026-09-01')
  await expect(page.getByRole('button', { name: '생일', exact: true })).toHaveCount(0)
  await expect(
    page.getByRole('button', { name: '2026년 9월 20일, 1개 일정', exact: true }),
  ).toBeVisible()
  expect(calls.some((p) => p.startsWith('/api/draft/'))).toBe(false)
})
