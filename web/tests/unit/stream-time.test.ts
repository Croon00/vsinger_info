import { describe, expect, it } from 'vitest'
import { isStreamWithinUpcomingWindow, streamTime } from '@/lib/stream-time'

const now = Date.parse('2026-11-14T12:00:00Z')
describe('stream time badges', () => {
  it('only includes upcoming streams from now through exactly two hours', () => {
    const upcoming = (scheduled_at: string | null) => ({
      status: 'upcoming' as const,
      scheduled_at,
    })
    expect(isStreamWithinUpcomingWindow(upcoming('2026-11-14T12:00:00Z'), now)).toBe(true)
    expect(isStreamWithinUpcomingWindow(upcoming('2026-11-14T14:00:00Z'), now)).toBe(true)
    expect(isStreamWithinUpcomingWindow(upcoming('2026-11-14T14:00:00.001Z'), now)).toBe(false)
    expect(isStreamWithinUpcomingWindow(upcoming('2026-11-14T11:59:59Z'), now)).toBe(false)
    expect(isStreamWithinUpcomingWindow(upcoming(null), now)).toBe(false)
    expect(isStreamWithinUpcomingWindow(upcoming('invalid'), now)).toBe(false)
  })
  it('keeps live broadcasts regardless of their duration or previous schedule', () => {
    expect(isStreamWithinUpcomingWindow({ status: 'live', scheduled_at: null }, now)).toBe(true)
    expect(isStreamWithinUpcomingWindow({ status: undefined }, now)).toBe(true)
  })
  it('shows elapsed time from the actual start', () => {
    expect(streamTime({ status: 'live', started_at: '2026-11-14T11:43:00Z' }, now)).toBe('17m')
    expect(streamTime({ status: 'live', started_at: '2026-11-14T09:40:00Z' }, now)).toBe('2h')
    expect(streamTime({ started_at: '2026-11-12T09:40:00Z' }, now)).toBe('2d')
  })
  it('rounds remaining minutes up and handles missing schedules', () => {
    expect(
      streamTime(
        { status: 'upcoming', started_at: null, scheduled_at: '2026-11-14T12:17:01Z' },
        now,
      ),
    ).toBe('18m')
    expect(
      streamTime(
        { status: 'upcoming', started_at: null, scheduled_at: '2026-11-14T14:17:00Z' },
        now,
      ),
    ).toBe('2h')
    expect(streamTime({ status: 'upcoming', started_at: null }, now)).toBe('예정')
  })
  it('keeps delayed broadcasts waiting until an actual start is confirmed', () => {
    expect(
      streamTime(
        { status: 'upcoming', started_at: null, scheduled_at: '2026-11-14T11:59:00Z' },
        now,
      ),
    ).toBe('대기')
  })
  it('does not invent elapsed times for invalid/missing dates or clock skew', () => {
    expect(streamTime({ status: 'live', started_at: null }, now)).toBe('LIVE')
    expect(streamTime({ status: 'live', started_at: 'invalid' }, now)).toBe('LIVE')
    expect(streamTime({ status: 'live', started_at: '2026-11-14T12:01:00Z' }, now)).toBe('0m')
  })
})
