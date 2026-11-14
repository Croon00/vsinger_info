// Built-production smoke check. No live API, database, or media requests.
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { chromium } from '@playwright/test'

const origin = 'http://localhost:5198'
const server = spawn(process.execPath, ['server.mjs'], {
  env: { ...process.env, PORT: '5198', BACKEND_URL: '' }, stdio: 'pipe',
})
let browser
try {
  await new Promise((resolve, reject) => {
    server.stdout.once('data', resolve)
    server.once('error', reject)
    server.once('exit', (code) => reject(new Error(`Server exited: ${code}`)))
  })
  browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe' })
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true })
  // Permit only our local origin. The online UI may show the expected API error.
  await context.route('**/*', (route) => new URL(route.request().url()).origin === origin
    ? route.continue() : route.abort())
  const page = await context.newPage()
  await page.goto(origin)
  await page.waitForFunction(() => !!navigator.serviceWorker.controller)
  const manifest = await (await context.request.get(`${origin}/manifest.webmanifest`)).json()
  assert.equal(manifest.display, 'standalone')
  assert.equal(manifest.start_url, '/')
  for (const icon of manifest.icons) {
    const response = await context.request.get(origin + icon.src)
    assert.match(response.headers()['content-type'], /image\/png/)
    const bytes = await response.body()
    const size = Number(icon.sizes.split('x')[0])
    assert.equal(bytes.readUInt32BE(16), size)
    assert.equal(bytes.readUInt32BE(20), size)
  }
  for (const path of ['/sw.js', '/manifest.webmanifest', '/index.html']) {
    const response = await context.request.get(origin + path)
    assert.equal(response.headers()['cache-control'], 'no-cache')
  }
  assert.match((await context.request.get(`${origin}/manifest.webmanifest`)).headers()['content-type'], /application\/manifest\+json/)
  await context.setOffline(true)
  await page.goto(`${origin}/artists/123`)
  await page.getByRole('heading', { name: '인터넷 연결을 확인해 주세요' }).waitFor()
  assert.equal(await page.evaluate(async () => {
    try { await fetch('/api/artists'); return 'unexpected response' } catch { return 'network error' }
  }), 'network error')
  const cached = await page.evaluate(async () => {
    const cache = await caches.open('utamowa-offline-v1')
    return (await cache.keys()).map((request) => new URL(request.url).pathname)
  })
  assert.deepEqual(cached, ['/offline.html'])
  await context.setOffline(false)
  await page.getByRole('button', { name: '다시 시도' }).click()
  await page.waitForFunction(() => !!document.querySelector('#app')?.childElementCount)
  console.log('PWA smoke passed: manifest/icons, registration, cache headers, deep-link offline fallback, API bypass, reconnect.')
} finally {
  await browser?.close()
  server.kill()
}
