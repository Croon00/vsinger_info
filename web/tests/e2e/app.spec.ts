import { test, expect, type Page } from '@playwright/test'

const visit = (page: Page, route: string) => page.goto(route, { waitUntil: 'domcontentloaded' })
const recordCalendarMonthAnimations = (page: Page) =>
  page.evaluate(() => {
    const frames: string[][] = []
    ;(window as Window & { calendarMonthFrames: string[][] }).calendarMonthFrames = frames
    const animate = Element.prototype.animate
    Element.prototype.animate = function (keyframes, options) {
      if (this.classList.contains('calendar-month-surface') && Array.isArray(keyframes))
        frames.push(keyframes.map((frame) => String(frame.transform)))
      return animate.call(this, keyframes, options)
    }
  })

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
  await expect(page.locator('.favorite-grid button')).toHaveCount(0)
  await visit(page, '/explore')
  const artistNames = page.locator('.artist-grid .artist-name-link h3')
  await expect(artistNames).toHaveCount(12)
  const initialOrder = await artistNames.allTextContents()
  const hachiFavorite = page.getByRole('button', { name: 'HACHI 즐겨찾기', exact: true })
  await hachiFavorite.click()
  await expect(hachiFavorite).toHaveAttribute('aria-pressed', 'false')
  expect(await artistNames.allTextContents()).toEqual(initialOrder)
  await visit(page, '/')
  await expect(page.locator('.favorite-grid .artist-tile')).toHaveCount(5)
  await page.reload({ waitUntil: 'domcontentloaded' })
  await expect(page.locator('.favorite-grid .artist-tile')).toHaveCount(5)
  await visit(page, '/explore')
  await expect(artistNames).toHaveCount(12)
  expect((await artistNames.allTextContents()).indexOf('HACHI')).toBeGreaterThan(
    initialOrder.indexOf('HACHI'),
  )
  await page.getByRole('textbox').fill('하치')
  await expect(page.locator('.artist-grid .artist-tile')).toHaveCount(1)
  await page.getByRole('button', { name: 'HACHI 즐겨찾기', exact: true }).click()
  await page.getByRole('textbox').fill('ＨＡＣＨＩ')
  await expect(page.locator('.artist-grid .artist-tile')).toHaveCount(1)
  await page.getByRole('link', { name: 'HACHI 아티스트 상세' }).click()
  await expect(page.getByRole('heading', { name: 'HACHI', exact: true })).toBeVisible()
})

test('explore keeps its search query on Enter and clears only on request', async ({ page }) => {
  await visit(page, '/explore')
  const search = page.getByRole('textbox', { name: '아티스트 이름', exact: true })
  await search.fill('하치')
  await expect(page.locator('.artist-grid .artist-tile')).toHaveCount(1)
  await search.press('Enter')
  await expect(search).toHaveValue('하치')
  await expect(page).toHaveURL(`/explore?q=${encodeURIComponent('하치')}`)
  await expect(page.locator('.artist-grid .artist-tile')).toHaveCount(1)
  await page.getByRole('button', { name: '검색어 지우기' }).click()
  await expect(search).toHaveValue('')
  await expect(page).toHaveURL('/explore')
  await expect(page.locator('.artist-grid .artist-tile')).toHaveCount(12)
})

test('artist back button returns to the entry page across detail tabs', async ({ page }) => {
  await visit(page, '/')
  await page.getByRole('link', { name: 'HACHI 아티스트 상세' }).click()
  await page.getByRole('tab', { name: '통계' }).click()
  await page.getByRole('button', { name: '뒤로가기' }).click()
  await expect(page).toHaveURL('/')

  await visit(page, '/explore?q=하치')
  await page.getByRole('link', { name: 'HACHI 아티스트 상세' }).click()
  await page.getByRole('tab', { name: '통계' }).click()
  await page.getByRole('button', { name: '뒤로가기' }).click()
  await expect(page).toHaveURL(`/explore?q=${encodeURIComponent('하치')}`)

  await visit(page, '/search?q=HACHI')
  await page.getByRole('link', { name: 'HACHI 아티스트 상세' }).click()
  await page.getByRole('tab', { name: '통계' }).click()
  await page.getByRole('button', { name: '뒤로가기' }).click()
  await expect(page).toHaveURL('/search?q=HACHI')
  await expect(page.getByRole('textbox', { name: '통합검색' })).toHaveValue('HACHI')

  await visit(page, '/artists/1')
  await page.getByRole('button', { name: '뒤로가기' }).click()
  await expect(page).toHaveURL('/explore')
})

