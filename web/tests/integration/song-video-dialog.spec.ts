import { test, expect } from '@playwright/test'

for (const kind of ['cover', 'original']) {
  test(`${kind} song title opens an inline player and closing removes playback`, async ({
    page,
  }, info) => {
    await page.emulateMedia({ colorScheme: 'dark', reducedMotion: 'reduce' })
    await page.route('https://www.youtube.com/embed/**', (route) =>
      route.fulfill({
        contentType: 'text/html',
        body: '<html><body style="background:#111;color:white;font-family:sans-serif">YouTube player fixture</body></html>',
      }),
    )
    await page.route(/^http:\/\/localhost:5196\/api\//, (route) => {
      if (new URL(route.request().url()).pathname === '/api/artists')
        return route.fulfill({ json: [{ id: 1, name: 'Singer', sources: [] }] })
      return route.fulfill({
        json: {
          items: [
            {
              key: 'one',
              title: 'First song',
              title_ko: '첫 번째 곡',
              artist_name: 'Singer',
              youtube_video_id: 'abcdefghijk',
              view_count: 121000,
            },
            {
              key: 'two',
              title: 'Second song',
              title_ko: null,
              artist_name: 'Singer',
              youtube_video_id: '12345678901',
              view_count: 10000,
            },
            {
              key: 'three',
              title: 'Unlinked song',
              title_ko: null,
              artist_name: 'Singer',
              youtube_video_id: null,
              view_count: null,
            },
          ],
          total: 3,
          offset: 0,
          limit: 24,
        },
      })
    })
    await page.goto(`/explore?view=songs&kind=${kind}`)
    await expect(page.locator('iframe')).toHaveCount(0)
    const location = page.url()
    const first = page.getByRole('button', { name: '첫 번째 곡', exact: true })
    await first.click()
    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()
    await expect(dialog.getByRole('heading', { name: '첫 번째 곡' })).toBeVisible()
    const iframe = dialog.locator('iframe')
    await expect(iframe).toHaveAttribute('src', /\/embed\/abcdefghijk\?autoplay=1/)
    const url = new URL((await iframe.getAttribute('src'))!)
    expect(url.searchParams.get('origin')).toBe('http://localhost:5196')
    await expect(iframe).toHaveAttribute('allow', /autoplay/)
    expect(page.url()).toBe(location)
    const box = await dialog.boundingBox()
    expect(box!.x).toBeGreaterThanOrEqual(0)
    expect(box!.x + box!.width).toBeLessThanOrEqual(page.viewportSize()!.width)
    const frameBox = await iframe.boundingBox()
    expect(frameBox!.height).toBeGreaterThanOrEqual(200)
    await page.screenshot({
      path: `../outputs/song-player-2026-11-01/${kind}-${info.project.name}.png`,
    })
    await dialog.getByRole('button', { name: '닫기', exact: true }).click()
    await expect(page.locator('iframe')).toHaveCount(0)
    await expect(first).toBeFocused()
    const second = page.getByRole('button', { name: 'Second song', exact: true })
    await second.click()
    await expect(page.locator('iframe')).toHaveAttribute('src', /\/embed\/12345678901\?/)
    await page.getByRole('dialog').press('Escape')
    await expect(page.locator('iframe')).toHaveCount(0)
    await expect(second).toBeFocused()
    await expect(page.getByRole('button', { name: 'Unlinked song', exact: true })).toHaveCount(0)
  })
}
