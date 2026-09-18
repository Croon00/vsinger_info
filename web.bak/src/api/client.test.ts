import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from './client'

describe('FastAPI client', () => {
  afterEach(() => vi.restoreAllMocks())

  it('requests all saved broadcasts for artist statistics', async () => {
    const fetch = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('[]', { status: 200 }))
    await api.youtubeLives.list('HACHI')
    const url = String(fetch.mock.calls[0]?.[0])
    expect(url).toContain('artist_name=HACHI')
    expect(url).toContain('all_records=true')
  })

  it('returns typed artist records', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify([{ id: 1, name: 'HACHI', display_name: null, notes: null, sources: [], created_at: '', updated_at: '' }]), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    const artists = await api.artists.list()
    expect(artists[0]?.name).toBe('HACHI')
  })

  it('surfaces FastAPI detail messages', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ detail: '이미 등록된 출처입니다.' }), {
        status: 409,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    await expect(api.artists.list()).rejects.toThrow('이미 등록된 출처입니다.')
  })
})
