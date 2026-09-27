import { describe, expect, it } from 'vitest'
import { displayName } from '@/lib/display-name'

describe('displayName', () => {
  it('appends the Korean name in parentheses', () => {
    expect(displayName('晴る', '하레루')).toBe('晴る (하레루)')
  })
  it('returns only the original when Korean is missing or identical', () => {
    expect(displayName('YOASOBI', '')).toBe('YOASOBI')
    expect(displayName('YOASOBI', null)).toBe('YOASOBI')
    expect(displayName(' Ado ', 'Ado')).toBe('Ado')
  })
  it('falls back to Korean when the original is empty', () => {
    expect(displayName('', '가수')).toBe('가수')
  })
})
