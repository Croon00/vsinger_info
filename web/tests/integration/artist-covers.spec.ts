import { test, expect } from '@playwright/test'

test('cover tab loads lazily, pages uploads, and opens YouTube', async ({ page }, info) => {
  await page.emulateMedia({ colorScheme: 'dark', reducedMotion: 'reduce' })
  let coverRequests = 0
  await page.route(/^http:\/\/localhost:5196\/api\//, async (route) => {
    const url = new URL(route.request().url())
    if (url.pathname === '/api/artists') return route.fulfill({ json: [
      { id: 42, name: '明透', display_name: '아스', agency: 'KAMITSUBAKI', sources: [], related_artist_ids: [42] },
    ] })
    if (url.pathname === '/api/artists/42/covers') {
      coverRequests++
      const offset = Number(url.searchParams.get('offset'))
      return route.fulfill({ json: {
        items: Array.from({ length: offset ? 1 : 12 }, (_, i) => ({
          id: offset + i + 1, youtube_video_id: 'abcdefghijk',
          youtube_url: 'https://www.youtube.com/watch?v=abcdefghijk',
          title: `花になって / cover 歌ってみた ${offset + i + 1}`,
          published_at: '2026-10-31T03:00:00Z', duration_seconds: 210,
        })), total: 13, offset, limit: 12,
      } })
    }
    return route.fulfill({ json: { items: [], total: 0, offset: 0, limit: 6 } })
  })
  await page.goto('/artists/42')
  await expect(page.getByRole('tab', { name: '라이브', exact: true })).toBeVisible()
  expect(coverRequests).toBe(0)
  await page.getByRole('tab', { name: '커버', exact: true }).click()
  await expect(page).toHaveURL(/tab=covers/)
  await expect(page.locator('[role=tabpanel][data-state=active] .live-card')).toHaveCount(12)
  const link = page.locator('[role=tabpanel][data-state=active] .live-card').first()
  await expect(link).toHaveAttribute('href', 'https://www.youtube.com/watch?v=abcdefghijk')
  await expect(link).toHaveAttribute('target', '_blank')
  await expect(link).toContainText('3:30')
  await page.getByRole('button', { name: '더보기', exact: true }).click()
  await expect(page.locator('[role=tabpanel][data-state=active] .live-card')).toHaveCount(13)
  await expect(page.getByRole('button', { name: '더보기', exact: true })).toHaveCount(0)
  expect(coverRequests).toBe(2)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: `../outputs/covers-2026-10-31/${info.project.name}.png`, fullPage: true })
  await page.reload()
  await expect(page.getByRole('tab', { name: '커버', exact: true })).toHaveAttribute('data-state', 'active')
})

test('cover errors can retry and empty results are explicit', async ({ page }) => {
  let fail = true
  await page.route(/^http:\/\/localhost:5196\/api\//, async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/artists') return route.fulfill({ json: [{ id: 42, name: 'Artist', sources: [] }] })
    if (path.endsWith('/covers') && fail) return route.fulfill({ status: 503, json: {} })
    return route.fulfill({ json: { items: [], total: 0, offset: 0, limit: 12 } })
  })
  await page.goto('/artists/42?tab=covers')
  await expect(page.getByRole('button', { name: /다시/ })).toBeVisible()
  fail = false
  await page.getByRole('button', { name: /다시/ }).click()
  await expect(page.getByText('등록된 커버 영상이 없습니다')).toBeVisible()
})
