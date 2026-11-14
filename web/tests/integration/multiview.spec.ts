import { test, expect } from '@playwright/test'

test('selects streams, switches chat and audio, preserves players on refresh, and closes them', async ({
  page,
  isMobile,
}, info) => {
  await page.addInitScript(() => {
    localStorage.setItem('schedule-music-api:catalog-v1-favorites', '[1]')
    const trace: string[] = []
    ;(window as any).streamTrace = trace
    ;(window as any).YT = {
      Player: class {
        frame: HTMLIFrameElement
        constructor(target: HTMLElement, options: any) {
          this.frame = document.createElement('iframe')
          this.frame.dataset.player = options.videoId
          this.frame.title = 'Fixture YouTube player'
          target.replaceWith(this.frame)
          trace.push('create:' + options.videoId)
          setTimeout(options.events.onReady, 0)
        }
        mute() {
          trace.push('mute:' + this.frame.dataset.player)
        }
        unMute() {
          trace.push('unmute:' + this.frame.dataset.player)
        }
        destroy() {
          trace.push('destroy:' + this.frame.dataset.player)
          this.frame.remove()
        }
      },
    }
  })
  const now = Date.now()
  const items = Array.from({ length: 6 }, (_, i) => ({
    account_id: i + 1,
    artist_id: i + 1,
    artist_name: `Singer ${i + 1}`,
    channel_id: 'UC' + String(i).repeat(22),
    video_id: String(i).repeat(11),
    title: `生放送 · Live stream ${i + 1}`,
    status: i === 5 ? 'upcoming' : 'live',
    avatar_url: `/fixture-avatars/${i}.svg`,
    started_at: i === 5 ? null : new Date(now - (i + 1) * 3600000).toISOString(),
    scheduled_at: i === 5 ? new Date(now + 17 * 60000).toISOString() : null,
    checked_at: new Date().toISOString(),
  }))
  items.push(
    {
      ...items[5]!,
      video_id: 'future00000',
      artist_name: 'Far future',
      scheduled_at: new Date(now + 3 * 3600000).toISOString(),
    },
    { ...items[5]!, video_id: 'unknown0000', artist_name: 'Unknown schedule', scheduled_at: null },
    {
      ...items[5]!,
      video_id: 'delayed0000',
      artist_name: 'Delayed stream',
      scheduled_at: new Date(now - 60000).toISOString(),
    },
  )
  let failure = false
  items.push(
    {
      ...items[0]!,
      video_id: 'freechat000',
      artist_name: 'FreeChat room',
      title: '【FreeChat】お話ししましょう',
    },
    {
      ...items[5]!,
      video_id: 'freechat001',
      artist_name: 'Upcoming FreeChat',
      title: 'FREE CHAT waiting room',
    },
  )
  await page.route('**/fixture-avatars/*', (route) =>
    route.fulfill({
      contentType: 'image/svg+xml',
      body: '<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96"><rect width="96" height="96" fill="#90b5d0"/><circle cx="48" cy="38" r="18" fill="#e8eff4"/><path d="M12 96a36 36 0 0 1 72 0" fill="#e8eff4"/></svg>',
    }),
  )
  await page.route('**/api/stream-groups', (route) =>
    route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify([
        { key: 'agency:1', name: 'Agency A', kind: 'agency', account_ids: [1, 2, 3] },
        { key: 'group:1', name: 'Unit A', kind: 'group', account_ids: [1, 2] },
        { key: 'group:2', name: 'Unit B', kind: 'group', account_ids: [4, 5] },
      ]),
    }),
  )
  await page.route('**/api/streams?*', (route) =>
    route.fulfill({
      status: failure ? 503 : 200,
      contentType: 'application/json',
      body: JSON.stringify(
        failure
          ? { detail: 'fixture failure' }
          : { items, total: items.length, offset: 0, limit: 100 },
      ),
    }),
  )
  await page.route('https://www.youtube.com/**', (route) =>
    route.fulfill({ contentType: 'text/html', body: '<p>Fixture chat</p>' }),
  )
  await page.route('**/api/artists', (route) =>
    route.fulfill({ contentType: 'application/json', body: '[]' }),
  )
  await page.goto('/multiview')
  await expect(page.getByRole('button', { name: 'FreeChat room LIVE', exact: true })).toHaveCount(0)
  await expect(
    page.getByRole('button', { name: 'Upcoming FreeChat 예정', exact: true }),
  ).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Far future 예정', exact: true })).toHaveCount(0)
  await expect(
    page.getByRole('button', { name: 'Unknown schedule 예정', exact: true }),
  ).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Delayed stream 예정', exact: true })).toHaveCount(
    0,
  )
  const liveChannel = page.getByRole('button', { name: 'Singer 1 LIVE', exact: true })
  const upcomingChannel = page.getByRole('button', { name: 'Singer 6 예정', exact: true })
  await expect(liveChannel.locator('img')).toBeVisible()
  await expect(liveChannel.locator('[data-status="live"]')).toHaveText('1h')
  await expect(upcomingChannel.locator('[data-status="upcoming"]')).toHaveText('17m')
  expect(await liveChannel.boundingBox()).toMatchObject({ width: 48 })
  expect(
    await liveChannel
      .locator('[data-status="live"]')
      .evaluate((el) => getComputedStyle(el).backgroundColor),
  ).not.toBe(
    await upcomingChannel
      .locator('[data-status="upcoming"]')
      .evaluate((el) => getComputedStyle(el).backgroundColor),
  )
  await page.getByRole('combobox', { name: '그룹 필터' }).selectOption('group:1')
  await expect(
    page.getByRole('region', { name: '방송 중인 채널' }).getByRole('button'),
  ).toHaveCount(2)
  await page.getByRole('button', { name: '표시된 방송 담기' }).click()
  await expect(page.locator('iframe[data-player]')).toHaveCount(2)
  await page.getByRole('combobox', { name: '그룹 필터' }).selectOption('group:2')
  await expect(page.locator('iframe[data-player]')).toHaveCount(2)
  await expect(
    page.getByRole('region', { name: '방송 중인 채널' }).getByRole('button'),
  ).toHaveCount(2)
  await page.getByRole('button', { name: 'Singer 1 닫기', exact: true }).click()
  await page.getByRole('button', { name: 'Singer 2 닫기', exact: true }).click()
  await page.getByRole('combobox', { name: '그룹 필터' }).selectOption('agency:1')
  await expect(
    page.getByRole('region', { name: '방송 중인 채널' }).getByRole('button'),
  ).toHaveCount(3)
  await page.getByRole('combobox', { name: '그룹 필터' }).selectOption('all')
  await page.evaluate(() => {
    ;(window as any).streamTrace.length = 0
  })
  await page.getByRole('combobox', { name: '채널 필터' }).selectOption('favorites')
  await expect(
    page.getByRole('region', { name: '방송 중인 채널' }).getByRole('button'),
  ).toHaveCount(1)
  await page.getByRole('combobox', { name: '채널 필터' }).selectOption('all')
  const channels = page.getByRole('region', { name: '방송 중인 채널' })
  for (let i = 1; i <= 4; i++)
    await channels.getByRole('button', { name: `Singer ${i} LIVE` }).click()
  await expect(page.locator('iframe[data-player]')).toHaveCount(4)
  await channels.getByRole('button', { name: 'Singer 5 LIVE' }).click()
  await expect(page.getByRole('status')).toContainText('최대 4개')
  await page.getByRole('button', { name: 'Singer 1 소리', exact: true }).click()
  await page.getByRole('button', { name: 'Singer 2 소리', exact: true }).click()
  const trace = await page.evaluate(() => (window as any).streamTrace as string[])
  expect(trace).toContain('unmute:11111111111')
  expect(trace.lastIndexOf('mute:00000000000')).toBeGreaterThan(
    trace.lastIndexOf('unmute:00000000000'),
  )
  await page.getByRole('combobox', { name: '채팅 방송 선택' }).selectOption('11111111111')
  if (isMobile) {
    await expect(page.locator('iframe[src*="live_chat"]')).toHaveCount(0)
    await expect(page.getByText('모바일 웹에서는 YouTube 채팅')).toBeVisible()
  } else {
    await expect(page.locator('iframe[src*="live_chat"]')).toHaveAttribute(
      'src',
      /v=11111111111&embed_domain=localhost/,
    )
  }
  await page.getByRole('button', { name: '방송 목록 새로고침' }).click()
  await expect(page.getByRole('button', { name: '방송 목록 새로고침' })).toBeEnabled()
  expect(
    (await page.evaluate(() => (window as any).streamTrace as string[])).filter((s) =>
      s.startsWith('create:'),
    ),
  ).toHaveLength(4)
  failure = true
  await page.getByRole('button', { name: '방송 목록 새로고침' }).click()
  await expect(page.getByText('콘텐츠 서비스를 사용할 수 없어요.', { exact: false })).toBeVisible()
  await expect(page.locator('iframe[data-player]')).toHaveCount(4)
  await page.getByRole('button', { name: 'Singer 2 닫기', exact: true }).click()
  await expect(page.locator('iframe[data-player]')).toHaveCount(3)
  expect(await page.evaluate(() => (window as any).streamTrace)).toContain('destroy:11111111111')
  failure = false
  await page.getByRole('button', { name: '방송 목록 새로고침' }).click()
  await page.getByRole('combobox', { name: '영상 배치' }).selectOption('focus')
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
  ).toBeTruthy()
  await page.screenshot({
    path: `docs/screenshots/multiview-${info.project.name}.png`,
    fullPage: true,
  })
  await page.getByRole('link', { name: '홈으로' }).click()
  await expect(page.locator('iframe[data-player]')).toHaveCount(0)
})
