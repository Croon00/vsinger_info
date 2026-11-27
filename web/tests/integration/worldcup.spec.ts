import { test, expect } from '@playwright/test'

const artists = [
  {
    id: 1,
    name: 'Singer A',
    display_name: '가수A',
    agency: 'Label',
    sources: [],
    related_artist_ids: [1],
  },
  {
    id: 2,
    name: 'Singer B',
    display_name: '가수B',
    agency: 'Label',
    sources: [],
    related_artist_ids: [2],
  },
  {
    id: 3,
    name: 'Solo',
    display_name: '솔로',
    agency: 'Other',
    sources: [],
    related_artist_ids: [3],
  },
  {
    id: 4,
    name: 'Rare',
    display_name: '레어',
    agency: 'Label',
    sources: [],
    related_artist_ids: [4],
  },
]
const names: Record<string, string> = { '1': 'Singer A', '2': 'Singer B', '3': 'Solo', '4': 'Rare' }
const songs = Array.from({ length: 40 }, (_, i) => ({
  key: `recording:${i + 1}`,
  title: `Song ${i + 1}`,
  title_ko: null,
  // Rare has 5 songs, Singer A 18 and Singer B 17; Solo has none.
  artist_name: i < 5 ? 'Rare' : i % 2 ? 'Singer A' : 'Singer B',
  youtube_video_id: `video${String(i + 1).padStart(6, '0')}`,
  view_count: 1000 * (i + 1),
  views_updated_at: null,
  performance_count: null,
  artist_count: null,
  archive_id: null,
  start_seconds: null,
  published_at: '2025-01-01T00:00:00Z',
}))

