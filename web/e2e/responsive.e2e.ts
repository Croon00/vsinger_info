import { expect, test } from '@playwright/test'

test.beforeEach(async ({ page }) => {
  await page.route('**/api-proxy/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    let data: unknown = []
    if (path.endsWith('/health')) data = { status: 'ok' }
    if (path.endsWith('/artists')) data = Array.from({ length: 6 }, (_, i) => ({
      id: i + 1, name: `Artist ${i + 1}`, display_name: `아티스트 ${i + 1}`,
      artist_kind: 'vtuber', agency: 'RK Music', show_in_youtube_lives: true,
      show_in_lyrics: true, show_in_spotify: true, sources: [],
    }))
    if (path.endsWith('/artist-agencies')) data = [{ id: 1, name: 'RK Music' }]
    if (path.endsWith('/filters')) data = { songs: [], performers: [], original_artists: [] }
    await route.fulfill({ json: data })
  })
})

for (const width of [320, 375, 412, 768, 1024]) {
  test(`mobile layout and menu at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 922 })
    await page.goto('/youtube-lives')
    await expect(page.locator('.artist-select-card')).toHaveCount(6)
    await expect(page.locator('#desktop-sidebar')).toHaveCount(0)
    const bounds = await page.locator('.main-content').boundingBox()
    expect(bounds?.width).toBe(width)
    expect(bounds?.x).toBe(0)
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(width)
    const card = page.locator('.artist-select-card').first()
    const avatar = await card.locator('.artist-image').boundingBox()
    const name = await card.locator('strong').boundingBox()
    expect(avatar!.width).toBeGreaterThanOrEqual(80)
    expect(name!.y).toBeGreaterThanOrEqual(avatar!.y + avatar!.height)

    const menu = page.getByRole('button', { name: '메뉴 열기', exact: true })
    await menu.click()
    await expect(page.getByRole('dialog')).toBeVisible()
    await expect(page.getByRole('button', { name: '메뉴 닫기' })).toBeInViewport()
    await page.keyboard.press('Escape')
    await expect(page.getByRole('dialog')).toBeHidden()
    await expect(menu).toBeFocused()
    await menu.click()
    await page.getByRole('button', { name: '메뉴 닫기' }).click()
    await expect(page.getByRole('dialog')).toBeHidden()
    await menu.click()
    await page.locator('[data-slot="overlay"]').click({ position: { x: width - 20, y: 450 } })
    await expect(page.getByRole('dialog')).toBeHidden()
    await menu.click()
    await page.getByRole('dialog').getByRole('link', { name: '연동 설정' }).click()
    await expect(page).toHaveURL(/\/settings$/)
    await expect(page.getByRole('dialog')).toBeHidden()
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(width)
  })
}

test('desktop sidebar and resizing from an open mobile menu', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/youtube-lives')
  await expect(page.locator('#desktop-sidebar')).toBeVisible()
  await page.getByRole('button', { name: '사이드바 접기' }).click()
  await expect(page.locator('#desktop-sidebar')).toHaveCount(0)
  expect((await page.locator('.main-content').boundingBox())?.width).toBe(1440)
  await page.getByRole('button', { name: '사이드바 열기' }).click()
  await page.setViewportSize({ width: 412, height: 922 })
  await page.getByRole('button', { name: '메뉴 열기' }).click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await page.setViewportSize({ width: 1440, height: 900 })
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(page.locator('#desktop-sidebar')).toBeVisible()
})
