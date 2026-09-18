// Run against the temporary v2 backend/front, without data mutations.
import { chromium } from '@playwright/test'
const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe' })
try {
  for (const width of [1440, 390]) {
    const page = await browser.newPage({ viewport: { width, height: 1000 } })
    const errors = []
    page.on('pageerror', e => errors.push(e.message))
    const apiErrors = []
    page.on('response', r => { if (r.url().includes('/api/') && r.status() >= 400) apiErrors.push(r.status()) })
    await page.goto('http://localhost:5198/artists/2', { waitUntil: 'domcontentloaded' })
    await page.locator('.live-card').first().waitFor({ timeout: 20000 })
    const first = await page.locator('.live-card').count()
    await page.getByRole('button', { name: '라이브 더 보기' }).click()
    await page.waitForFunction(() => document.querySelectorAll('.live-card').length === 12)
    await page.getByRole('tab', { name: '통계', exact: true }).click()
    await page.locator('.statistics-song-row').first().waitFor({ timeout: 20000 })
    const statsRows = await page.locator('.statistics-song-row').count()
    await page.goto('http://localhost:5198/calendar?month=2026-09-01', { waitUntil: 'domcontentloaded' })
    await page.locator('.month-cell').first().waitFor({ timeout: 20000 })
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)
    if (errors.length || apiErrors.length || first !== 6 || statsRows !== 10 || overflow) throw Error(JSON.stringify({width,errors,apiErrors,first,statsRows,overflow}))
    console.log(JSON.stringify({ width, firstPage: first, more:12, statisticsRows:statsRows, errors:0, overflow }))
    await page.close()
  }
} finally { await browser.close() }
