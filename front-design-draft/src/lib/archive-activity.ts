import type { Live } from '@/api/types'
import { dateKey } from '@/lib/dates'

export type ActivityPeriod = '6M' | '12M' | 'All'
export function archiveActivity(lives: Live[], period: ActivityPeriod, now = new Date()) {
  const toIndex = (key: string) => Number(key.slice(0, 4)) * 12 + Number(key.slice(5, 7)) - 1
  const end = toIndex(dateKey(now))
  const counts = new Map<number, number>()
  for (const live of lives) {
    const date = new Date(live.broadcast_at)
    if (!Number.isFinite(date.getTime()) || date > now) continue
    const month = toIndex(dateKey(date))
    counts.set(month, (counts.get(month) ?? 0) + 1)
  }
  const start =
    period === 'All' ? Math.min(end, ...counts.keys()) : end - (period === '6M' ? 5 : 11)
  return Array.from({ length: end - start + 1 }, (_, index) => {
    const month = start + index
    return {
      index,
      month: `${Math.floor(month / 12)}-${String((month % 12) + 1).padStart(2, '0')}`,
      count: counts.get(month) ?? 0,
    }
  })
}
