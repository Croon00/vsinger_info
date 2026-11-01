import { test, expect } from '@playwright/test'

test('all song tabs multi-select artists within agency and reset on agency changes', async ({
  page,
}, info) => {
  await page.emulateMedia({ colorScheme: 'dark', reducedMotion: 'reduce' })
  const requests: URL[] = []
  const artists = [
    { id: 1, name: 'Artist 1', agency: 'Group A' },
    { id: 2, name: 'Artist 2', agency: 'Group A' },
    { id: 3, name: 'Artist 3', agency: 'Group B' },
    { id: 4, name: 'Artist 4', agency: null },
  ].map((a) => ({ ...a, display_name: '', sources: [] }))
  await page.route(/^http:\/\/localhost:5196\/api\//, (route) => {
    const url = new URL(route.request().url())
    if (url.pathname === '/api/artists') return route.fulfill({ json: artists })
    requests.push(url)
    const offset = Number(url.searchParams.get('offset') ?? 0)
    const utawaku = url.searchParams.get('kind') === 'utawaku'
    return route.fulfill({
      json: {
        items: [
          {
            key: utawaku ? `song:${offset + 1}` : `video:${offset}`,
            title: `Song ${offset}`,
            artist_name: 'Artist 1 · Artist 2',
            youtube_video_id: utawaku ? null : 'abcdefghijk',
            performance_count: 4,
            artist_count: 2,
            view_count: 120000,
            published_at: '2026-10-01T00:00:00Z',
          },
        ],
        total: 2,
        offset,
        limit: 24,
      },
    })
  })
  await page.goto('/explore?view=songs&kind=cover')
  for (const kind of ['utawaku', 'cover', 'original']) {
    await page
      .getByRole('tab', {
        name: kind === 'utawaku' ? '우타와꾸 곡' : kind === 'cover' ? '커버 곡' : '오리지널 곡',
        exact: true,
      })
      .click()
    await expect(page.getByRole('combobox', { name: '곡 아티스트 필터' })).toContainText(
      '아티스트 전체',
    )
    await page.getByRole('combobox', { name: '곡 소속사 필터' }).click()
    await page.getByRole('option', { name: 'Group A', exact: true }).click()
    await page.getByRole('combobox', { name: '곡 아티스트 필터' }).click()
    await expect(page.getByRole('option', { name: 'Artist 3', exact: true })).toHaveCount(0)
    await page.getByRole('option', { name: 'Artist 1', exact: true }).click()
    await page.keyboard.press('Escape')
    await expect.poll(() => requests.at(-1)?.searchParams.getAll('artist_ids')).toEqual(['1'])
    await page.getByRole('combobox', { name: '곡 아티스트 필터' }).click()
    await page.getByRole('option', { name: 'Artist 2', exact: true }).click()
    await page.keyboard.press('Escape')
    await expect.poll(() => requests.at(-1)?.searchParams.getAll('artist_ids')).toEqual(['1', '2'])
    await expect(page.getByRole('combobox', { name: '곡 아티스트 필터' })).toContainText('2명')
    if (kind === 'utawaku') {
      const href = await page
        .getByRole('link', { name: '리스트 열기', exact: true })
        .getAttribute('href')
      const target = new URL(href!, 'http://localhost')
      expect(target.searchParams.getAll('artist_ids')).toEqual(['1', '2'])
      expect(target.searchParams.get('song_key')).toBe('song:1')
      expect(target.searchParams.get('agency')).toBe('Group A')
    }
    await page.getByRole('button', { name: '더보기', exact: true }).click()
    await expect(page.locator('.song-explore-row')).toHaveCount(2)
    expect(requests.at(-1)?.searchParams.getAll('artist_ids')).toEqual(['1', '2'])
    await page.reload()
    await expect(page.getByRole('combobox', { name: '곡 아티스트 필터' })).toContainText('2명')
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.screenshot({
      path: `../outputs/song-artist-filters/${info.project.name}-${kind}.png`,
      fullPage: true,
    })
    await page.getByRole('combobox', { name: '곡 소속사 필터' }).click()
    await page.getByRole('option', { name: 'Group B', exact: true }).click()
    await expect.poll(() => requests.at(-1)?.searchParams.get('agency')).toBe('Group B')
    expect(requests.at(-1)?.searchParams.getAll('artist_ids')).toEqual([])
    await expect(page.getByRole('combobox', { name: '곡 아티스트 필터' })).toContainText(
      '아티스트 전체',
    )
    await page.getByRole('combobox', { name: '곡 아티스트 필터' }).click()
    await expect(page.getByRole('option', { name: 'Artist 1', exact: true })).toHaveCount(0)
    await page.getByRole('option', { name: 'Artist 3', exact: true }).click()
    await page.keyboard.press('Escape')
    await expect.poll(() => requests.at(-1)?.searchParams.getAll('artist_ids')).toEqual(['3'])
    await page.getByRole('combobox', { name: '곡 아티스트 필터' }).click()
    await page.getByRole('option', { name: '아티스트 전체', exact: true }).click()
    await page.keyboard.press('Escape')
    await expect(page).not.toHaveURL(/song_artists=/)
    await expect(page.getByRole('combobox', { name: '곡 아티스트 필터' })).toContainText(
      '아티스트 전체',
    )
  }
})

test('original songs offer each group once and keep cover members separate', async ({ page }) => {
  const requests: URL[] = []
  const groups = [
    { id: 13, name: 'KMNZ', members: ['LITA', 'TINA', 'NERO'] },
    { id: 17, name: 'VESPERBELL', members: ['YOMI', 'KASUKA'] },
    { id: 39, name: 'HONK THE HORN', members: ['MOCO', 'BAMBI'] },
    { id: 24, name: 'NUROJUNK', members: ['KAGURA', 'SAKUYA'] },
  ]
  const artists = groups.flatMap((group) => group.members.map((name, i) => ({
    id: group.id * 100 + i, name, display_name: '', agency: 'RK Music', sources: [],
    original_song_group: { id: group.id, name: group.name, agency: 'RK Music' },
  })))
  await page.route(/^http:\/\/localhost:5196\/api\//, (route) => {
    const url = new URL(route.request().url())
    if (url.pathname === '/api/artists') return route.fulfill({ json: artists })
    requests.push(url)
    return route.fulfill({ json: { items: [], total: 0, offset: 0, limit: 24 } })
  })
  await page.goto('/explore?view=songs&kind=original&song_agency=RK%20Music')
  const filter = page.getByRole('combobox', { name: '곡 아티스트 필터' })
  await filter.click()
  for (const group of groups) {
    await expect(page.getByRole('option', { name: group.name, exact: true })).toHaveCount(1)
    for (const member of group.members) {
      await expect(page.getByRole('option', { name: member, exact: true })).toHaveCount(0)
    }
  }
  await page.getByRole('option', { name: 'KMNZ', exact: true }).click()
  await page.getByRole('option', { name: 'VESPERBELL', exact: true }).click()
  await page.keyboard.press('Escape')
  await expect.poll(() => requests.at(-1)?.searchParams.getAll('artist_ids')).toEqual(['13', '17'])
  await page.getByRole('tab', { name: '커버 곡', exact: true }).click()
  await expect(filter).toContainText('아티스트 전체')
  await filter.click()
  for (const group of groups) {
    await expect(page.getByRole('option', { name: group.name, exact: true })).toHaveCount(0)
    for (const member of group.members) {
      await expect(page.getByRole('option', { name: member, exact: true })).toHaveCount(1)
    }
  }
  await page.keyboard.press('Escape')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})
