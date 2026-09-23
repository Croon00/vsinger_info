import type { Album, Artist, Concert, Live, Lyrics, SearchResults } from './types'

import { request } from './http'
import { isMock } from './config'
import { backendApi } from './backend'
import { cachedRead } from './read-cache'
import { artistStatistics } from '@/lib/artist-statistics'
import { archiveActivity } from '@/lib/archive-activity'

const mockApi = {
  artists: (signal?: AbortSignal) => request<Artist[]>('/api/draft/artists', signal),
  artist: (id: string, signal?: AbortSignal) =>
    request<Artist>(`/api/draft/artists/${encodeURIComponent(id)}`, signal),
  lives: (artistId?: number, signal?: AbortSignal) =>
    cachedRead<Live[]>(`/api/draft/lives${artistId ? `?artist_id=${artistId}` : ''}`, signal),
  live: (id: string, signal?: AbortSignal) =>
    request<Live>(`/api/draft/lives/${encodeURIComponent(id)}`, signal),
  albums: (artistId: number, signal?: AbortSignal) =>
    request<Album[]>(`/api/draft/albums?artist_id=${artistId}`, signal),
  lyrics: (id: string, signal?: AbortSignal) =>
    request<Lyrics>(`/api/songs/${encodeURIComponent(id)}/lyrics`, signal),
  concerts: (
    signal?: AbortSignal,
    _options?: { artistId?: number; start?: string; end?: string },
  ) => request<Concert[]>('/api/draft/concerts', signal),
  search: (q: string, signal?: AbortSignal, _offset = 0) =>
    request<SearchResults>(`/api/draft/search?q=${encodeURIComponent(q)}`, signal),
}

export const api = isMock
  ? {
      ...mockApi,
      concert: async (id: string, signal?: AbortSignal) => {
        const result = (await mockApi.concerts(signal)).find((c) => String(c.id) === id)
        if (!result) throw new Error('찾으시는 공연이 없어요.')
        return result
      },
      livePage: async (artistId: number, offset = 0, limit = 6, signal?: AbortSignal) => {
        const all = await mockApi.lives(artistId, signal)
        return { items: all.slice(offset, offset + limit).map((live) => ({
          ...live, performance_count: live.performances.length,
        })), total: all.length, offset, limit }
      },
      statistics: async (artistId: number, signal?: AbortSignal) => {
        const lives = await mockApi.lives(artistId, signal)
        return { ...artistStatistics(lives), activity: archiveActivity(lives, 'All') }
      },
      album: async (id: string, artistId: number, signal?: AbortSignal) => {
        const albums = await mockApi.albums(artistId, signal)
        const album = albums.find((a) => a.id === id)
        if (!album) throw new Error('앨범을 찾을 수 없습니다.')
        return album
      },
    }
  : backendApi
