import { test, expect } from '@playwright/test'

test('calendar colors events by artist and shows adjacent-month events', async ({ page }) => {
  await page.emulateMedia({ colorScheme: 'light' })
  const artists = [
    { id: 42, name: 'HACHI', theme_color: '#336699', birthday: '10-01', related_artist_ids: [42], sources: [] },
    { id: 43, name: 'Another', theme_color: '#ffcc00', birthday: '01-01', related_artist_ids: [43], sources: [] },
  ]
  const concerts = [
    { id: 79, artist_id: 42, title: 'August concert', starts_at: '2026-08-31T18:00:00+09:00' },
    { id: 80, artist_id: 42, title: 'September concert', starts_at: '2026-09-20T18:00:00+09:00' },
    { id: 81, artist_id: 42, title: 'November concert', starts_at: '2026-11-30T18:00:00+09:00' },
  ]
  await page.route(/^http:\/\/localhost:5196\/api\//, async (route) => {
    const url = new URL(route.request().url())
    if (url.pathname === '/api/artists') {
      await route.fulfill({ json: artists })
      return
    }
    if (url.pathname === '/api/concerts') {
      const start = url.searchParams.get('start')!
      const end = url.searchParams.get('end')!
      const items = concerts.filter((concert) => concert.starts_at.slice(0, 10) >= start && concert.starts_at.slice(0, 10) < end)
        .map((concert) => ({ ...concert, event_type: 'live_event', event_format: 'onsite', status: 'ready' }))
      await route.fulfill({ json: { items, total: items.length, offset: 0, limit: 100 } })
      return
    }
    throw new Error(`Unexpected API: ${url.pathname}`)
  })
  await page.goto('/calendar?month=2026-09-01')
  const august = page.getByRole('button', { name: '2026년 8월 31일, 1개 일정' }).locator('..')
  await expect(august.locator('.calendar-event-theme')).toHaveCount(1)
  await expect(august.locator('.cell-events')).toHaveCSS('opacity', '0.22')
  await expect(august.locator('.calendar-event-theme')).toHaveCSS('--calendar-event-color', '#336699')
  const lightBackground = await august.locator('.calendar-event-theme').evaluate((badge) => getComputedStyle(badge).backgroundColor)
  expect(lightBackground).not.toBe('rgb(51, 102, 153)')
  await page.emulateMedia({ colorScheme: 'dark' })
  await expect(page.locator('html')).toHaveClass(/dark/)
  const darkBackground = await august.locator('.calendar-event-theme').evaluate((badge) => getComputedStyle(badge).backgroundColor)
  expect(darkBackground).not.toBe(lightBackground)
  const october = page.getByRole('button', { name: '2026년 10월 1일, 1개 일정' }).locator('..')
  await expect(october.locator('.calendar-event-theme')).toHaveCount(1)
  await page.emulateMedia({ colorScheme: 'light' })
  await page.goto('/calendar?month=2026-12-01')
  const january = page.getByRole('button', { name: '2027년 1월 1일, 1개 일정' }).locator('..')
  await expect(january.locator('.calendar-event-theme')).toHaveCSS('--calendar-event-color', '#ffcc00')
  await expect(january.locator('.calendar-event-theme')).not.toHaveCSS('background-color', 'rgb(255, 204, 0)')
})

