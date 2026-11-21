import { test, expect } from '@playwright/test'

test('artist originals include albumless songs, paginate, search and play', async ({
  page,
}, info) => {
  await page.emulateMedia({ colorScheme: 'dark', reducedMotion: 'reduce' })
  await page.route('https://www.youtube.com/**', (route) => route.fulfill({ body: '' }))
  await page.route('https://i.ytimg.com/**', (route) => route.abort())
  const calls: URL[] = []
  const song = (id: number, video: string | null = 'abcdefghijk') => ({
    key: `recording:${id}`,
    title: `Original ${id}`,
    title_ko: null,
    artist_name: 'Artist',
    youtube_video_id: video,
    view_count: 1234,
    published_at: '2026-11-21T00:00:00Z',
    views_updated_at: null,
    performance_count: null,
    artist_count: null,
    archive_id: null,
    start_seconds: null,
  })
  await page.route(/^http:\/\/localhost:5196\/api\//, async (route) => {
    const url = new URL(route.request().url())
    if (url.pathname === '/api/artists' || url.pathname === '/api/artists/983')
      return route.fulfill({
        json: url.pathname.endsWith('/983')
          ? { id: 983, name: 'Artist', sources: [], related_artist_ids: [983] }
          : [{ id: 983, name: 'Artist', sources: [], related_artist_ids: [983] }],
      })
    if (url.pathname === '/api/explore/songs') {
      calls.push(url)
      const offset = Number(url.searchParams.get('offset'))
      const items = url.searchParams.get('q')
        ? [song(30)]
        : offset
          ? [song(25, null)]
          : Array.from({ length: 24 }, (_, i) => song(i + 1))
      return route.fulfill({
        json: { items, total: url.searchParams.get('q') ? 1 : 25, offset, limit: 24 },
      })
    }
    return route.fulfill({ json: { items: [], total: 0, offset: 0, limit: 24 } })
  })
  await page.goto('/artists/983?tab=originals')
  await expect(page.getByRole('tab', { name: '오리지널 곡', exact: true })).toHaveAttribute(
    'aria-selected',
    'true',
  )
  const list = page.getByLabel('오리지널 곡 목록')
  await expect(list.getByRole('listitem')).toHaveCount(24)
  expect(calls[0]!.searchParams.get('artist_ids')).toBe('983')
  expect(calls[0]!.searchParams.get('kind')).toBe('original')
  expect(calls[0]!.searchParams.has('published_only')).toBe(false)
  await page.getByRole('button', { name: '더보기', exact: true }).click()
  await expect(list.getByRole('listitem')).toHaveCount(25)
  await expect(
    list.getByRole('listitem').filter({ hasText: 'Original 25' }).getByRole('button'),
  ).toHaveCount(0)
  await expect(page.getByRole('button', { name: '더보기', exact: true })).toHaveCount(0)
  await page.getByRole('button', { name: 'Original 1', exact: true }).click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await expect(page.locator('iframe')).toHaveAttribute('src', /embed\/abcdefghijk/)
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Original 1', exact: true })).toBeFocused()
  await page.getByRole('textbox', { name: '오리지널 곡 제목', exact: true }).fill('Original 30')
  await expect(list.getByRole('listitem')).toHaveCount(1)
  await expect(list).toContainText('Original 30')
  expect(calls.at(-1)!.searchParams.get('offset')).toBe('0')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({
    path: `../outputs/original-backfill-2026-11-22/artist-originals-${info.project.name}.png`,
    fullPage: true,
  })
})
