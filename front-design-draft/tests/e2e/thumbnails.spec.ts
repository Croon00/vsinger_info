import { expect, test } from '@playwright/test'

test('archive thumbnails keep 16:9 and recover from unavailable image sizes', async ({ page, context }) => {
  // MSW forwards these requests from its worker, so intercept at context level.
  await context.route('https://i.ytimg.com/vi/**', async (route) => {
    const url = route.request().url()
    if (
      url.includes('jtzjXOVw7_Q') ||
      (url.includes('rCLT8jX9Xhw') && url.includes('maxresdefault'))
    ) {
      await route.fulfill({ status: 404, body: '' })
      return
    }
    const width = url.includes('maxresdefault') ? 120 : 320
    await route.fulfill({
      contentType: 'image/svg+xml',
      body: `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="180"><rect width="100%" height="100%" fill="gray"/></svg>`,
    })
  })
  await page.goto('http://127.0.0.1:5174/artists/1?tab=lives')
  await expect(page).toHaveURL('http://localhost:5174/artists/1?tab=lives')
  await expect(page.locator('.live-card')).toHaveCount(3)
  for (const id of [107, 108]) {
    const card = page.locator(`.live-card[href="/lives/${id}"]`)
    await card.scrollIntoViewIfNeeded()
    await expect(card.locator('img')).toHaveAttribute('src', /mqdefault\.jpg$/)
    await expect
      .poll(() => card.locator('img').evaluate((image) => (image as HTMLImageElement).naturalWidth))
      .toBe(320)
    const box = await card.locator('.live-thumb').boundingBox()
    expect(box!.width / box!.height).toBeCloseTo(16 / 9, 2)
  }
  const unavailable = page.locator('.live-card[href="/lives/101"]')
  await unavailable.scrollIntoViewIfNeeded()
  await expect(unavailable.locator('.live-thumb > img')).toHaveCount(0)
  await expect(unavailable).toContainText('Honeycomb Station #171')
  const box = await unavailable.locator('.live-thumb').boundingBox()
  expect(box!.width / box!.height).toBeCloseTo(16 / 9, 2)
})
