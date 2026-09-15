import { test, expect } from '@playwright/test'

test('artist statistics paginate, retain Enter searches, filter aliases and paginate all artists independently', async ({
  page,
}) => {
  await page.goto('/artists/1', { waitUntil: 'domcontentloaded' })
  await page.getByRole('tab', { name: '통계', exact: true }).click()
  await expect(page).toHaveURL(/tab=statistics/)
  await expect(page.getByRole('tab')).toHaveText([/라이브/, '통계', '오리곡', '공연 정보'])
  const songSection = page.locator('.song-statistics')
  const artistSection = page.locator('.original-artist-statistics')
  await expect(page.getByText('라이브 기록', { exact: true })).toHaveCount(0)
  const rows = page.locator('.statistics-song-row')
  await expect(rows).toHaveCount(10)
  await songSection.getByRole('button', { name: '다음 페이지', exact: true }).click()
  await expect(rows).toHaveCount(4)
  await expect(songSection.getByRole('button', { name: '다음 페이지', exact: true })).toBeDisabled()
  const search = page.getByRole('textbox', { name: '곡명 또는 원곡 아티스트' })
  await search.fill('요루시카')
  await search.press('Enter')
  await expect(search).toHaveValue('요루시카')
  await expect(rows).toHaveCount(2)
  await expect(songSection.getByRole('button', { name: '이전 페이지', exact: true })).toBeDisabled()
  await expect(page.locator('.statistics-page:not([inert]) .statistics-artists li')).toHaveCount(10)
  await expect(page.getByRole('progressbar').first()).toHaveAttribute(
    'aria-valuenow',
    String((2 / 14) * 100),
  )
  await artistSection.getByRole('button', { name: '다음 페이지', exact: true }).click()
  await expect(artistSection.locator('.statistics-page:not([inert]) li')).toHaveCount(1)
  await expect(artistSection.locator('.statistics-page:not([inert]) .statistics-rank')).toHaveText(
    '11',
  )
  await expect(artistSection.getByRole('progressbar')).toHaveAttribute(
    'aria-valuenow',
    String((1 / 14) * 100),
  )
  await expect(rows).toHaveCount(2)
  await artistSection.getByRole('button', { name: '이전 페이지', exact: true }).click()
  await expect(artistSection.locator('.statistics-page:not([inert]) li')).toHaveCount(10)
  await search.fill('no matching song')
  await expect(page.getByText('검색 결과가 없습니다', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '통계 검색어 지우기' }).click()
  await expect(rows).toHaveCount(10)
  for (const value of ['적게 부른 순', '최근에 부른 순', '오래전에 부른 순', '많이 부른 순']) {
    await page.getByRole('combobox', { name: '곡 정렬순서' }).click()
    await page.getByRole('option', { name: value, exact: true }).click()
    await expect(rows).toHaveCount(10)
  }
  for (const width of [320, 390, 768, 900, 1440]) {
    await page.setViewportSize({ width, height: 900 })
    await expect(page.getByRole('tab', { name: '통계', exact: true })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
  }
  await page.reload({ waitUntil: 'domcontentloaded' })
  await expect(page.getByRole('tab', { name: '통계', exact: true })).toHaveAttribute(
    'aria-selected',
    'true',
  )
})

test('archives without setlists show zero totals and an empty state', async ({ page }) => {
  await page.goto('/artists/2?tab=statistics', { waitUntil: 'domcontentloaded' })
  await expect(page.locator('.statistics-summary')).toHaveCount(0)
  await expect(page.getByText('아직 집계할 세트리스트가 없어요', { exact: true })).toBeVisible()
  await expect(page.getByRole('progressbar')).toHaveCount(0)
})

test('statistics pagination preserves document height, scroll and controls in both directions', async ({
  page,
}) => {
  await page.goto('/artists/1?tab=statistics', { waitUntil: 'domcontentloaded' })
  await expect(page.locator('.statistics-song-row')).toHaveCount(10)
  for (const width of [320, 1440]) {
    await page.setViewportSize({ width, height: 844 })
    for (const selector of ['.song-statistics', '.original-artist-statistics']) {
      const section = page.locator(selector)
      const next = section.getByRole('button', { name: '다음 페이지', exact: true })
      await next.evaluate((el) => el.scrollIntoView({ block: 'center' }))
      const measure = () =>
        section.evaluate((el) => ({
          scroll: scrollY,
          height: document.documentElement.scrollHeight,
          buttonTop: el.querySelector('.statistics-pagination')!.getBoundingClientRect().top,
        }))
      const initial = await measure()
      for (const label of ['다음 페이지', '이전 페이지']) {
        await section.getByRole('button', { name: label, exact: true }).click()
        await expect
          .poll(async () => {
            const current = await measure()
            return Math.max(
              ...Object.keys(initial).map((key) =>
                Math.abs(
                  current[key as keyof typeof current] - initial[key as keyof typeof initial],
                ),
              ),
            )
          })
          .toBeLessThan(1.5)
      }
      await expect(section.locator('.statistics-page[inert]')).toHaveAttribute(
        'aria-hidden',
        'true',
      )
    }
  }
})
