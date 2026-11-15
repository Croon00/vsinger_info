import { test, expect } from '@playwright/test'

test('original music supports multiple genre and mood filters with persistent pagination', async ({
  page,
}, info) => {
  const requests: URL[] = []
  await page.route(/^http:\/\/localhost:5196\/api\//, (route) => {
    const url = new URL(route.request().url())
    if (url.pathname === '/api/artists') return route.fulfill({ json: [] })
    if (url.pathname === '/api/explore/music-tags')
      return route.fulfill({
        json: {
          genres: [
            { value: 'rock', label: '록' },
            { value: 'ballad', label: '발라드' },
          ],
          moods: [
            { value: 'calm', label: '잔잔한' },
            { value: 'powerful', label: '힘찬' },
          ],
        },
      })
    requests.push(url)
    const offset = Number(url.searchParams.get('offset') ?? 0)
    return route.fulfill({
      json: {
        items: [
          {
            key: `recording:${offset + 1}`,
            title: `Song ${offset}`,
            artist_name: 'Singer',
            genres: ['rock', 'ballad'],
            moods: ['calm'],
            youtube_video_id: null,
            view_count: null,
            music_tag_sources: [
              { source_url: 'https://example.com/release', excerpt: 'rock ballad' },
            ],
          },
        ],
        total: 2,
        offset,
        limit: 24,
      },
    })
  })
  await page.goto('/explore?view=songs&kind=original')
  await expect(page.getByLabel('장르', { exact: true })).toHaveCount(2)
  for (const [dimension, labels] of [
    ['장르 분류', ['록', '발라드']],
    ['분위기 분류', ['잔잔한', '힘찬']],
  ] as const) {
    for (const label of labels) {
      await page.getByRole('combobox', { name: dimension, exact: true }).click()
      await page.getByRole('option', { name: label, exact: true }).click()
      await page.keyboard.press('Escape')
    }
    await expect(page.getByRole('combobox', { name: dimension, exact: true })).toContainText(
      '2개 선택',
    )
  }
  await expect
    .poll(() => requests.at(-1)?.searchParams.getAll('genres'))
    .toEqual(['ballad', 'rock'])
  await expect
    .poll(() => requests.at(-1)?.searchParams.getAll('moods'))
    .toEqual(['calm', 'powerful'])
  await page.getByRole('button', { name: '더보기', exact: true }).click()
  await expect(page.locator('.song-explore-row')).toHaveCount(2)
  expect(requests.at(-1)?.searchParams.getAll('genres')).toEqual(['ballad', 'rock'])
  await page.reload()
  await expect(page.getByRole('combobox', { name: '분위기 분류' })).toContainText('2개 선택')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({
    path: `../outputs/song-music-tags/${info.project.name}.png`,
    fullPage: true,
  })
  await page.getByRole('combobox', { name: '장르 분류' }).click()
  await page.getByRole('option', { name: '전체 · 선택 해제' }).click()
  await page.keyboard.press('Escape')
  await expect.poll(() => requests.at(-1)?.searchParams.getAll('genres')).toEqual([])
  expect(requests.at(-1)?.searchParams.getAll('moods')).toEqual(['calm', 'powerful'])
  await page.getByRole('tab', { name: '커버 곡', exact: true }).click()
  await expect(page.getByRole('combobox', { name: '장르 분류' })).toHaveCount(0)
  await expect.poll(() => requests.at(-1)?.searchParams.getAll('moods')).toEqual([])
})
