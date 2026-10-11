import { test, expect } from '@playwright/test'

test('album tracks show verified YouTube pills and keep unlinked versions separate', async ({
  page,
  isMobile,
}, info) => {
  await page.emulateMedia({ colorScheme: 'dark', reducedMotion: 'reduce' })
  const album = {
    id: '901',
    name: 'イニミニまいご',
    album_type: 'single',
    release_date: '2025-10-04',
    total_tracks: 2,
    is_primary: true,
    tracks: [
      {
        id: '1',
        recording_id: 1,
        name: 'イニミニまいご',
        duration_ms: 192000,
        disc_number: 1,
        track_number: 1,
        has_lyrics: false,
        youtube_url: 'https://www.youtube.com/watch?v=abcdefghijk',
      },
      {
        id: '2',
        recording_id: 2,
        name: 'イニミニまいご - Instrumental',
        duration_ms: 192000,
        disc_number: 1,
        track_number: 2,
        has_lyrics: false,
        youtube_url: null,
      },
    ],
  }
  await page.route(/^http:\/\/localhost:5196\/api\//, async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/artists')
      return route.fulfill({
        json: [{ id: 42, name: 'Artist', sources: [], related_artist_ids: [42] }],
      })
    if (path === '/api/artists/42/albums') return route.fulfill({ json: [album] })
    if (path === '/api/albums/901') return route.fulfill({ json: album })
    return route.fulfill({ json: { items: [], total: 0, offset: 0, limit: 6 } })
  })
  await page.goto('/artists/42?tab=originals&album=901')
  const pill = page.locator('.overlay-scroll .youtube-link')
  await expect(pill).toHaveCount(1)
  await expect(pill).toHaveAttribute('href', 'https://www.youtube.com/watch?v=abcdefghijk')
  await expect(pill).toHaveAttribute('target', '_blank')
  await expect(pill).toHaveAttribute('rel', 'noopener noreferrer')
  await expect(pill).toHaveCSS('color', 'rgb(255, 255, 255)')
  await expect(pill).toHaveCSS('background-color', 'rgb(8, 8, 8)')
  await expect(page.locator('.overlay-scroll')).toContainText('Instrumental')
  const box = await pill.boundingBox()
  expect(box!.x).toBeGreaterThanOrEqual(0)
  expect(box!.x + box!.width).toBeLessThanOrEqual(page.viewportSize()!.width)
  await page.screenshot({
    path: `../outputs/discography-youtube-2026-10-11/button-${info.project.name}.png`,
  })
  if (!isMobile) {
    await pill.hover()
    await expect(pill).toHaveCSS('background-size', '100% 100%')
    await page.screenshot({ path: '../outputs/discography-youtube-2026-10-11/button-hover.png' })
  }
})
