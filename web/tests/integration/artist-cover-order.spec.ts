import { test, expect } from '@playwright/test'

test('artist covers can be sorted and show view counts', async ({ page }) => {
  const orders: string[] = []
  const cover = (id: number, title: string, views: number | null, date: string) => ({
    id,
    youtube_video_id: `cover${String(id).padStart(6, '0')}`,
    youtube_url: `https://www.youtube.com/watch?v=cover${String(id).padStart(6, '0')}`,
    title,
    published_at: date,
    duration_seconds: 200,
    view_count: views,
  })
  await page.route(/^http:\/\/localhost:5196\/api\//, async (route) => {
    const url = new URL(route.request().url())
    if (url.pathname === '/api/artists')
      return route.fulfill({
        json: [{ id: 42, name: 'Artist', sources: [], related_artist_ids: [42] }],
      })
    if (url.pathname === '/api/artists/42/covers') {
      const order = url.searchParams.get('order') ?? ''
      orders.push(order)
      const items =
        order === 'views'
          ? [
              cover(2, 'Popular cover', 1234567, '2024-01-01T00:00:00Z'),
              cover(1, 'Quiet cover', null, '2025-01-01T00:00:00Z'),
            ]
          : [
              cover(1, 'Quiet cover', null, '2025-01-01T00:00:00Z'),
              cover(2, 'Popular cover', 1234567, '2024-01-01T00:00:00Z'),
            ]
      return route.fulfill({ json: { items, total: 2, offset: 0, limit: 12 } })
    }
    return route.fulfill({ json: { items: [], total: 0, offset: 0, limit: 12 } })
  })
  await page.goto('/artists/42?tab=covers')
  const cards = page.locator('.live-card')
  await expect(cards).toHaveCount(2)
  expect(orders.at(-1)).toBe('latest')
  await expect(cards.nth(1)).toContainText('조회수 123.4만회')
  await expect(cards.nth(0)).not.toContainText('조회수')
  await page.getByRole('combobox', { name: '커버 영상 정렬' }).click()
  await page.getByRole('option', { name: '조회수 높은순' }).click()
  await expect(cards.first()).toContainText('Popular cover')
  expect(orders.at(-1)).toBe('views')
  await page.getByRole('combobox', { name: '커버 영상 정렬' }).click()
  await page.getByRole('option', { name: '오래된순' }).click()
  await expect.poll(() => orders.at(-1)).toBe('oldest')
})
