import { chromium, expect } from '@playwright/test'

// Real network/player verification; normal E2E tests use an API double.
const browser = await chromium.launch({
  executablePath:
    process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  headless: true,
})
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
  const errors = []
  page.on('pageerror', (error) => errors.push(error.message))
  await page.goto('http://127.0.0.1:5174/artists/1', { waitUntil: 'domcontentloaded' })
  await expect(page).toHaveURL('http://localhost:5174/artists/1')
  await expect(page.locator('.live-card')).toHaveCount(3)
  await expect
    .poll(() =>
      page
        .locator('.live-thumb img')
        .evaluateAll(
          (images) =>
            images.length === 3 &&
            images.every((image) => image.complete && image.naturalWidth > 120),
        ),
    )
    .toBe(true)
  console.log(
    'Thumbnails:',
    await page.locator('.live-thumb img').evaluateAll((images) =>
      images.map((image) => ({
        source: image.src,
        naturalWidth: image.naturalWidth,
        ratio: image.getBoundingClientRect().width / image.getBoundingClientRect().height,
      })),
    ),
  )
  await page.screenshot({ path: 'docs/screenshots/hachi-live-archives.png', fullPage: true })
  for (const id of [107, 108, 101]) {
    await page.goto(`http://localhost:5174/lives/${id}${id === 101 ? '?t=1088' : ''}`, {
      waitUntil: 'domcontentloaded',
    })
    await expect(page.locator('.player-host iframe')).toBeVisible({ timeout: 25000 })
    await expect(page.locator('.player-loading')).toHaveCount(0, { timeout: 25000 })
    await expect(page.locator('[data-slot="alert"]')).toHaveCount(0)
    const frame = page.frames().find((f) => f.url().startsWith('https://www.youtube.com/embed/'))
    if (!frame) throw new Error(`Archive ${id}: missing YouTube frame`)
    const read = () =>
      frame.evaluate(() => {
        const player = document.getElementById('movie_player')
        const video = document.querySelector('video')
        return {
          time: player?.getCurrentTime?.() ?? 0,
          state: player?.getPlayerState?.(),
          decodedFrames: video?.webkitDecodedFrameCount,
          paused: video?.paused,
        }
      })
    const play = frame.getByRole('button', { name: /^(동영상 재생|재생|Play|Play video)$/i }).first()
    await expect(play).toBeVisible({ timeout: 20000 })
    await play.click()
    await expect.poll(async () => (await read()).state, { timeout: 25000 }).toBe(1)
    const before = await read()
    await expect
      .poll(async () => (await read()).time, { timeout: 15000 })
      .toBeGreaterThan(before.time + 1)
    console.log(`Archive ${id} playing:`, await read())
    if (id === 101) {
      await page.getByRole('button', { name: /踊り子.*Vaundy/ }).click()
      await expect
        .poll(
          async () => {
            const { time, state } = await read()
            return state === 1 && time >= 587 && time < 600
          },
          { timeout: 25000 },
        )
        .toBe(true)
      console.log('Setlist seek to 587:', await read())
    }
    await page.screenshot({ path: `docs/screenshots/hachi-live-${id}-playing.png`, fullPage: true })
  }
  expect(errors).toEqual([])
  console.log('PASS: localhost redirect, 3 real thumbnails, 3 real video playbacks, setlist seek.')
} finally {
  await browser.close()
}