test('search finds original artists and songs and seeks through the YouTube API', async ({
  page,
}) => {
  // Deterministic integration contract; real YouTube is checked separately.
  await page.addInitScript(() => {
    const state = { time: 0, destroyed: false, autoplay: 0, muted: false, playCalls: 0 }
    ;(window as any).__playerTest = state
    ;(window as any).YT = {
      Player: class {
        constructor(target: HTMLElement, options: any) {
          state.time = options.playerVars.start
          state.autoplay = options.playerVars.autoplay
          const frame = document.createElement('iframe')
          frame.title = 'YouTube video player'
          target.replaceWith(frame)
          setTimeout(() => {
            options.events.onReady()
            options.events.onAutoplayBlocked()
          }, 25)
        }
        mute() {
          state.muted = true
        }
        playVideo() {
          state.playCalls++
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
  await page.mouse.move(0, 0)
  await expect(page.locator('.performance-result .archive-thumbnail')).toHaveCount(3)
  await expect(page.locator('.performance-result .result-arrow').first()).toBeVisible()
  await page.locator('.performance-result').filter({ hasText: '晴る' }).click()
  await expect(page).toHaveURL(/\/lives\/101\?t=1088/)
  await expect.poll(() => page.evaluate(() => (window as any).__playerTest.time)).toBe(1088)
  expect(await page.evaluate(() => (window as any).__playerTest.autoplay)).toBe(1)
  await expect.poll(() => page.evaluate(() => (window as any).__playerTest.playCalls)).toBe(1)
  expect(await page.evaluate(() => (window as any).__playerTest.muted)).toBe(true)
  const songButton = page.getByRole('button', { name: /踊り子.*Vaundy/ })
  await songButton.focus()
  await page.keyboard.press('Enter')
  await expect.poll(() => page.evaluate(() => (window as any).__playerTest.time)).toBe(587)
  await expect(page.locator('.setlist-song[aria-current="true"]')).toContainText('踊り子')
  await page.reload({ waitUntil: 'domcontentloaded' })
  await expect.poll(() => page.evaluate(() => (window as any).__playerTest.time)).toBe(587)
  await page.getByRole('button', { name: '뒤로가기' }).click()
  await expect(page).toHaveURL(`/search?q=${encodeURIComponent('요루시카')}`)
  await expect(page.getByRole('textbox', { name: '통합검색' })).toHaveValue('요루시카')

  await visit(page, '/lives/101')
  await expect(page.locator('.setlist-song').first()).toBeVisible()
  await page.getByRole('button', { name: '뒤로가기' }).click()
  await expect(page).toHaveURL('/artists/1?tab=lives')
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
  while (!(await page.locator('a.live-card').count())) {
    await page.getByRole('button', { name: '라이브 더 보기' }).click()
  }
  const archive = page.locator('a.live-card').first()
  await archive.focus()
  await page.keyboard.press('Shift+Tab')
  await page.keyboard.press('Tab')
  await expect(archive.locator('.live-play')).toHaveCSS('opacity', '1')
  await page.getByRole('tab', { name: '발매곡' }).click()
  const lyrics = page.getByRole('button', { name: '가사', exact: true }).first()
  await lyrics.click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await expect(
    page.getByRole('dialog').getByRole('button', { name: '닫기', exact: true }),
  ).toBeVisible()
  await expect(page.getByRole('dialog')).toContainText('Weekend milk')
  await page.getByRole('dialog').getByRole('button', { name: '발음', exact: true }).click()
  await expect(page.locator('.lyric-pronunciation').first()).toBeVisible()
  await page.goBack()
  await expect(page.getByRole('dialog')).not.toBeVisible()
  await expect(page.getByRole('tab', { name: '발매곡' })).toHaveAttribute('data-state', 'active')
  await expect(lyrics).toBeFocused()
  await page.getByRole('tab', { name: '공연 정보' }).click()
  await page.locator('.concert-row').first().click()
  await expect(page.getByRole('dialog')).toContainText('티켓')
  await page.reload({ waitUntil: 'domcontentloaded' })
  await expect(page.getByRole('dialog')).toContainText('Zepp Shinjuku')
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog')).not.toBeVisible()
  await expect(page).toHaveURL(/tab=concerts$/)
})

test('calendar changes month, filters birthdays, and opens concerts', async ({
  page,
  isMobile,
}) => {
  await visit(page, '/calendar?month=2026-09-01')
  await recordCalendarMonthAnimations(page)
  const waitForMonthTransition = () =>
    page.waitForFunction(
      () =>
        !document.querySelector('.calendar-month-surface')?.getAnimations().length &&
        !(document.querySelector('.calendar-month-surface') as HTMLElement)?.style.transform,
    )
  const expectButtonDirections = async () => {
    const frames = await page.evaluate(
      () => (window as Window & { calendarMonthFrames: string[][] }).calendarMonthFrames,
    )
    expect(frames).toHaveLength(4)
    expect(frames[0]?.[0]).toBe('translateX(0px)')
    expect(frames[0]?.[1]).toMatch(/^translateX\(-/)
    expect(frames[1]?.[0]).toMatch(/^translateX\([1-9]/)
    expect(frames[1]?.[1]).toBe('translateX(0px)')
    expect(frames[2]?.[0]).toBe('translateX(0px)')
    expect(frames[2]?.[1]).toMatch(/^translateX\([1-9]/)
    expect(frames[3]?.[0]).toMatch(/^translateX\(-/)
    expect(frames[3]?.[1]).toBe('translateX(0px)')
  }
  if (!isMobile) {
    await page.getByRole('button', { name: '다음 달', exact: true }).click()
    await expect(page).toHaveURL(/month=2026-10-01/)
    await waitForMonthTransition()
    await page.getByRole('button', { name: '이전 달', exact: true }).click()
    await expect(page).toHaveURL(/month=2026-09-01/)
    await waitForMonthTransition()
    await expectButtonDirections()
    const crowdedCell = page
      .getByRole('button', { name: '2026년 9월 20일, 5개 일정', exact: true })
      .locator('..')
    await expect(crowdedCell.locator('.cell-event-link')).toHaveCount(3)
    await expect(crowdedCell.locator('.cell-more')).toContainText('+2')
    await page.setViewportSize({ width: 1440, height: 1400 })
    await expect(crowdedCell.locator('.cell-event-link')).toHaveCount(5)
    await expect(crowdedCell.locator('.cell-more')).toHaveCount(0)
    await page.setViewportSize({ width: 1440, height: 1000 })
    await expect(crowdedCell.locator('.cell-event-link')).toHaveCount(3)
    await crowdedCell.locator('.month-date').click({ position: { x: 12, y: 12 } })
    await expect(page.getByRole('dialog')).toContainText('일정 리스트')
    await expect(page.getByRole('dialog').locator('.schedule-entry')).toHaveCount(5)
    await page.keyboard.press('Escape')
    const board = page.locator('.calendar-board')
    const height = (await board.boundingBox())!.height
    await page.getByRole('button', { name: '리스트 보기', exact: true }).click()
    await expect(page.locator('.calendar-list-view')).toBeVisible()
    await expect(page.locator('.month-grid')).toHaveCount(0)
    expect(Math.abs((await board.boundingBox())!.height - height)).toBeGreaterThan(2)
    await page.getByRole('button', { name: '캘린더 보기', exact: true }).click()
    await page
      .getByRole('button', { name: '2026년 9월 9일, 1개 일정', exact: true })
      .click({ position: { x: 12, y: 100 } })
    await expect(page.getByRole('dialog')).toContainText('KASUKA 생일')
    await page.keyboard.press('Escape')
    await expect(page.getByRole('dialog')).not.toBeVisible()
    await page.getByRole('button', { name: '리스트 보기', exact: true }).click()
    await page
      .locator('.calendar-list-view .month-event')
      .filter({ hasText: '공연' })
      .first()
      .click()
    await expect(page.getByRole('dialog')).toContainText('공연 일시 · 장소 · 티켓 정보')
    return
  }
  const crowdedDay = page.getByRole('button', { name: '2026년 9월 20일, 5개 일정', exact: true })
  await crowdedDay.click({ position: { x: 10, y: 65 } })
  await expect(page.locator('[data-slot="drawer-content"]')).toBeVisible()
  await expect(page.getByRole('dialog').locator('.schedule-entry')).toHaveCount(5)
  await page.getByRole('button', { name: '닫기', exact: true }).click()
  await expect(page.getByRole('dialog')).not.toBeVisible()
  const calendarSwipeHeight = (await page.locator('.calendar-month-surface').boundingBox())!.height
  await page.getByRole('button', { name: '리스트', exact: true }).click()
  await expect(page.locator('.month-grid')).toHaveCount(0)
  await expect(page.locator('.calendar-list-view')).toBeVisible()
  await page.getByRole('button', { name: '공연', exact: true }).click()
  await expect(page.locator('.month-event').filter({ hasText: '공연' })).toHaveCount(0)
  await page.getByRole('button', { name: '생일', exact: true }).click()
  const emptyList = page.locator('.calendar-list-view')
  await expect(emptyList).toContainText('이번 달에 일정이 없습니다')
  const listBox = (await page.locator('.calendar-month-surface').boundingBox())!
  const emptyBox = (await emptyList.getByText('이번 달에 일정이 없습니다').boundingBox())!
  expect(listBox.height).toBeGreaterThanOrEqual(calendarSwipeHeight - 8)
  const listSwipeY = Math.min(listBox.y + listBox.height - 40, 650)
  expect(listSwipeY).toBeGreaterThan(emptyBox.y + emptyBox.height + 30)
  const listClient = await page.context().newCDPSession(page)
  await listClient.send('Input.dispatchTouchEvent', {
    type: 'touchStart',
    touchPoints: [{ x: 300, y: listSwipeY }],
  })
  await listClient.send('Input.dispatchTouchEvent', {
    type: 'touchMove',
    touchPoints: [{ x: 80, y: listSwipeY }],
  })
  await expect(page.locator('.calendar-month-surface')).toHaveAttribute('style', /translateX\(-/)
  await listClient.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] })
  await expect(page).toHaveURL(/month=2026-10-01/)
  await waitForMonthTransition()
  await listClient.send('Input.dispatchTouchEvent', {
    type: 'touchStart',
    touchPoints: [{ x: 80, y: listSwipeY }],
  })
  await listClient.send('Input.dispatchTouchEvent', {
    type: 'touchMove',
    touchPoints: [{ x: 300, y: listSwipeY }],
  })
  await listClient.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] })
  await expect(page).toHaveURL(/month=2026-09-01/)
  await waitForMonthTransition()
  await page.getByRole('button', { name: '공연', exact: true }).click()
  await page.locator('.month-event').first().click()
  await expect(page.getByRole('dialog')).toContainText('공연 일시 · 장소 · 티켓 정보')
  await page.getByRole('button', { name: '닫기', exact: true }).click()
  await page.getByRole('button', { name: '캘린더', exact: true }).click()
  await page.evaluate(
    () => ((window as Window & { calendarMonthFrames: string[][] }).calendarMonthFrames.length = 0),
  )
  const previousMonth = page.getByRole('button', { name: '이전 달', exact: true })
  const nextMonth = page.getByRole('button', { name: '다음 달', exact: true })
  const heading = page.locator('.calendar-toolbar [data-slot="calendar-heading"]')
  const [previousBox, headingBox, nextBox] = await Promise.all([
    previousMonth.boundingBox(),
    heading.boundingBox(),
    nextMonth.boundingBox(),
  ])
  expect(previousBox!.x + previousBox!.width).toBeLessThan(headingBox!.x)
  expect(nextBox!.x).toBeGreaterThan(headingBox!.x + headingBox!.width)
  await nextMonth.click()
  await expect(page).toHaveURL(/month=2026-10-01/)
  await waitForMonthTransition()
  await previousMonth.click()
  await expect(page).toHaveURL(/month=2026-09-01/)
  await waitForMonthTransition()
  await expectButtonDirections()
  const client = await page.context().newCDPSession(page)
  const boardBox = (await page.locator('.calendar-board').boundingBox())!
  const swipeY = boardBox.y + 180
  await client.send('Input.dispatchTouchEvent', {
    type: 'touchStart',
    touchPoints: [{ x: 300, y: swipeY }],
  })
  await client.send('Input.dispatchTouchEvent', {
    type: 'touchMove',
    touchPoints: [{ x: 200, y: swipeY + 2 }],
  })
  await client.send('Input.dispatchTouchEvent', {
    type: 'touchMove',
    touchPoints: [{ x: 80, y: swipeY + 3 }],
  })
  await expect(page.locator('.calendar-month-surface')).toHaveAttribute('style', /translateX\(-/)
  await client.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] })
  await expect(page).toHaveURL(/month=2026-10-01/)
  await waitForMonthTransition()
  await expect(page.getByRole('dialog')).not.toBeVisible()
  await client.send('Input.dispatchTouchEvent', {
    type: 'touchStart',
    touchPoints: [{ x: 80, y: swipeY }],
  })
  await client.send('Input.dispatchTouchEvent', {
    type: 'touchMove',
    touchPoints: [{ x: 300, y: swipeY }],
  })
  await client.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] })
  await expect(page).toHaveURL(/month=2026-09-01/)
  await expect(page.locator('.month-grid')).toBeVisible()
})

