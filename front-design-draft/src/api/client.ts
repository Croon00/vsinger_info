import type { Album, Artist, Concert, Live, Lyrics, SearchResults } from './types'

export async function request<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(path, { signal, headers: { Accept: 'application/json' } })
  if (!response.ok) {
    if (response.status === 404) throw new Error('찾으시는 콘텐츠가 없어요.')
    throw new Error('잠시 연결이 어려워요. 다시 시도해 주세요.')
  }
  return response.json() as Promise<T>
}
export const api = {
  artists: (signal?: AbortSignal) => request<Artist[]>('/api/draft/artists', signal),
  artist: (id: string, signal?: AbortSignal) =>
    request<Artist>(`/api/draft/artists/${encodeURIComponent(id)}`, signal),
  lives: (artistId?: number, signal?: AbortSignal) =>
    request<Live[]>(`/api/draft/lives${artistId ? `?artist_id=${artistId}` : ''}`, signal),
  live: (id: string, signal?: AbortSignal) =>
    request<Live>(`/api/draft/lives/${encodeURIComponent(id)}`, signal),
  albums: (artistId: number, signal?: AbortSignal) =>
    request<Album[]>(`/api/draft/albums?artist_id=${artistId}`, signal),
  lyrics: (id: string, signal?: AbortSignal) =>
    request<Lyrics>(`/api/songs/${encodeURIComponent(id)}/lyrics`, signal),
  concerts: (signal?: AbortSignal) => request<Concert[]>('/api/draft/concerts', signal),
  search: (q: string, signal?: AbortSignal) =>
    request<SearchResults>(`/api/draft/search?q=${encodeURIComponent(q)}`, signal),
}
