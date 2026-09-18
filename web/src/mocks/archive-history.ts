import type { Live } from '@/api/types'
import { changeMonth, todayKey } from '@/lib/dates'

// Synthetic history for the activity preview; never associate it with a real video.
export function hachiArchiveHistory(): Live[] {
  const today = todayKey()
  const monthStart = `${today.slice(0, 7)}-01`
  const counts = [4, 7, 5, 9, 12, 8, 6, 10, 14, 11, 7, 13, 9, 15, 12, 8, 14, 10]
  return counts.flatMap((count, monthIndex) => {
    const month = changeMonth(monthStart, monthIndex - counts.length + 1).slice(0, 7)
    const lastDay = monthIndex === counts.length - 1 ? Math.max(1, Number(today.slice(-2)) - 1) : 27
    return Array.from({ length: count }, (_, index): Live => ({
      id: 10000 + monthIndex * 100 + index,
      artist_id: 1,
      title: `HACHI Singing Session ${month} #${index + 1}`,
      title_ko: `HACHI 노래 시간 · ${month} #${index + 1}`,
      broadcast_at: `${month}-${String(1 + Math.floor((index * lastDay) / count)).padStart(2, '0')}T00:00:00+09:00`,
      video_id: '',
      duration_seconds: 3600 + (index % 5) * 600,
      performances: [],
      source_url: '',
      is_sample: true,
    }))
  })
}
