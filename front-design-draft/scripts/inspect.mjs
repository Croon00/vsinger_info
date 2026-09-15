import { chromium } from '@playwright/test'
import { mkdir } from 'node:fs/promises'

await mkdir('docs/screenshots', { recursive: true })
const browser = await chromium.launch({
  executablePath:
    process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  headless: true,
})
for (const [name, width, height, colorScheme] of [
  ['desktop', 1440, 1000, 'light'],
  ['mobile', 390, 844, 'light'],
  ['dark', 1440, 1000, 'dark'],
]) {
  const context = await browser.newContext({ viewport: { width, height }, colorScheme })
  const page = await context.newPage()
  page.on('pageerror', (error) => console.log('PAGE ERROR', error.message))
  for (const [route, label] of [
    ['/', 'home'],
    ['/explore', 'explore'],
    ['/artists/1', 'artist'],
    ['/calendar', 'calendar'],
    ['/artists/1?tab=originals', 'originals'],
    ['/artists/1?tab=originals&lyrics=201', 'lyrics'],
    ['/artists/1?tab=concerts&event=301', 'concert'],
  ]) {
    if (name === 'dark' && label !== 'home') continue
    await page.goto(`http://127.0.0.1:5174${route}`, { waitUntil: 'domcontentloaded' })
    await page.locator('h1').waitFor()
    await page.waitForTimeout(1000)
    await page.screenshot({ path: `docs/screenshots/${name}-${label}.png`, fullPage: true })
    console.log(
      name,
      route,
      await page.locator('h1').innerText(),
      'overflow',
      await page.evaluate(() => document.documentElement.scrollWidth > innerWidth),
    )
  }
  await context.close()
}
await browser.close()
