import { test, expect, type Page } from '@playwright/test'

const visit = (page: Page, route: string) => page.goto(route, { waitUntil: 'domcontentloaded' })

test.beforeEach(async ({ page }) => {
  // Start each scenario on a document already controlled by MSW. Activating a
  // worker halfway through the initial history can make Chrome reload on Back.
  await visit(page, '/')
  await expect(page.locator('#main-content')).toBeVisible()
  await page.waitForFunction(() => !!navigator.serviceWorker.controller)
})

test('favorites persist and artist filtering accepts Korean and full-width names', async ({
  page,
}) => {
  await visit(page, '/')
  await expect(page.locator('.favorite-grid .artist-tile')).toHaveCount(6)
  await page.getByRole('button', { name: 'HACHI 즐겨찾기', exact: true }).click()
  await expect(page.locator('.favorite-grid .artist-tile')).toHaveCount(5)
  await page.reload({ waitUntil: 'domcontentloaded' })
  await expect(page.locator('.favorite-grid .artist-tile')).toHaveCount(5)
  await visit(page, '/explore')
  await page.getByRole('textbox').fill('하치')
  await expect(page.locator('.artist-grid .artist-tile')).toHaveCount(1)
  await page.getByRole('button', { name: 'HACHI 즐겨찾기', exact: true }).click()
  await page.getByRole('textbox').fill('ＨＡＣＨＩ')
  await expect(page.locator('.artist-grid .artist-tile')).toHaveCount(1)
  await page.getByRole('link', { name: 'HACHI 아티스트 상세' }).click()
  await expect(page.getByRole('heading', { name: 'HACHI', exact: true })).toBeVisible()
})

test('search finds original artists and songs and seeks through the YouTube API', async ({
  page,
}) => {
  // Deterministic integration contract; real YouTube is checked separately.
  await page.addInitScript(() => {
    const state = { time: 0, destroyed: false }
    ;(window as any).__playerTest = state
    ;(window as any).YT = {
      Player: class {
        constructor(target: HTMLElement, options: any) {
          const frame = document.createElement('iframe')
          frame.title = 'YouTube video player'
          target.replaceWith(frame)
          setTimeout(() => options.events.onReady(), 25)
        }
        seekTo(t: number) {
          state.time = t
        }
        getCurrentTime() {
          return state.time
        }
        getDuration() {
          return 7261
        }
        getPlayerState() {
          return 2
        }
        destroy() {
          state.destroyed = true
        }
      },
    }
  })
  await visit(page, '/')
  await page.getByRole('textbox').fill('요루시카')
  await page.getByRole('button', { name: '검색', exact: true }).click()
  await expect(page.locator('.performance-result')).toHaveCount(3)
  await page.locator('.performance-result').filter({ hasText: '晴る' }).click()
  await expect(page).toHaveURL(/\/lives\/101\?t=1088/)
  await expect.poll(() => page.evaluate(() => (window as any).__playerTest.time)).toBe(1088)
  await page.getByRole('button', { name: /踊り子.*Vaundy/ }).click()
  await expect.poll(() => page.evaluate(() => (window as any).__playerTest.time)).toBe(587)
  await expect(page.locator('.setlist-song[aria-current="true"]')).toContainText('踊り子')
  await page.reload({ waitUntil: 'domcontentloaded' })
  await expect.poll(() => page.evaluate(() => (window as any).__playerTest.time)).toBe(587)
})

test('lyrics and concert overlays preserve route state, keyboard focus and back behavior', async ({
  page,
}) => {
  await visit(page, '/artists/2?tab=originals')
  await page.locator('.album-card').filter({ hasText: 'EAT THE PAST' }).click()
  await expect(page.locator('.track-section h2')).toHaveText('EAT THE PAST')
  await expect(page.locator('.album-card').filter({ hasText: 'EAT THE PAST' })).toHaveAttribute(
    'data-state',
    'on',
  )
  await visit(page, '/artists/1')
  await page.getByRole('tab', { name: '오리곡' }).click()
  const lyrics = page.getByRole('button', { name: '가사', exact: true }).first()
  await lyrics.click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await expect(page.getByRole('dialog')).toContainText('실제 곡의 가사가 아닙니다')
  await page.getByRole('dialog').getByRole('button', { name: '발음', exact: true }).click()
  await expect(page.locator('.lyric-pronunciation').first()).toBeVisible()
  await page.goBack()
  await expect(page.getByRole('dialog')).not.toBeVisible()
  await expect(page.getByRole('tab', { name: '오리곡' })).toHaveAttribute('data-state', 'active')
  await expect(lyrics).toBeFocused()
  await page.getByRole('tab', { name: '공연 정보' }).click()
  await page.locator('.concert-row').first().click()
  await expect(page.getByRole('dialog')).toContainText('실제 공연 일정이 아닙니다')
  await page.reload({ waitUntil: 'domcontentloaded' })
  await expect(page.getByRole('dialog')).toContainText('Zepp Shinjuku')
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog')).not.toBeVisible()
  await expect(page).toHaveURL(/tab=concerts$/)
})

