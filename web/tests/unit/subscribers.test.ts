import { expect, it } from 'vitest'
import { formatSubscribers } from '@/lib/subscribers'
it('formats Korean subscriber counts and unknown values', () => {
  expect(formatSubscribers(121000)).toBe('12.1만')
  expect(formatSubscribers(10000)).toBe('1만')
  expect(formatSubscribers(99999)).toBe('9.9만')
  expect(formatSubscribers(1230000)).toBe('123만')
  expect(formatSubscribers(100000000)).toBe('1억')
  expect(formatSubscribers(9999)).toBe('9,999')
  expect(formatSubscribers(0)).toBe('0')
  expect(formatSubscribers(null)).toBe('—')
  expect(formatSubscribers(undefined)).toBe('—')
})
