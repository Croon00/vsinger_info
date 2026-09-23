import { describe, expect, it } from 'vitest'
import { avatarImageSource } from '../../src/lib/avatar-image'
const variants = { '128': '/128.webp', '256': '/256.webp', '512': '/512.webp' }
describe('avatar image selection', () => {
  it('matches CSS size and pixel density without downloading originals', () => {
    expect(avatarImageSource('/original', variants, 64, 2)).toBe('/128.webp')
    expect(avatarImageSource('/original', variants, 116, 2)).toBe('/256.webp')
    expect(avatarImageSource('/original', variants, 168, 2)).toBe('/512.webp')
    expect(avatarImageSource('/original', variants, 200, 3)).toBe('/512.webp')
  })
  it('keeps external and mock URLs working', () => {
    expect(avatarImageSource('/old', undefined, 64, 2)).toBe('/old')
    expect(avatarImageSource('/old', {}, 64, 2)).toBe('/old')
  })
})