test('translated calendar view control keeps toggling without runtime errors', async ({
  page,
  isMobile,
}) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  await visit(page, '/calendar?month=2026-09-01')
  await expect(page.locator('.month-grid')).toBeVisible()
  const viewControl = page.getByRole('button', {
    name: isMobile ? '리스트' : '리스트 보기',
    exact: true,
  })
  await viewControl.evaluate((button) => {
    const label = button.querySelector('span:last-child')!
    const text = label.firstChild!
    const outer = document.createElement('font')
    const inner = document.createElement('font')
    inner.textContent = text.textContent
    outer.append(inner)
    text.replaceWith(outer)
  })
  await viewControl.click()
  await expect(page.locator('.calendar-list-view')).toBeVisible()
  await page.getByRole('button', { name: isMobile ? '캘린더' : '캘린더 보기', exact: true }).click()
  await expect(page.locator('.month-grid')).toBeVisible()
  expect(errors).toEqual([])
})

test('translated mobile controls keep horizontal overflow inside their control rows', async ({
  page,
}) => {
  await page.setViewportSize({ width: 320, height: 844 })
  await visit(page, '/artists/1')
  await expect(page.getByRole('tab')).toHaveCount(4)
  await page.getByRole('tab').evaluateAll((tabs) => {
    const labels = ['Live broadcasts', 'Statistics', 'Original songs', 'Concert information']
    tabs.forEach((tab, index) => {
      const text = [...tab.childNodes].find(
        (node) => node.nodeType === Node.TEXT_NODE && node.textContent?.trim(),
      )
      if (!text) return
      const outer = document.createElement('font')
      const inner = document.createElement('font')
      inner.textContent = labels[index]
      outer.append(inner)
      text.replaceWith(outer)
    })
  })
  await expect
    .poll(() => page.evaluate(() => document.documentElement.scrollWidth))
    .toBeLessThanOrEqual(320)

  await visit(page, '/calendar?month=2026-09-01')
  await expect(page.locator('.month-grid')).toBeVisible()
  await page.locator('.calendar-view-controls button').evaluateAll((buttons) => {
    const labels = ['Favorite artists', 'All artists', 'List view']
    buttons.forEach((button, index) => {
      const target = button.querySelector('span:last-child') ?? button
      const text = [...target.childNodes].find(
        (node) => node.nodeType === Node.TEXT_NODE && node.textContent?.trim(),
      )
      if (!text) return
      const outer = document.createElement('font')
      const inner = document.createElement('font')
      inner.textContent = labels[index]
      outer.append(inner)
      text.replaceWith(outer)
    })
  })
  await expect
    .poll(() => page.evaluate(() => document.documentElement.scrollWidth))
    .toBeLessThanOrEqual(320)
})

