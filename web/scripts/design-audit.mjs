import { chromium } from '@playwright/test'
import { mkdir, writeFile } from 'node:fs/promises'

const directory = 'test-results/design-audit'
await mkdir(directory, { recursive: true })
const browser = await chromium.launch({
  executablePath: process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  headless: true,
})
const routes = [
  ['home', '/'],
  ['explore', '/explore'],
  ['artist', '/artists/1'],
  ['statistics', '/artists/1?tab=statistics'],
  ['originals', '/artists/2?tab=originals'],
  ['concerts', '/artists/1?tab=concerts'],
  ['calendar', '/calendar'],
  ['settings', '/settings'],
  ['search', '/search?q=HACHI'],
  ['lyrics', '/artists/1?tab=originals&lyrics=201'],
  ['concert-detail', '/artists/1?tab=concerts&event=301'],
  ['live', '/lives/101'],
]
const results = []
try {
  for (const [size, width, height, colorScheme] of [
    ['desktop', 1440, 1000, 'light'],
    ['mobile', 390, 844, 'light'],
    ['mobile-dark', 390, 844, 'dark'],
    ['compact', 320, 720, 'light'],
    ['tablet', 900, 900, 'dark'],
  ]) {
    const context = await browser.newContext({
      viewport: { width, height },
      colorScheme,
      isMobile: width <= 768,
      hasTouch: width <= 768,
    })
    // Verify viewer layout without relying on external playback availability.
    await context.addInitScript(() => {
      window.YT = {
        Player: class {
          constructor(target, options) {
            const frame = document.createElement('iframe')
            frame.title = 'YouTube video player'
            target.replaceWith(frame)
            setTimeout(() => options.events.onReady(), 20)
          }
          getCurrentTime() {
            return 0
          }
          getDuration() {
            return 7261
          }
          getPlayerState() {
            return 2
          }
          seekTo() {}
          playVideo() {}
          mute() {}
          unMute() {}
          destroy() {}
        },
      }
    })
    const page = await context.newPage()
    const errors = []
    page.on('pageerror', (error) => errors.push(error.message))
    for (const [name, route] of routes) {
      await page.goto(`http://localhost:5174${route}`, { waitUntil: 'domcontentloaded' })
      await page.locator('#main-content').waitFor()
      await page.waitForFunction(() => !document.querySelector('[aria-label="불러오는 중"]'))
      await page.evaluate(() => document.fonts.ready)
      // AvatarImage mounts after its image preload completes; awaiting page load
      // alone can capture the temporary initials fallback in otherwise healthy UI.
      await page.waitForFunction(
        () => [...document.querySelectorAll('.artist-avatar')].every(avatar => avatar.querySelector('img')?.complete),
        undefined,
        { timeout: 5000 },
      )
      await page.evaluate(async () => {
        const animations = document
          .getAnimations()
          .filter((animation) => animation.effect?.getComputedTiming().iterations !== Infinity)
        await Promise.all(animations.map((animation) => animation.finished.catch(() => {})))
      })
      const findings = await page.evaluate(() => ({
        overflow: document.documentElement.scrollWidth > innerWidth,
        outside: [
          ...document.querySelectorAll(
            '#main-content button, #main-content input, #main-content h1, #main-content h2',
          ),
        ]
          .filter(
            (el) =>
              el.checkVisibility({ checkVisibilityCSS: true }) &&
              !el.closest('[inert], .album-grid'),
          )
          .filter((el) => {
            const r = el.getBoundingClientRect()
            return r.right > innerWidth + 1 || r.left < -1
          })
          .map((el) => ({ text: el.textContent?.trim().slice(0, 50) })),
      }))
      results.push({ size, name, ...findings, errors: [...errors] })
      console.log(
        size,
        name,
        findings.overflow ? 'OVERFLOW' : 'ok',
        findings.outside.length ? findings.outside : '',
      )
      if (['desktop', 'mobile', 'mobile-dark'].includes(size))
        await page.screenshot({ path: `${directory}/${size}-${name}.png`, fullPage: true })
    }
    await context.close()
  }
} finally {
  await browser.close()
}
await writeFile(`${directory}/results.json`, JSON.stringify(results, null, 2))
