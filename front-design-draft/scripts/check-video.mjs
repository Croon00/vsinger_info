import { chromium } from '@playwright/test'
const browser = await chromium.launch({
  executablePath:
    process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  headless: true,
})
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
page.on('pageerror', (error) => console.log('Runtime error:', error.message))
await page.goto('http://127.0.0.1:5174/lives/101?t=1088', { waitUntil: 'domcontentloaded' })
await page.locator('.setlist-song').first().waitFor()
await page.waitForTimeout(18000)
await page.screenshot({ path: 'docs/screenshots/desktop-live.png', fullPage: true })
console.log('Player loading:', await page.locator('.player-loading').count())
console.log('Player alert:', await page.locator('[data-slot="alert"]').allTextContents())
console.log(
  'Frames:',
  page.frames().map((f) => f.url()),
)
const frame = page.frames().find((f) => f.url().includes('youtube.com/embed/'))
if (frame) {
  console.log('YouTube UI:', (await frame.locator('body').innerText()).slice(0, 700))
  const read = () =>
    frame.evaluate(() => {
      const p = document.getElementById('movie_player')
      return { time: p?.getCurrentTime?.(), state: p?.getPlayerState?.() }
    })
  console.log('Initial playback:', await read())
  const play = frame.getByRole('button', { name: /play|재생/i }).first()
  if (await play.isVisible()) await play.click()
  await page.waitForTimeout(5000)
  console.log('After play:', await read())
  await page.getByRole('button', { name: /踊り子.*Vaundy/ }).click()
  await page.waitForTimeout(3000)
  console.log('After setlist seek (expected 587):', await read())
  await page.screenshot({ path: 'docs/screenshots/desktop-live-playing.png', fullPage: true })
}
await browser.close()