test('world cup draws originals, plays a bracket, undoes, resumes and shows the winner', async ({
  page,
}) => {
  const requests: URLSearchParams[] = []
  const submissions: Record<string, unknown>[] = []
  const statRequests: URLSearchParams[] = []
  const summaries: string[] = []
  await page.route(/^http:\/\/localhost:5196\/api\//, async (route) => {
    const url = new URL(route.request().url())
    if (url.pathname === '/api/artists') return route.fulfill({ json: artists })
    if (url.pathname === '/api/worldcup/pool-summary') {
      summaries.push(url.searchParams.get('song_kind') ?? '')
      // 'Other' can join another agency's pool; Solo has no playable songs.
      return route.fulfill({
        json: {
          song_kind: url.searchParams.get('song_kind'),
          total: 40,
          agencies: [
            { name: 'Label', count: 40 },
            { name: 'Other', count: 5 },
          ],
          artists: [
            { id: 1, count: 18 },
            { id: 2, count: 17 },
            { id: 4, count: 5 },
          ],
        },
      })
    }
    if (url.pathname === '/api/worldcup/results') {
      const body = route.request().postDataJSON()
      submissions.push(body)
      const winner = body.matches.at(-1).winner
      return route.fulfill({
        status: 201,
        json: {
          run_id: 7,
          duplicate: false,
          winner: {
            video_id: winner,
            title: 'Winner',
            title_ko: null,
            artist_name: 'Singer A',
            appearances: 12,
            championships: 3,
            championship_rate: 0.25,
            match_wins: 30,
            match_losses: 9,
            match_win_rate: 30 / 39,
          },
        },
      })
    }
    if (url.pathname === '/api/worldcup/stats') {
      statRequests.push(url.searchParams)
      const row = (n: number, champs: number) => ({
        video_id: songs[n].youtube_video_id,
        title: songs[n].title,
        title_ko: null,
        artist_name: songs[n].artist_name,
        appearances: 10,
        championships: champs,
        championship_rate: champs / 10,
        match_wins: 20,
        match_losses: 5,
        match_win_rate: 0.8,
      })
      return route.fulfill({
        json: { items: [row(0, 5), row(1, 2)], total: 2, offset: 0, limit: 50, total_runs: 14 },
      })
    }
    if (url.pathname === '/api/explore/songs') {
      requests.push(url.searchParams)
      const offset = Number(url.searchParams.get('offset'))
      const limit = Number(url.searchParams.get('limit'))
      const ids = url.searchParams.getAll('artist_ids')
      const pool =
        url.searchParams.getAll('agency_names').join() === 'Other'
          ? songs.slice(0, 5)
          : ids.length
            ? songs.filter((song) => ids.some((id) => names[id] === song.artist_name))
            : songs
      return route.fulfill({
        json: { items: pool.slice(offset, offset + limit), total: pool.length, offset, limit },
      })
    }
    return route.fulfill({ json: { items: [], total: 0, offset: 0, limit: 24 } })
  })
  await page.goto('/worldcup')
  await expect(page.getByRole('heading', { name: '오리지널 곡 월드컵' })).toBeVisible()
  await expect(page.getByRole('status').filter({ hasText: 'MV가 있는 오리지널' })).toContainText(
    '40곡 · 아티스트 3명',
  )
  const first = requests.find((params) => params.get('limit') === '100')!
  expect(first.get('kind')).toBe('original')
  expect(first.getAll('agency_names')).toEqual(['Label'])
  expect(first.get('published_only')).toBe('true')
  expect(first.get('limit')).toBe('100')
  await page.getByRole('combobox', { name: '소속사' }).click()
  await expect(page.getByRole('option')).toHaveText(['Label · 40곡', 'Other · 5곡'])
  await page.keyboard.press('Escape')
  await expect(page.getByRole('button', { name: '64강', exact: true })).toBeDisabled()
  await expect(page.getByRole('button', { name: '128강', exact: true })).toBeDisabled()
  await page.getByRole('button', { name: '16강', exact: true }).click()
  await page.getByRole('button', { name: '16강 시작하기' }).click()

  await expect(page.getByRole('heading', { name: /16강/ })).toContainText('1 / 8')
  const cards = page.locator('.worldcup-card')
  await expect(cards).toHaveCount(2)
  const firstTitle = await cards.first().locator('.worldcup-title').textContent()
  await cards.first().getByRole('button', { name: /듣기$/ }).click()
  await expect(cards.first().locator('iframe')).toHaveAttribute('src', /youtube\.com\/embed\/video/)
  await cards.first().getByRole('button', { name: /선택$/ }).click()
  await expect(page.getByRole('heading', { name: /16강/ })).toContainText('2 / 8')
  await page.getByRole('button', { name: '되돌리기' }).click()
  await expect(page.getByRole('heading', { name: /16강/ })).toContainText('1 / 8')
  await expect(cards.first().locator('.worldcup-title')).toHaveText(firstTitle!)

  for (let i = 0; i < 7; i++) await cards.first().getByRole('button', { name: /선택$/ }).click()
  await expect(page.getByRole('heading', { name: /16강/ })).toContainText('8 / 8')
  await page.reload()
  await expect(page.getByRole('heading', { name: /16강/ })).toContainText('8 / 8')

  for (let i = 0; i < 8; i++)
    await page.locator('.worldcup-card').last().getByRole('button', { name: /선택$/ }).click()
  await expect(page.getByLabel('월드컵 결과')).toBeVisible()
  await expect(page.locator('.worldcup-winner-stats')).toContainText(
    '전체 12판 출전 · 우승 3회 (25.0%) · 1:1 승률 76.9% (30승 9패)',
  )
  expect(submissions).toHaveLength(1)
  const sent = submissions[0] as { matches: { round: number }[]; size: number; scope_kind: string }
  expect(sent).toMatchObject({
    size: 16,
    song_kind: 'original',
    scope_kind: 'agency',
    scope_label: 'Label 오리지널 · 16강',
  })
  expect(sent.matches.map((m) => m.round)).toEqual([
    16, 16, 16, 16, 16, 16, 16, 16, 8, 8, 8, 8, 4, 4, 2,
  ])
  await page.reload()
  // Already submitted: the reload reads the winner's statistics instead of posting again.
  await expect(page.locator('.worldcup-winner-stats')).toContainText('우승 5회')
  expect(submissions).toHaveLength(1)
  expect(statRequests.at(-1)?.getAll('video_ids')).toEqual([
    (submissions[0] as { matches: { winner: string }[] }).matches.at(-1)!.winner,
  ])
  await page.getByRole('button', { name: '랭킹 보기' }).click()
  await expect(page).toHaveURL(/view=ranking/)
  await expect(page.locator('.worldcup-rank-row')).toHaveCount(2)
  await expect(page.locator('.worldcup-rank-row').first()).toContainText('Song 1')
  await expect(page.locator('.worldcup-rank-row').first()).toContainText('5회')
  await expect(page.getByLabel('월드컵 랭킹')).toContainText('전체 14판 집계')
  await page.getByRole('combobox', { name: '랭킹 정렬' }).click()
  await page.getByRole('option', { name: '우승 비율' }).click()
  await expect.poll(() => statRequests.at(-1)?.get('order')).toBe('championship_rate')
  expect(statRequests.at(-1)?.get('min_appearances')).toBe('3')
  await page.getByRole('tab', { name: '월드컵' }).click()
  await expect(page.getByText('우승', { exact: true })).toBeVisible()
  await expect(page.locator('.worldcup-ranks')).toContainText('준우승')
  await expect(page.locator('.worldcup-ranks')).toContainText('8강')

  await page.getByRole('button', { name: '새 월드컵' }).click()
  await page.getByRole('button', { name: '아티스트 선택', exact: true }).click()
  await expect(page.getByRole('status').filter({ hasText: '아티스트를' })).toBeVisible()
  const start = page.getByRole('button', { name: /강 시작하기$/ })
  await expect(start).toBeDisabled()
  await page.getByRole('combobox', { name: '아티스트' }).click()
  // Only artists with MV originals are offered, with their song counts.
  await expect(page.getByRole('option')).toHaveText([
    'Singer A (가수A) · 18곡',
    'Singer B (가수B) · 17곡',
    'Rare (레어) · 5곡',
  ])
  await page.getByRole('option', { name: /Rare/ }).click()
  await page.keyboard.press('Escape')
  await expect.poll(() => requests.at(-1)?.getAll('artist_ids')).toEqual(['4'])
  expect(requests.at(-1)?.get('agency')).toBe('all')
  expect(new Set(summaries)).toEqual(new Set(['original']))
  await expect(page.getByRole('status').filter({ hasText: '5곡' })).toContainText(
    '8곡 이상이 되도록 아티스트를 더 골라 주세요.',
  )
  await expect(start).toBeDisabled()
  await page.getByRole('combobox', { name: '아티스트' }).click()
  await page.getByRole('option', { name: /Singer A/ }).click()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('status').filter({ hasText: 'MV가 있는 오리지널' })).toContainText(
    '23곡 · 아티스트 2명',
  )
  await expect(page.getByRole('button', { name: '16강 시작하기' })).toBeEnabled()

  // Covers use the same flow with their own counts and candidate requests.
  await page.getByRole('button', { name: '커버', exact: true }).click()
  await expect.poll(() => summaries.at(-1)).toBe('cover')
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('커버 곡 월드컵')
  // Switching kinds clears the picked artists (cover credits differ from original groups).
  await expect(page.getByRole('status').filter({ hasText: '아티스트를' })).toBeVisible()
  await page.getByRole('button', { name: '소속사', exact: true }).click()
  await expect.poll(() => requests.at(-1)?.get('kind')).toBe('cover')
  await expect(page.getByRole('status').filter({ hasText: '커버 영상' })).toContainText('40곡')
  await page.getByRole('button', { name: '8강', exact: true }).click()
  await page.getByRole('button', { name: '8강 시작하기' }).click()
  await expect(page.locator('.worldcup-label')).toHaveText('Label 커버 · 8강')
  for (let i = 0; i < 7; i++)
    await cards.first().getByRole('button', { name: /선택$/ }).click()
  await expect(page.locator('.worldcup-winner-stats')).toContainText('우승 3회')
  expect(submissions).toHaveLength(2)
  expect(submissions[1]).toMatchObject({ size: 8, song_kind: 'cover' })
  const cover = submissions[1] as { matches: { round: number }[] }
  expect(cover.matches.map((match) => match.round)).toEqual([8, 8, 8, 8, 4, 4, 2])
})

