import { test, expect } from '@playwright/test'
test('song exploration switches kinds, orders, agency and search with pagination', async ({
  page,
}, info) => {
  await page.emulateMedia({ colorScheme: 'dark', reducedMotion: 'reduce' })
  const requests: URL[] = []
  await page.route(/^http:\/\/localhost:5196\/api\//, (route) => {
    const url = new URL(route.request().url())
    if (url.pathname === '/api/artists')
      return route.fulfill({
        json: [{ id: 1, name: 'Singer', display_name: '가수', agency: 'Group', sources: [] }],
      })
    requests.push(url)
    const offset = Number(url.searchParams.get('offset'))
    const kind = url.searchParams.get('kind')
    return route.fulfill({
      json: {
        items: [
          {
            key: kind === 'utawaku' ? 'song:1' : kind + ':' + offset,
            title: '花になって',
            title_ko: '꽃이 되어',
            artist_name: 'Singer',
            youtube_video_id: kind === 'utawaku' ? null : 'abcdefghijk',
            view_count: kind === 'utawaku' ? null : 121000,
            views_updated_at: '2026-11-01T00:00:00Z',
            performance_count: 128,
            artist_count: 12,
            archive_id: 1,
            start_seconds: 60,
            published_at: '2026-10-01T00:00:00Z',
          },
        ],
        total: 2,
        offset,
        limit: 24,
      },
    })
  })
  await page.goto('/explore')
  expect(requests.length).toBe(0)
  await page.getByRole('tab', { name: '곡 탐색', exact: true }).click()
  await expect(page.getByRole('heading', { name: '곡 탐색', exact: true })).toBeVisible()
  await expect(page.locator('.song-explore-row')).toHaveCount(1)
  await expect(page.locator('.song-explore-metric')).toContainText('128회')
  await expect(page.getByRole('link', { name: '리스트 열기', exact: true })).toHaveAttribute(
    'href',
    /\/search\?q=.*song_key=song:1.*agency=all/,
  )
  await page.getByRole('combobox', { name: '곡 소속사 필터' }).click()
  await page.getByRole('option', { name: 'Group', exact: true }).click()
  await expect.poll(() => requests.at(-1)?.searchParams.get('agency')).toBe('Group')
  await page.getByRole('combobox', { name: '곡 정렬 기준' }).click()
  await page.getByRole('option', { name: '부른 횟수 낮은 순', exact: true }).click()
  await expect.poll(() => requests.at(-1)?.searchParams.get('order')).toBe('low')
  await page.getByRole('tab', { name: '커버 곡', exact: true }).click()
  await expect(page.getByRole('combobox', { name: '곡 정렬 기준' })).toContainText('조회수 낮은 순')
  await expect(page.locator('.song-explore-metric')).toContainText('12.1만회')
  await page.getByRole('textbox', { name: '곡 또는 아티스트 이름', exact: true }).fill('꽃')
  await expect.poll(() => requests.at(-1)?.searchParams.get('q')).toBe('꽃')
  await page.getByRole('button', { name: '더보기', exact: true }).click()
  await expect(page.locator('.song-explore-row')).toHaveCount(2)
  await page.getByRole('tab', { name: '오리지널 곡', exact: true }).click()
  await expect(page.locator('.song-explore-row')).toHaveCount(1)
  await expect.poll(() => requests.at(-1)?.searchParams.get('kind')).toBe('original')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({
    path: `../outputs/song-explore-2026-11-01/${info.project.name}.png`,
    fullPage: true,
  })
  await page.reload()
  await expect(page.getByRole('tab', { name: '오리지널 곡', exact: true })).toHaveAttribute(
    'data-state',
    'active',
  )
})