test('calendar changes month, filters birthdays, and opens concerts', async ({ page, isMobile }) => {
  await visit(page, '/calendar?month=2026-09-01')
  await page.getByRole('button', { name: '전체 아티스트', exact: true }).click()
  await expect(page.locator('.month-event').filter({ hasText: 'KASUKA 생일' })).toBeVisible()
  await page.getByRole('button', { name: '공연', exact: true }).click()
  await expect(page.locator('.month-event').filter({ hasText: '샘플 공연' })).toHaveCount(0)
  await page.getByRole('button', { name: '생일', exact: true }).click()
  await expect(page.locator('.month-agenda')).toContainText('공연 또는 생일 필터를 켜 주세요.')
  await expect(page.locator('.month-event')).toHaveCount(0)
  await page.getByRole('button', { name: '생일', exact: true }).click()
  await page.getByRole('button', { name: '다음 달', exact: true }).click()
  await expect(page).toHaveURL(/month=2026-10-01/)
  await expect(page.locator('.month-agenda h2')).toContainText('10월 일정')
  await page.goBack()
  await expect(page.locator('.month-agenda h2')).toContainText('9월 일정')
  await page.getByRole('button', { name: '2026년 9월 9일, 1개 일정', exact: true }).click()
  await expect(page.locator('.calendar-agenda')).toContainText('KASUKA 생일')
  await expect(page.locator('.month-agenda')).toHaveCount(0)
  await page.getByRole('button', { name: '월 전체 보기' }).click()
  await expect(page.locator('.calendar-agenda')).toHaveCount(0)
  await expect(page.locator('.month-event').filter({ hasText: 'KASUKA 생일' })).toBeVisible()
  await page.getByRole('button', { name: '2026년 9월 9일, 1개 일정', exact: true }).click()
  await expect(page.locator('.calendar-agenda')).toContainText('KASUKA 생일')
  await page.getByRole('button', { name: '월 전체 보기' }).click()
  await page.getByRole('button', { name: '공연', exact: true }).click()
  await page.getByRole('button', { name: '오늘', exact: true }).click()
  await page.getByRole('button', { name: '월 전체 보기' }).click()
  await page.locator('.month-event').filter({ hasText: '샘플 공연' }).first().click()
  await expect(page.getByRole('dialog')).toContainText('샘플 일정')
  if (!isMobile) {
    await page.keyboard.press('Escape')
    await expect(page.getByRole('dialog')).toHaveCount(0)
    await page.locator('.cell-event-link').filter({ hasText: 'HACHI' }).first().click()
    await expect(page.getByRole('dialog')).toContainText('샘플 일정')
  }
})

test('system theme follows the device and explicit preference survives reload', async ({
  page,
}) => {
  await page.emulateMedia({ colorScheme: 'dark', reducedMotion: 'reduce' })
  await visit(page, '/settings')
  await expect(page.locator('html')).toHaveClass('dark')
  await page.getByRole('button', { name: '라이트', exact: true }).click()
  await expect(page.locator('html')).not.toHaveClass('dark')
  await page.reload({ waitUntil: 'domcontentloaded' })
  await expect(page.locator('html')).not.toHaveClass('dark')
  await page.getByRole('button', { name: '시스템', exact: true }).click()
  await expect(page.locator('html')).toHaveClass('dark')
  await page.emulateMedia({ colorScheme: 'light' })
  await expect(page.locator('html')).not.toHaveClass('dark')
})

test('error, empty, invalid routes and failed portraits stay usable', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', (e) => errors.push(e.message))
  await visit(page, '/explore?scenario=error')
  await expect(page.getByRole('button', { name: '다시 시도' })).toBeVisible()
  await visit(page, '/explore?scenario=empty')
  await expect(page.locator('[data-slot="empty"]')).toBeVisible()
  await visit(page, '/explore?scenario=broken-images')
  await expect(page.locator('.artist-grid .artist-tile')).toHaveCount(12)
  await expect(page.locator('.artist-grid [data-slot="avatar-fallback"]').first()).toBeVisible()
  await visit(page, '/artists/9999')
  await expect(page.getByRole('button', { name: '다시 시도' })).toBeVisible()
  await visit(page, '/not-a-page')
  await expect(page.getByRole('link', { name: /홈/ }).last()).toBeVisible()
  expect(errors).toEqual([])
})

test('main routes have no horizontal overflow or runtime errors', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', (e) => errors.push(e.message))
  for (const route of [
    '/',
    '/explore',
    '/artists/2?tab=originals',
    '/calendar',
    '/settings',
    '/search?q=HACHI',
  ]) {
    await visit(page, route)
    await expect(page.locator('h1')).toBeVisible()
    await expect(page.locator('.loading-grid')).toHaveCount(0)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  }
  expect(errors).toEqual([])
})