test('calendar keeps its grid and cached events while fetching adjacent months', async ({
  page,
  isMobile,
}) => {
  test.skip(isMobile, 'Month navigation by touch is covered in the mock browser test.')
  const requests: URL[] = []
  let octoberAttempts = 0
  let releaseOctober!: () => void
  const octoberGate = new Promise<void>((resolve) => {
    releaseOctober = resolve
  })
  await page.route(/^http:\/\/localhost:5196\/api\//, async (route) => {
    const url = new URL(route.request().url())
    if (url.pathname === '/api/artists') {
      await route.fulfill({
        json: [{ id: 42, name: 'HACHI', related_artist_ids: [42], sources: [] }],
      })
      return
    }
    if (url.pathname === '/api/concerts') {
      requests.push(url)
      const isOctober = url.searchParams.get('start') === '2026-09-01'
      if (isOctober) {
        await octoberGate
        if (++octoberAttempts === 1) {
          await route.fulfill({ status: 503, json: {} })
          return
        }
      }
      const start = url.searchParams.get('start')!
      const end = url.searchParams.get('end')!
      const events = [
        { id: 80, day: '2026-09-20' },
        { id: 82, day: '2026-10-10' },
      ]
      await route.fulfill({
        json: {
          items: events.filter(({ day }) => day >= start && day < end).map(({ id, day }) => ({
              id,
              artist_id: 42,
              title: `${day} concert`,
              event_type: 'live_event',
              event_format: 'onsite',
              status: 'ready',
              starts_at: `${day}T18:00:00+09:00`,
          })),
          total: 2,
          offset: 0,
          limit: 100,
        },
      })
      return
    }
    throw new Error(`Unexpected API: ${url.pathname}`)
  })
  await page.goto('/calendar?month=2026-09-01')
  await expect(page.getByRole('button', { name: '2026년 9월 20일, 1개 일정' })).toBeVisible()
  await page.getByRole('button', { name: '다음 달' }).click()
  await expect(page).toHaveURL(/month=2026-10-01/)
  await expect(page.locator('.month-grid')).toBeVisible()
  await expect(page.getByRole('button', { name: '2026년 10월 10일, 1개 일정' })).toBeVisible()
  await expect(page.getByText('일정 불러오는 중')).toHaveCount(0)
  await expect(page.locator('.loading-grid')).toHaveCount(0)
  await expect.poll(() => requests.length).toBe(2)
  releaseOctober()
  await expect(page.getByText('일정을 불러오지 못했어요')).toBeVisible()
  await expect(page.locator('.month-grid')).toBeVisible()
  await expect(page.getByRole('button', { name: '2026년 10월 10일, 1개 일정' })).toBeVisible()
  await page.getByRole('button', { name: '다시 시도' }).click()
  await expect(page.getByRole('button', { name: '2026년 10월 10일, 1개 일정' })).toBeVisible()
  expect(
    requests.map((url) => [url.searchParams.get('start'), url.searchParams.get('end')]),
  ).toEqual([
    ['2026-08-01', '2026-11-01'],
    ['2026-09-01', '2026-12-01'],
    ['2026-09-01', '2026-12-01'],
  ])
})