test('song list reuses home search rows and selects singers beyond the first page', async ({
  page,
}, info) => {
  const searchRequests: URL[] = []
  const artists = [1, 2, 3].map((id) => ({
    id,
    name: `Singer ${id}`,
    display_name: `가수 ${id}`,
    agency: 'Group',
    sources: [],
  }))
  await page.route(/^http:\/\/localhost:5196\/api\//, (route) => {
    const url = new URL(route.request().url())
    if (url.pathname === '/api/artists') return route.fulfill({ json: artists })
    if (url.pathname === '/api/explore/song-performers') return route.fulfill({ json: artists })
    if (url.pathname === '/api/search') {
      searchRequests.push(url)
      const selected = url.searchParams.getAll('artist_ids').map(Number)
      const ids = selected.length ? selected : [1]
      return route.fulfill({
        json: {
          items:
            url.searchParams.get('end') === '2020-01-01'
              ? []
              : ids.map((id) => ({
                  id,
                  archive_id: 7,
                  artist_id: id,
                  artist_name: `Singer ${id}`,
                  artist_name_ko: `가수 ${id}`,
                  song_title: 'Song',
                  song_title_ko: '노래',
                  original_artist: 'Original',
                  original_artist_ko: '원곡 가수',
                  start_seconds: 60,
                  youtube_url: 'https://www.youtube.com/watch?v=abcdefghijk',
                  video_title: 'Singing archive',
                  broadcast_at: '2026-11-01T00:00:00Z',
                })),
          total: selected.length ? ids.length : 80,
          offset: 0,
          limit: 50,
        },
      })
    }
    return route.fulfill({
      json: {
        items: [
          {
            key: 'song:1',
            title: 'Song',
            artist_name: 'Original',
            performance_count: 80,
            artist_count: 3,
          },
        ],
        total: 1,
        offset: 0,
        limit: 24,
      },
    })
  })
  await page.goto('/explore?view=songs&song_agency=Group')
  await page.getByRole('link', { name: '리스트 열기', exact: true }).click()
  await expect(page.locator('.performance-result')).toHaveCount(1)
  await expect(page.locator('.performance-original')).toContainText('Original')
  await page.getByRole('combobox', { name: '부른 아티스트', exact: true }).click()
  await page.getByRole('option', { name: /Singer 3/ }).click()
  await page.keyboard.press('Escape')
  await expect.poll(() => searchRequests.at(-1)?.searchParams.getAll('artist_ids')).toEqual(['3'])
  expect(searchRequests.at(-1)?.searchParams.get('song_key')).toBe('song:1')
  expect(searchRequests.at(-1)?.searchParams.get('agency')).toBe('Group')
  await expect(page.locator('.performance-singer')).toContainText('Singer 3')
  await expect(page.locator('.performance-result')).toHaveAttribute('href', '/lives/7?t=60')
  await page.getByRole('combobox', { name: '부른 아티스트', exact: true }).click()
  await page.getByRole('option', { name: /Singer 1/ }).click()
  await page.keyboard.press('Escape')
  await expect
    .poll(() => searchRequests.at(-1)?.searchParams.getAll('artist_ids'))
    .toEqual(['3', '1'])
  await expect(page.locator('.performance-result')).toHaveCount(2)
  await page.emulateMedia({ colorScheme: 'dark', reducedMotion: 'reduce' })
  await page.getByRole('button', { name: '방송 기간 선택', exact: true }).click()
  await page.getByLabel('기간 연도', { exact: true }).selectOption('2026')
  await page.getByLabel('기간 월', { exact: true }).selectOption('10')
  const requestsBeforeDates = searchRequests.length
  await page.locator('[data-slot="range-calendar-trigger"][data-value="2026-10-01"]').click()
  await expect(page.getByRole('button', { name: '적용', exact: true })).toBeDisabled()
  await page.getByLabel('기간 월', { exact: true }).selectOption('11')
  await page.locator('[data-slot="range-calendar-trigger"][data-value="2026-11-01"]').click()
  await expect
    .poll(() =>
      page.locator('[data-slot="range-calendar-trigger"][data-selection-end]').evaluate((el) => {
        const probe = document.createElement('span')
        probe.style.backgroundColor = 'var(--primary)'
        document.body.appendChild(probe)
        const expected = getComputedStyle(probe).backgroundColor
        probe.remove()
        return getComputedStyle(el).backgroundColor === expected
      }),
    )
    .toBe(true)
  expect(searchRequests.length).toBe(requestsBeforeDates)
  const calendarBounds = await page.locator('[data-slot="popover-content"]').boundingBox()
  expect(calendarBounds!.x).toBeGreaterThanOrEqual(0)
  expect(calendarBounds!.x + calendarBounds!.width).toBeLessThanOrEqual(page.viewportSize()!.width)
  await page.screenshot({
    path: `../outputs/broadcast-period-2026-11-01/${info.project.name}.png`,
    fullPage: true,
  })
  await page.getByRole('button', { name: '적용', exact: true }).click()
  await expect.poll(() => searchRequests.at(-1)?.searchParams.get('start')).toBe('2026-10-01')
  await expect.poll(() => searchRequests.at(-1)?.searchParams.get('end')).toBe('2026-11-01')
  await page.reload()
  await expect(page.getByRole('combobox', { name: '부른 아티스트', exact: true })).toContainText(
    '2명',
  )
  await expect(page.getByRole('button', { name: '방송 기간 선택', exact: true })).toContainText(
    '2026.10.01 ~ 2026.11.01',
  )
  await expect(page.locator('.performance-result')).toHaveCount(2)
  await page.getByRole('button', { name: '방송 기간 선택', exact: true }).click()
  await page.getByRole('button', { name: '최근 30일', exact: true }).click()
  await page.getByRole('button', { name: '취소', exact: true }).click()
  expect(searchRequests.at(-1)?.searchParams.get('start')).toBe('2026-10-01')
  await page.getByRole('button', { name: '방송 기간 선택', exact: true }).click()
  await page.getByLabel('기간 연도', { exact: true }).selectOption('2020')
  await page.getByLabel('기간 월', { exact: true }).selectOption('1')
  await page.locator('[data-slot="range-calendar-trigger"][data-value="2020-01-01"]').click()
  await page.locator('[data-slot="range-calendar-trigger"][data-value="2020-01-01"]').click()
  await page.getByRole('button', { name: '적용', exact: true }).click()
  await expect(page.locator('.performance-result')).toHaveCount(0)
  await expect(page.getByRole('combobox', { name: '부른 아티스트', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '필터 초기화', exact: true }).click()
  await expect(page.getByRole('button', { name: '방송 기간 선택', exact: true })).toContainText(
    '방송 기간 전체',
  )
  await expect(page.locator('.performance-result')).toHaveCount(1)
  await page.getByRole('button', { name: '방송 기간 선택', exact: true }).click()
  await page.getByRole('button', { name: '최근 90일', exact: true }).click()
  await page.getByRole('button', { name: '적용', exact: true }).click()
  await expect.poll(() => searchRequests.at(-1)?.searchParams.get('start')).toBeTruthy()
  const recent = searchRequests.at(-1)!.searchParams
  expect((Date.parse(recent.get('end')!) - Date.parse(recent.get('start')!)) / 86400000).toBe(89)
  await page.getByRole('button', { name: '방송 기간 선택', exact: true }).click()
  await page.getByRole('button', { name: '전체 기간', exact: true }).click()
  await expect(page.getByRole('button', { name: '방송 기간 선택', exact: true })).toContainText(
    '방송 기간 전체',
  )
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({
    path: `../outputs/song-list-2026-11-01/${info.project.name}.png`,
    fullPage: true,
  })
})
