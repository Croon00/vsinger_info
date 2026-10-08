import { expect, it } from 'vitest'
import type { Live } from '@/api/types'
import { archiveActivity, monthlyActivity } from '@/lib/archive-activity'
const archive = (broadcast_at: string) => ({ broadcast_at }) as Live
const now = new Date('2026-03-15T00:00:00Z')
it('counts archives by Korean month, including months without archives', () => {
  const data = archiveActivity(
    [
      archive('2025-12-31T16:00:00Z'),
      archive('2026-01-20T00:00:00Z'),
      archive('invalid'),
      archive('2026-04-01T00:00:00Z'),
    ],
    '6M',
    now,
  )
  expect(data).toHaveLength(6)
  expect(data[0]?.month).toBe('2025-09')
  expect(data.at(-1)?.month).toBe('2026-02')
  expect(data.find((d) => d.month === '2026-01')?.count).toBe(2)
  expect(data.at(-1)?.count).toBe(0)
})
it('supports twelve months, full history and an empty history', () => {
  expect(archiveActivity([], '12M', now)).toHaveLength(12)
  expect(archiveActivity([archive('2024-01-01')], 'All', now)).toHaveLength(26)
  expect(archiveActivity([], 'All', now)).toEqual([{ index: 0, month: '2026-02', count: 0 }])
})

it.each(['6M', '12M', 'All'] as const)(
  'excludes current and future months for %s in both data paths',
  (period) => {
    const lives = [archive('2026-02-10'), archive('2026-03-01'), archive('2026-04-01')]
    const months = [
      { month: '2026-02', count: 1 },
      { month: '2026-03', count: 1 },
      { month: '2026-04', count: 1 },
    ]
    const data = monthlyActivity(months, period, now)
    expect(archiveActivity(lives, period, now)).toEqual(data)
    expect(data.at(-1)).toMatchObject({ month: '2026-02', count: 1 })
    expect(data.every((month) => month.month < '2026-03')).toBe(true)
  },
)

it('rolls over at Korean midnight on January 1 and preserves full period lengths', () => {
  const boundary = new Date('2025-12-31T15:00:00Z')
  const lives = [archive('2025-12-31T14:59:59Z'), archive('2025-12-31T15:00:00Z')]
  const months = [
    { month: '2025-12', count: 1 },
    { month: '2026-01', count: 1 },
  ]
  for (const period of ['6M', '12M'] as const) {
    const data = monthlyActivity(months, period, boundary)
    expect(archiveActivity(lives, period, boundary)).toEqual(data)
    expect(data).toHaveLength(period === '6M' ? 6 : 12)
    expect(data[0]?.month).toBe(period === '6M' ? '2025-07' : '2025-01')
    expect(data.at(-1)).toMatchObject({ month: '2025-12', count: 1 })
  }
  expect(monthlyActivity(months, 'All', new Date(boundary.getTime() - 1)).at(-1)?.month).toBe(
    '2025-11',
  )
})

it('keeps the empty state when history contains only the current month', () => {
  const empty = [{ index: 0, month: '2026-02', count: 0 }]
  expect(monthlyActivity([{ month: '2026-03', count: 3 }], 'All', now)).toEqual(empty)
  expect(archiveActivity([archive('2026-03-01')], 'All', now)).toEqual(empty)
  expect(monthlyActivity([], 'All', now)).toEqual(empty)
})
