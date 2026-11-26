import { test, expect } from '@playwright/test'

test('original songs open lyrics and dock the player beside the list', async ({ page }) => {
  const song = (n: number, lyrics: number | null) => ({
    key: `recording:${n}`,
    title: `Song ${n}`,
    title_ko: null,
    artist_name: 'Artist',
    youtube_video_id: `video${String(n).padStart(6, '0')}`,
    view_count: 1000 * n,
    views_updated_at: null,
    performance_count: null,
    artist_count: null,
    archive_id: null,
    start_seconds: null,
    published_at: '2025-01-01T00:00:00Z',
    lyrics_recording_id: lyrics,
  })
  await page.route(/^https:\/\/www\.youtube\.com\//, (route) =>
    route.fulfill({ contentType: 'text/html', body: '<html></html>' }),
  )
  await page.route(/^http:\/\/localhost:5196\/api\//, async (route) => {
    const url = new URL(route.request().url())
    if (url.pathname === '/api/artists')
      return route.fulfill({
        json: [{ id: 42, name: 'Artist', sources: [], related_artist_ids: [42] }],
      })
    if (url.pathname === '/api/explore/songs')
      return route.fulfill({
        json: {
          items: [song(1, 501), song(2, null), song(3, 503)],
          total: 3,
          offset: 0,
          limit: 24,
        },
      })
    const lyrics = url.pathname.match(/^\/api\/recordings\/(\d+)\/lyrics$/)
    if (lyrics)
      return route.fulfill({
        json: {
          recording_id: Number(lyrics[1]),
          song_id: null,
          original_title: `Lyrics ${lyrics[1]}`,
          artist_name: 'Artist',
          original_lyrics: `first line ${lyrics[1]}\n\nsecond line`,
          translation_ko: '',
          pronunciation_ko: '',
          lyrics_source_url: 'https://www.youtube.com/watch?v=video000001',
          lyrics_source_type: 'video_description',
          needs_review: false,
        },
      })
    return route.fulfill({ json: { items: [], total: 0, offset: 0, limit: 12 } })
  })
  await page.goto('/artists/42?tab=originals')
  const rows = page.locator('.original-song-item')
  await expect(rows).toHaveCount(3)
  await expect(rows.nth(0).getByRole('button', { name: /가사 보기/ })).toBeVisible()
  await expect(rows.nth(1).getByRole('button', { name: /가사 보기/ })).toHaveCount(0)

  // The video dialog can show lyrics beside the player.
  await rows.nth(0).getByRole('button', { name: 'Song 1 재생' }).click()
  const video = page.getByRole('dialog')
  await expect(video.locator('iframe')).toHaveAttribute('src', /embed\/video000001/)
  await video.getByRole('button', { name: '가사 보기' }).click()
  await expect(video.getByRole('region', { name: '가사' })).toContainText('first line 501')
  await page.keyboard.press('Escape')
  await expect(video).toHaveCount(0)
  await rows.nth(1).getByRole('button', { name: 'Song 2 재생' }).click()
  await expect(page.getByRole('dialog').getByRole('button', { name: '가사 보기' })).toHaveCount(0)
  await page.keyboard.press('Escape')

  await rows
    .nth(0)
    .getByRole('button', { name: /가사 보기/ })
    .click()
  const dialog = page.getByRole('dialog')
  await expect(dialog).toContainText('first line 501')
  // Lyrics without translation or pronunciation have no language toggle.
  await expect(dialog.getByRole('group', { name: '가사 표시 언어' })).toHaveCount(0)
  await dialog.getByRole('button', { name: '들으면서 보기' }).click()
  await expect(dialog).toHaveCount(0)

  const panel = page.getByRole('complementary', { name: '재생 중인 곡과 가사' })
  await expect(panel).toContainText('first line 501')
  await expect(panel.locator('iframe')).toHaveAttribute('src', /embed\/video000001/)

  // While docked, another thumbnail plays in the panel instead of opening a dialog.
  await rows.nth(2).getByRole('button', { name: 'Song 3 재생' }).click()
  await expect(panel).toContainText('first line 503')
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await rows.nth(1).getByRole('button', { name: 'Song 2 재생' }).click()
  await expect(panel).toContainText('등록된 가사가 없습니다')

  // The panel stays in view while the page scrolls.
  const before = await panel.boundingBox()
  await page.mouse.wheel(0, 400)
  await page.waitForTimeout(200)
  const after = await panel.boundingBox()
  expect(Math.abs((after?.y ?? 0) - (before?.y ?? 0)) <= 400).toBe(true)

  await panel.getByRole('button', { name: '가사 패널 닫기' }).click()
  await expect(panel).toHaveCount(0)
})