test('calendar month buttons respect reduced motion', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await visit(page, '/calendar?month=2026-09-01')
  await recordCalendarMonthAnimations(page)
  await page.getByRole('button', { name: '다음 달', exact: true }).click()
  await expect(page).toHaveURL(/month=2026-10-01/)
  await expect(page.getByRole('button', { name: '다음 달', exact: true })).toBeEnabled()
  const frames = await page.evaluate(
    () => (window as Window & { calendarMonthFrames: string[][] }).calendarMonthFrames,
  )
  expect(frames).toHaveLength(0)
})

test('birthday list subtitle and artist back return to calendar', async ({ page, isMobile }) => {
  await visit(page, '/calendar?month=2026-01-01')
  await page.getByRole('button', { name: isMobile ? '리스트' : '리스트 보기', exact: true }).click()
  const birthday = page
    .locator('.calendar-list-view .month-event')
    .filter({ hasText: 'HACHI 생일' })
  await expect(birthday.locator('.entry-title')).toHaveText('HACHI 생일')
  await expect(birthday.locator('.entry-place')).toHaveText('하치 생일')
  await birthday.click()
  await expect(page).toHaveURL('/artists/1')
  await page.getByRole('button', { name: '뒤로가기' }).click()
  await expect(page).toHaveURL('/calendar?month=2026-01-01')
})

