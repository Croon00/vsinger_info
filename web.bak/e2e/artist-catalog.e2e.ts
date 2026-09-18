import { expect, test } from '@playwright/test'

test('bilingual card and both old artist URLs use one catalogue entry', async ({ page }) => {
  const artist = {
    id: 16, name: 'MIKAGE', display_name: '深影 (MIKAGE)', agency: 'RK Music',
    artist_kind: 'vtuber', show_in_youtube_lives: true, show_in_lyrics: true,
    show_in_spotify: true, sources: [], related_artist_ids: [16, 54], name_aliases: ['MIKAGE', '深影'],
  }
  await page.route('**/api-proxy/**', async route => {
    const url = new URL(route.request().url())
    let data: unknown = []
    if (url.pathname.endsWith('/artists')) {
      expect(url.searchParams.get('grouped')).toBe('true')
      data = [artist]
    }
    if (url.pathname.endsWith('/health')) data = { status: 'ok' }
    if (url.pathname.endsWith('/filters')) data = { songs: [], performers: [], original_artists: [] }
    await route.fulfill({ json: data })
  })
  await page.setViewportSize({ width: 412, height: 922 })
  await page.goto('/youtube-lives')
  await expect(page.locator('.artist-select-card')).toHaveCount(1)
  await expect(page.locator('.artist-select-card strong')).toHaveText('深影 (MIKAGE)')
  for (const id of [16, 54]) {
    await page.goto(`/youtube-lives/artists/${id}`)
    await expect(page.locator('.youtube-artist-hero h1')).toHaveText('深影 (MIKAGE)')
    await page.goto(`/profiles/${id}`)
    await expect(page.locator('.profile-hero h1')).toHaveText('深影 (MIKAGE)')
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(412)
  }
})
