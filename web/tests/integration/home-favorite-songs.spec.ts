import { test, expect } from '@playwright/test'

test('home favorite carousels filter artists and place arrows beside thumbnails', async ({
  page,
}, info) => {
  await page.emulateMedia({ colorScheme: 'dark', reducedMotion: 'reduce' })
  await page.addInitScript(() =>
    localStorage.setItem('schedule-music-api:catalog-v1-favorites', '[42]'),
  )
  await page.route('https://i.ytimg.com/**', (route) => route.abort())
  const calls: URL[] = []
  const artist = { id: 42, name: 'Favorite Artist', sources: [], related_artist_ids: [42] }
  await page.route(/^http:\/\/localhost:5196\/api\//, async (route) => {
    const url = new URL(route.request().url())
    if (url.pathname === '/api/artists') return route.fulfill({ json: [artist] })
    if (url.pathname === '/api/artists/42') return route.fulfill({ json: artist })
    if (url.pathname === '/api/explore/songs') {
      calls.push(url)
      const prefix = url.searchParams.has('artist_ids') ? 'Favorite' : 'Recent'
      const items = Array.from({ length: 10 }, (_, i) => ({
        key: `recording:${i}`,
        title: `${prefix} Song ${i}`,
        title_ko: null,
        artist_name: artist.name,
        youtube_video_id: 'abcdefghijk',
        published_at: `2026-11-${String(20 - i).padStart(2, '0')}T00:00:00Z`,
      }))
      return route.fulfill({ json: { items, total: 10, offset: 0, limit: 10 } })
    }
    return route.fulfill({ json: { items: [], total: 0, offset: 0, limit: 6 } })
  })
  await page.goto('/')
  await expect(page.locator('.recent-songs')).toHaveCount(4)
  for (const kind of ['original', 'cover']) {
    const section = page
      .locator('.recent-songs')
      .filter({ has: page.locator(`#favorite-${kind}-heading`) })
    await expect(section.getByRole('listitem')).toHaveCount(10)
    await expect(section).toContainText('Favorite Song 0')
    expect(
      calls.some(
        (url) =>
          url.searchParams.get('kind') === kind && url.searchParams.get('artist_ids') === '42',
      ),
    ).toBe(true)
    const next = section.getByRole('button', { name: /다음$/ })
    await expect(next).toBeEnabled()
    const image = await section.locator('.recent-song-thumb').first().boundingBox()
    const arrow = await next.boundingBox()
    expect(Math.abs(arrow!.y + arrow!.height / 2 - (image!.y + image!.height / 2))).toBeLessThan(5)
    await next.click()
    await expect(section.getByRole('button', { name: /이전$/ })).toBeEnabled()
    await expect(section.getByRole('link', { name: '전체 보기' })).toHaveAttribute(
      'href',
      /song_artists=42/,
    )
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({
    path: `../outputs/original-backfill-2026-11-22/home-favorites-${info.project.name}.png`,
    fullPage: true,
  })
  await page.getByRole('link', { name: 'Favorite Artist 아티스트 상세' }).click()
  await page.getByRole('button', { name: 'Favorite Artist 즐겨찾기', exact: true }).click()
  await page.getByRole('button', { name: '뒤로가기', exact: true }).click()
  await expect(page).toHaveURL('/')
  await expect(page.locator('#favorite-original-track')).toHaveCount(0)
  await expect(page.locator('#favorite-cover-track')).toHaveCount(0)
  await expect(page.getByText('즐겨찾기한 아티스트가 없어요', { exact: true })).toHaveCount(2)
  await expect(page.locator('#recent-original-track').getByRole('listitem')).toHaveCount(10)
})
