import { expect, test } from '@playwright/test'

test('locks page scrolling while a selector menu is open', async ({ page, isMobile }) => {
  await page.setViewportSize({ width: isMobile ? 390 : 1440, height: isMobile ? 600 : 700 })
  await page.goto('/explore')
  await expect(page.locator('.artist-grid .artist-tile')).toHaveCount(12)

  const trigger = page.locator('[data-slot="select-trigger"][aria-label="소속사 필터"]')
  await trigger.click()
  const menu = page.locator('[data-slot="select-content"]')
  await expect(menu).toBeVisible()
  expect(await menu.getByRole('option').count()).toBeGreaterThan(1)

  await expect.poll(() => page.evaluate(() => getComputedStyle(document.body).overflow)).toBe('hidden')
  const scrollBefore = await page.evaluate(() => window.scrollY)
  await page.mouse.move(isMobile ? 300 : 800, 500)
  await page.mouse.wheel(0, 160)
  await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))))
  expect(await page.evaluate(() => window.scrollY)).toBe(scrollBefore)

  await menu.getByRole('option').last().click()
  await expect(menu).not.toBeVisible()
  await expect.poll(() => page.evaluate(() => getComputedStyle(document.body).overflow)).not.toBe('hidden')
})

test('restores the explore scroll position after tab and history navigation', async ({ page, isMobile }) => {
  await page.setViewportSize({ width: isMobile ? 390 : 1440, height: isMobile ? 844 : 700 })
  await page.goto('/explore')
  await expect(page.locator('.artist-grid .artist-tile')).toHaveCount(12)
  await page.locator('.page-enter').evaluate(async (element) => {
    await Promise.all(element.getAnimations().map((animation) => animation.finished))
  })

  await page.evaluate(() => window.scrollTo({ top: document.documentElement.scrollHeight, behavior: 'instant' }))
  const savedScroll = await page.evaluate(() => window.scrollY)
  expect(savedScroll).toBeGreaterThan(0)
  const dockBefore = isMobile ? await page.locator('.mobile-dock').boundingBox() : null

  await page.locator('.mobile-dock a[aria-label="홈"], .sidebar-nav-item[aria-label="홈"]').click()
  await page.locator('.mobile-dock a[aria-label="탐색"], .sidebar-nav-item[aria-label="탐색"]').click()
  await expect(page.locator('.artist-grid .artist-tile')).toHaveCount(12)
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(savedScroll)

  await page.locator('.artist-grid .artist-tile').last().locator('.artist-portrait-link').evaluate((link) => {
    (link as HTMLElement).click()
  })
  await expect(page).toHaveURL(/\/artists\/\d+$/)
  await page.goBack()
  await expect(page.locator('.artist-grid .artist-tile')).toHaveCount(12)
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(savedScroll)

  if (dockBefore) {
    const dockAfter = await page.locator('.mobile-dock').boundingBox()
    expect(dockAfter?.x).toBe(dockBefore.x)
    expect(dockAfter?.y).toBe(dockBefore.y)
  }
})
