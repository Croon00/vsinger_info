import { describe, it, expect } from 'vitest'
import { inMonthRange, searchKey } from './archiveFilters'

describe('archive month filters', () => {
  it('includes undated records only in the default full range', () => {
    expect(inMonthRange(null, '', '')).toBe(true)
    expect(inMonthRange(null, '2024-01', '')).toBe(false)
  })
  it('uses inclusive months in Korean time including UTC month boundaries', () => {
    expect(inMonthRange('2024-08-31T15:00:00Z', '2024-09', '2024-09')).toBe(true)
    expect(inMonthRange('2024-08-31T14:59:59Z', '2024-09', '')).toBe(false)
    expect(inMonthRange('2024-09-30T15:00:00Z', '', '2024-09')).toBe(false)
    expect(inMonthRange('2024-09-10', '2025-01', '2024-01')).toBe(false)
  })
  it('matches song names despite spaces or decorative symbols', () => {
    expect(searchKey('いきのこり●ぼくら')).toBe(searchKey('いきのこり ぼくら'))
    expect(searchKey('생존, 우리')).toBe(searchKey('생존우리'))
  })
})
