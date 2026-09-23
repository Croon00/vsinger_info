import { describe, expect, it } from 'vitest'
import { artists, lives, concerts } from '@/mocks/fixtures'
import { searchCatalog } from '@/mocks/search'
import { calendarDays, calendarEvents, changeMonth, dateKey, monthKey, todayKey } from '@/lib/dates'
import { clampTime } from '@/lib/youtube'

describe('search semantics', () => {
  it('normalizes Korean aliases and full-width Latin names', () => {
    for (const q of ['하치', 'ＨＡＣＨＩ', ' hachi '])
      expect(searchCatalog(q, artists, lives).artists.map((a) => a.id)).toEqual([1])
  })
  it('finds the same original song across performing artists at their own timestamps', () => {
    const result = searchCatalog('각성', artists, lives).performances
    expect(result.map((p) => [p.artist.id, p.start_seconds]).sort()).toEqual([
      [1, 4520],
      [3, 1755],
    ])
  })
  it('finds original-artist aliases without adding unrelated artist tiles', () => {
    const result = searchCatalog('요루시카', artists, lives)
    expect(result.artists).toHaveLength(0)
    expect(result.performances.every((p) => p.original_artist === 'ヨルシカ')).toBe(true)
    expect(result.performances.length).toBeGreaterThanOrEqual(3)
    expect(searchCatalog('   ', artists, lives)).toEqual({ artists: [], performances: [] })
  })
})
describe('calendar boundaries', () => {
  it('uses Korea dates even when UTC is the previous date', () => {
    expect(dateKey(new Date('2026-09-14T16:00:00Z'))).toBe('2026-09-15')
    expect(changeMonth('2026-12-01', 1)).toBe('2027-01-01')
    expect(changeMonth('2026-01-01', -1)).toBe('2025-12-01')
    expect(calendarDays('2026-09-01')).toHaveLength(42)
    expect(calendarDays('2026-09-01')[0]).toBe('2026-08-31')
  })
  it('rejects invalid route months', () => {
    for (const input of ['0000-01-01', '2026-13-01', '2026-02-30', ['2026-09-01']])
      expect(monthKey(input)).toBe(`${todayKey().slice(0, 7)}-01`)
  })
  it('excludes online events and preserves member birthdays', () => {
    const events = calendarEvents(
      artists,
      [{ ...concerts[0], id: 9999, event_format: 'online' }, concerts[1]],
      2027,
    )
    expect(events.filter((e) => e.kind === 'concert')).toHaveLength(1)
    expect(
      events
        .filter((e) => e.artist_id === 11 && e.kind === 'birthday')
        .map((e) => e.person)
        .sort(),
    ).toEqual(['LITA', 'NERO', 'TINA'])
    expect(events.some((e) => e.title === 'KMNZ 생일')).toBe(false)
    expect(events.find((e) => e.id === 'birthday-1')?.date).toBe('2027-01-16')
  })
  it('repeats February 29 only in leap years', () => {
    const leapArtist = { ...artists[0], birthday: '02-29' }
    expect(calendarEvents([leapArtist], [], 2028)).toHaveLength(1)
    expect(calendarEvents([leapArtist], [], 2027)).toHaveLength(0)
  })
})
it('clamps hostile or out-of-range video timestamps', () => {
  expect(clampTime('abc', 100)).toBe(0)
  expect(clampTime(-40, 100)).toBe(0)
  expect(clampTime(Infinity, 100)).toBe(0)
  expect(clampTime(999, 100)).toBe(99)
  expect(clampTime(32.9, 100)).toBe(32)
})