test('calendar view persists and mobile grid and list keep their layout', async ({
  page,
  isMobile,
}) => {
  const currentMonth = await page.evaluate(() => {
    const now = new Date()
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-01`
  })
  await visit(page, `/calendar?month=${currentMonth}`)
  const today = page.locator('.month-cell[data-today]:not([data-outside])')
  await expect(today).toHaveCount(1)
  const backgrounds = await page.evaluate(() => {
    const todayCell = document.querySelector<HTMLElement>('.month-cell[data-today]')!
    const otherCell = document.querySelector<HTMLElement>('.month-cell:not([data-today])')!
    return [
      getComputedStyle(todayCell).backgroundColor,
      getComputedStyle(otherCell).backgroundColor,
    ]
  })
  expect(backgrounds[0]).not.toBe(backgrounds[1])

  await visit(page, '/calendar?month=2026-09-01')
  if (isMobile) {
    const lastCell = page.locator('.month-grid tbody tr:last-child .month-cell').first()
    await expect(lastCell).toHaveCSS('border-bottom-style', 'solid')
    await expect(page.locator('.mobile-event-label').first()).toBeVisible()
    await expect(page.locator('.mobile-event-label svg')).toHaveCount(0)
  }

  await page.getByRole('button', { name: isMobile ? '리스트' : '리스트 보기', exact: true }).click()
  await expect(page.locator('.calendar-list-view')).toBeVisible()
  await page.reload({ waitUntil: 'domcontentloaded' })
  await expect(page.locator('.calendar-list-view')).toBeVisible()
  await expect(
    page.getByRole('button', { name: isMobile ? '캘린더' : '캘린더 보기', exact: true }),
  ).toBeVisible()

  if (isMobile) {
    const entry = page.locator('.calendar-list-view .schedule-entry').first()
    await expect(entry).toBeVisible()
    const avatar = await entry.locator('.artist-avatar').boundingBox()
    const copy = await entry.locator('.entry-copy').boundingBox()
    const row = await entry.boundingBox()
    expect(avatar).not.toBeNull()
    expect(copy).not.toBeNull()
    expect(row).not.toBeNull()
    expect(avatar!.height).toBe(64)
    expect(copy!.height).toBeLessThanOrEqual(avatar!.height)
    expect(avatar!.y).toBeGreaterThanOrEqual(row!.y + 11)
    expect(avatar!.y + avatar!.height).toBeLessThanOrEqual(row!.y + row!.height - 11)
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
