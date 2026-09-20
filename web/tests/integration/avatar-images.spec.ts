import { test, expect } from '@playwright/test'

test('avatar variants load at rendered size, defer offscreen images and survive replacement', async ({
  page,
}) => {
  let version = 'v1'
  const requests: string[] = []
  const artists = () =>
    Array.from({ length: 60 }, (_, i) => ({
      id: i + 1,
      name: 'Artist ' + String(i + 1).padStart(2, '0'),
      spotify_image_url: 'https://images.example.test/' + version + '/' + (i + 1) + '/512.webp',
      avatar_variants: Object.fromEntries(
        [128, 256, 512].map((s) => [
          s,
          'https://images.example.test/' + version + '/' + (i + 1) + '/' + s + '.webp',
        ]),
      ),
      sources: [],
    }))
  await page.route('**/api/v2/artists', (route) => route.fulfill({ json: artists() }))
  await page.route('https://images.example.test/**', (route) => {
    requests.push(route.request().url())
    return route.fulfill({
      contentType: 'image/svg+xml',
      body: '<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512"><rect width="512" height="512" fill="teal"/></svg>',
    })
  })
  await page.goto('/explore')
  const first = page.locator('.artist-avatar img').first()
  await expect(first).toBeVisible()
  await expect
    .poll(() => first.evaluate((el: HTMLImageElement) => el.naturalWidth))
    .toBeGreaterThan(0)
  const requested = Number((await first.getAttribute('src'))!.match(/(128|256|512)\.webp$/)![1])
  const required = await first.evaluate(
    (el) => el.getBoundingClientRect().width * window.devicePixelRatio,
  )
  expect(requested).toBe([128, 256, 512].find((s) => s >= required) ?? 512)
  expect(requests.some((url) => url.includes('/60/'))).toBe(false)
  await page.locator('.artist-avatar').last().scrollIntoViewIfNeeded()
  await expect(page.locator('.artist-avatar img').last()).toBeVisible()
  await expect.poll(() => requests.some((url) => url.includes('/60/'))).toBe(true)
  version = 'v2'
  await page.reload()
  await page.locator('.artist-avatar').first().scrollIntoViewIfNeeded()
  await expect(first).toHaveAttribute('src', /\/v2\//)
})
