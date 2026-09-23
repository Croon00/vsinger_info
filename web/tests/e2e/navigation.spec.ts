import { expect, test } from '@playwright/test'

test('responsive navigation keeps named links, selected indicator and keyboard access', async ({ page }) => {
  await page.goto('/')
  await expect(page.locator('#main-content')).toBeVisible()
  await page.waitForFunction(() => !!navigator.serviceWorker.controller)
  await page.setViewportSize({ width: 1440, height: 900 })
  const sidebarLink = page.locator('.sidebar-nav-item').first()
  await expect(sidebarLink).toHaveCSS('font-size', '16px')
  await expect(sidebarLink.locator('svg')).toHaveCSS('width', '24px')
  await page.setViewportSize({ width: 900, height: 900 })
  await expect(sidebarLink).toHaveCSS('width', '56px')
  await expect(sidebarLink.locator('svg')).toHaveCSS('width', '28px')
  await expect(sidebarLink).toHaveAccessibleName('홈')
  await expect(sidebarLink.locator('span')).toHaveCount(0)

  await page.setViewportSize({ width: 390, height: 844 })
  const dock = page.getByRole('navigation', { name: '주 메뉴' })
  await expect(dock.getByRole('link')).toHaveCount(4)
  for (const name of ['홈', '탐색', '캘린더', '설정']) {
    const link = dock.getByRole('link', { name, exact: true })
    await expect(link).toHaveText('')
    await expect(link).toHaveCSS('width', '44px')
  }
  await dock.getByRole('link', { name: '탐색', exact: true }).click()
  await dock.getByRole('link', { name: '캘린더', exact: true }).click()
  await expect(page).toHaveURL(/\/calendar$/)
  await page.goBack()
  await expect(dock.getByRole('link', { name: '탐색', exact: true })).toHaveAttribute('aria-current', 'page')
  await expect.poll(async () => {
    const indicator = await page.locator('.dock-indicator').boundingBox()
    const selected = await dock.locator('[aria-current="page"]').boundingBox()
    return Math.abs(indicator!.x - selected!.x)
  }).toBeLessThan(1)
  await dock.getByRole('link', { name: '설정', exact: true }).focus()
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(/\/settings$/)
  await page.emulateMedia({ reducedMotion: 'reduce' })
  const duration = await page.locator('.dock-indicator').evaluate(el => parseFloat(getComputedStyle(el).transitionDuration))
  expect(duration).toBeLessThan(0.001)
  for (const width of [320, 768, 769, 1023, 1024]) {
    await page.setViewportSize({ width, height: 900 })
    await expect(page.locator(width <= 768 ? '.mobile-dock' : '.sidebar-nav-item').first()).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
  }
})