// Fixtures follow existing backend DTOs. These verify real-mode HTTP paths;
// they deliberately do not use the design mock worker or any running database.
test('real mode uses new catalog contracts, isolates errors and displays stored birthdays', async ({
  page,
}) => {
  const calls: string[] = []
  const artist = {
    id: 42,
    name: 'HACHI',
    display_name: '하치',
    birthday: '09-20',
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
    if (url.pathname === '/api/artists') data = [artist]
    else if (url.pathname.endsWith('/statistics')) data = {
      archives: 200, archivesWithSetlist: 180, performances: 900, uniqueSongs: 1, uniqueArtists: 1,
      songs: [{ key: 'song', title: 'Aggregated song', artist: 'Band', searchText: 'Aggregated song Band', count: 900, lastPerformedAt: '2026-09-01T00:00:00Z', rank: 1 }],
      artists: [{ key: 'band', name: 'Band', count: 900, percentage: 100 }],
      activity: [{ month: '2026-08', count: 200 }],
    }
    else if (url.pathname === '/api/artists/42/lives')
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
    else if (url.pathname === '/api/artists/42/albums') {
      status = spotifyReady ? 200 : 503
      data = spotifyReady
        ? [
            {
              id: '15',
              name: 'Real release',
              album_type: 'single',
              release_date: '2020-04',
              total_tracks: 1,
            },
          ]
        : { detail: 'Needs Spotify match' }
    } else if (url.pathname === '/api/albums/15')
      data = {
        id: '15',
        name: 'Real release',
        album_type: 'single',
        release_date: '2020-04',
        total_tracks: 1,
        tracks: [
          {
            id: '21',
            recording_id: 37, song_id: 987, has_lyrics: true,
            name: 'Real song',
            disc_number: 1,
            track_number: 1,
            duration_ms: 123000,
          },
        ],
      }
    else if (url.pathname === '/api/recordings/37/lyrics')
      data = {
        recording_id: 37,
        song_id: 987,
        original_title: 'Real song',
        artist_name: 'HACHI',
        original_lyrics: 'Contract fixture text',
        translation_ko: '',
        pronunciation_ko: '',
        needs_review: true,
        lyrics_source_type: 'caption',
      }
    else if (url.pathname === '/api/search')
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
    else if (url.pathname === '/api/concerts')
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
    if (['/api/artists/42/lives', '/api/search', '/api/concerts'].includes(url.pathname)) {
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
  expect(calls.filter((p) => p === '/api/artists')).toHaveLength(1)
  expect(await page.evaluate(() => navigator.serviceWorker.controller)).toBeNull()
  await page.getByRole('tab', { name: '통계', exact: true }).click()
  await expect(page.locator('.statistics-song-row')).toContainText('Aggregated song')
  await expect(page.locator('.statistics-count').first()).toContainText('900')
  expect(calls.filter(p => p.includes('/lives?'))).toHaveLength(1)
  expect(calls.some(p => p.includes('all_records'))).toBe(false)
  await page.getByRole('tab', { name: '발매곡' }).click()
  await expect(page.getByText('콘텐츠 서비스를 사용할 수 없어요. 잠시 후 다시 시도해 주세요.')).toBeVisible()
  await expect(page.locator('h1')).toHaveText('HACHI')
  spotifyReady = true
  await page.getByRole('button', { name: '다시 시도' }).click()
  await expect(page.locator('.track-row')).toContainText('Real song')
  await expect(page.locator('.track-section')).toContainText('2020년 4월')
  await page.getByRole('button', { name: '가사', exact: true }).click()
  await expect(page.getByRole('dialog')).toContainText('Contract fixture text')
  expect(calls).toContain('/api/recordings/37/lyrics')
  await page.goto('/search?q=Band')
  await expect(page.locator('.performance-result')).toHaveCount(1)
  await expect(page.locator('.performance-result')).toHaveAttribute('href', '/lives/700?t=75')
  await page.goto('/calendar?month=2026-09-01')
  await expect(page.getByRole('button', { name: '생일', exact: true })).toBeVisible()
  await expect(
    page.getByRole('button', { name: '2026년 9월 20일, 2개 일정', exact: true }),
  ).toBeVisible()
  expect(calls.some((p) => p.startsWith('/api/draft/') || p.startsWith('/api/songs/'))).toBe(false)
})

test('search filters ignore missing artist credits and keep navigation clickable', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  const artist = {
    id: 42, name: 'HACHI', display_name: '하치', related_artist_ids: [42], sources: [],
  }
  await page.route(/^http:\/\/localhost:5196\/api\//, async (route) => {
    const url = new URL(route.request().url())
    const data = url.pathname === '/api/artists' ? [artist]
      : url.pathname === '/api/artists/42' ? artist
      : url.pathname === '/api/search' ? {
          items: [
            { id: 1, archive_id: 10, artist_id: 42, artist_name: 'HACHI',
              song_title: 'First', original_artist: '', start_seconds: 10,
              youtube_url: 'https://youtu.be/abcdefghijk' },
            { id: 2, archive_id: 10, artist_id: 42, artist_name: 'HACHI',
              song_title: 'Second', original_artist: 'Band', start_seconds: 20,
              youtube_url: 'https://youtu.be/abcdefghijk' },
            { id: 3, archive_id: 10, artist_id: null, artist_name: '',
              song_title: 'Third', original_artist: 'Band', start_seconds: 30,
              youtube_url: 'https://youtu.be/abcdefghijk' },
          ], total: 3, offset: 0, limit: 50,
        }
      : { items: [], total: 0, offset: 0, limit: 12 }
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(data) })
  })
  await page.goto('/search?q=하치')
  await expect(page.locator('.performance-result')).toHaveCount(3)
  await page.getByRole('combobox', { name: '원곡 아티스트' }).click()
  await expect(page.getByRole('option', { name: 'Band' })).toBeVisible()
  await page.keyboard.press('Escape')
  await page.getByRole('combobox', { name: '부른 아티스트' }).click()
  await page.keyboard.press('Escape')
  expect(await page.evaluate(() => document.body.style.pointerEvents)).not.toBe('none')
  await page.getByRole('link', { name: 'HACHI 아티스트 상세' }).click()
  await expect(page).toHaveURL('/artists/42')
  expect(errors).toEqual([])
})
