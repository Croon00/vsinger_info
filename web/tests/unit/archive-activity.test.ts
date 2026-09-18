import { expect, it } from 'vitest'
import type { Live } from '@/api/types'
import { archiveActivity } from '@/lib/archive-activity'
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
  expect(data[0]?.month).toBe('2025-10')
  expect(data.find((d) => d.month === '2026-01')?.count).toBe(2)
  expect(data.at(-1)?.count).toBe(0)
})
it('supports twelve months, full history and an empty history', () => {
  expect(archiveActivity([], '12M', now)).toHaveLength(12)
  expect(archiveActivity([archive('2024-01-01')], 'All', now)).toHaveLength(27)
  expect(archiveActivity([], 'All', now)).toEqual([{ index: 0, month: '2026-03', count: 0 }])
})
