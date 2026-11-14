import type { LiveStream } from '@/api/types'

export function isStreamWithinUpcomingWindow(
  stream: Pick<LiveStream, 'status' | 'scheduled_at'>,
  now: number,
) {
  if (stream.status !== 'upcoming') return true
  const scheduled = stream.scheduled_at ? Date.parse(stream.scheduled_at) : NaN
  return Number.isFinite(scheduled) && scheduled >= now && scheduled <= now + 2 * 3600000
}

export function streamTime(
  stream: Pick<LiveStream, 'status' | 'started_at' | 'scheduled_at'>,
  now: number,
) {
  const upcoming = stream.status === 'upcoming'
  const value = upcoming ? stream.scheduled_at : stream.started_at
  const time = value ? Date.parse(value) : NaN
  if (!Number.isFinite(time)) return upcoming ? '예정' : 'LIVE'
  // The schedule passing is not evidence that a stream actually started.
  if (upcoming && time <= now) return '대기'
  const minutes = upcoming
    ? Math.ceil((time - now) / 60000)
    : Math.max(0, Math.floor((now - time) / 60000))
  if (minutes < 60) return `${minutes}m`
  if (minutes < 1440) return `${Math.floor(minutes / 60)}h`
  return `${Math.floor(minutes / 1440)}d`
}