test('multiple small agencies contribute to one video pool without duplicate candidates', async ({ page }) => {
  const combinations: string[][] = []
  await page.route(/^http:\/\/localhost:5196\/api\//, async (route) => {
    const url = new URL(route.request().url())
    if (url.pathname === '/api/artists') return route.fulfill({ json: artists })
    if (url.pathname === '/api/worldcup/pool-summary')
      return route.fulfill({
        json: {
          song_kind: url.searchParams.get('song_kind'), total: 17, artists: [],
          agencies: [{ name: 'Label', count: 10 }, { name: 'Other', count: 8 }],
        },
      })
    if (url.pathname === '/api/explore/songs') {
      const selected = url.searchParams.getAll('agency_names')
      combinations.push(selected)
      const pool = selected.length === 2
        ? [...songs.slice(0, 17), { ...songs[9], key: 'recording:shared' }]
        : selected.includes('Label') ? songs.slice(0, 10) : songs.slice(9, 17)
      return route.fulfill({ json: { items: pool, total: 17, offset: 0, limit: 100 } })
    }
    return route.fulfill({ json: { items: [], total: 0, offset: 0, limit: 24 } })
  })
  await page.goto('/worldcup')
  const count = page.getByRole('status').filter({ hasText: 'MV가 있는 오리지널' })
  await expect(count).toContainText('10곡')
  await expect(page.getByRole('button', { name: '8강 시작하기' })).toBeEnabled()
  await expect(page.getByRole('button', { name: '16강', exact: true })).toBeDisabled()
  const select = page.getByRole('combobox', { name: '소속사' })
  await select.click()
  await page.getByRole('option', { name: 'Other · 8곡' }).click()
  await page.keyboard.press('Escape')
  await expect(select).toContainText('소속사 2곳 선택')
  await expect(count).toContainText('17곡')
  expect(combinations.at(-1)).toEqual(['Label', 'Other'])
  await page.getByRole('button', { name: '16강', exact: true }).click()
  await page.getByRole('button', { name: '16강 시작하기' }).click()
  await expect(page.locator('.worldcup-label')).toHaveText('Label, Other 오리지널 · 16강')
})
