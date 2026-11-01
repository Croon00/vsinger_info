import { test, expect } from '@playwright/test'

test('cover and original use the same range calendar for publication dates', async ({
  page,
}, info) => {
  await page.emulateMedia({ colorScheme: 'dark', reducedMotion: 'reduce' })
  const requests: URL[] = []
  await page.route(/^http:\/\/localhost:5196\/api\//, (route) => {
    const url = new URL(route.request().url())
    if (url.pathname === '/api/artists')
      return route.fulfill({
        json: [{ id: 1, name: 'Singer', display_name: '', agency: 'Group', sources: [] }],
      })
    requests.push(url)
    const offset = Number(url.searchParams.get('offset') ?? 0)
    const empty = url.searchParams.get('start') === '2000-01-01'
    return route.fulfill({
      json: {
        items: empty
          ? []
          : [
              {
                key: `video:${offset}`,
                title: 'Song',
                artist_name: 'Singer',
                youtube_video_id: 'abcdefghijk',
                view_count: 120000,
                published_at: '2026-10-01T00:00:00Z',
              },
            ],
        total: empty ? 0 : 2,
        offset,
        limit: 24,
      },
    })
  })
  await page.goto('/explore?view=songs&kind=cover&song_agency=Group')
  for (const kind of ['cover', 'original']) {
    await page
      .getByRole('tab', { name: kind === 'cover' ? '커버 곡' : '오리지널 곡', exact: true })
      .click()
    await page.getByRole('combobox', { name: '곡 아티스트 필터' }).click()
    await page.getByRole('option', { name: 'Singer', exact: true }).click()
    await page.keyboard.press('Escape')
    await expect.poll(() => requests.at(-1)?.searchParams.getAll('artist_ids')).toEqual(['1'])
    await page.getByRole('button', { name: '영상 등록 기간 선택', exact: true }).click()
    await page.getByLabel('기간 연도', { exact: true }).selectOption('2026')
    await page.getByLabel('기간 월', { exact: true }).selectOption('10')
    const count = requests.length
    await page.locator('[data-slot="range-calendar-trigger"][data-value="2026-10-01"]').click()
    await page.locator('[data-slot="range-calendar-trigger"][data-value="2026-10-31"]').click()
    expect(requests.length).toBe(count)
    await page.getByRole('button', { name: '적용', exact: true }).click()
    await expect.poll(() => requests.at(-1)?.searchParams.get('start')).toBe('2026-10-01')
    expect(requests.at(-1)?.searchParams.get('end')).toBe('2026-10-31')
    expect(requests.at(-1)?.searchParams.get('agency')).toBe('Group')
    expect(requests.at(-1)?.searchParams.getAll('artist_ids')).toEqual(['1'])
    await page.getByRole('button', { name: '더보기', exact: true }).click()
    await expect(page.locator('.song-explore-row')).toHaveCount(2)
    expect(requests.at(-1)?.searchParams.get('start')).toBe('2026-10-01')
    await page.reload()
    await expect(
      page.getByRole('button', { name: '영상 등록 기간 선택', exact: true }),
    ).toContainText('2026.10.01 ~ 2026.10.31')
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.screenshot({
      path: `../outputs/song-date-filters/${info.project.name}-${kind}.png`,
      fullPage: true,
    })
    await page.getByRole('button', { name: '영상 등록 기간 선택', exact: true }).click()
    await page.getByLabel('기간 연도', { exact: true }).selectOption('2000')
    await page.getByLabel('기간 월', { exact: true }).selectOption('1')
    await page.locator('[data-slot="range-calendar-trigger"][data-value="2000-01-01"]').click()
    await page.locator('[data-slot="range-calendar-trigger"][data-value="2000-01-01"]').click()
    await page.getByRole('button', { name: '적용', exact: true }).click()
    await expect(page.locator('.song-explore-row')).toHaveCount(0)
    await page.getByRole('button', { name: '영상 등록 기간 선택', exact: true }).click()
    await page.getByRole('button', { name: '전체 기간', exact: true }).click()
    await expect(page).not.toHaveURL(/song_start=/)
    await expect(page.locator('.song-explore-row')).toHaveCount(1)
  }
})
