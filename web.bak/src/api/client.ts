import type {
  Artist,
  ArtistAgency,
  ArtistCreate,
  CandidateStatus,
  EventCandidate,
  EventCandidateCreate,
  SongCreditsUpdate,
  SongLyricsDetail,
  SongLyricsSummary,
  SpotifyTrackYouTubeLinkCreate,
  Source,
  SourceCreate,
  SpotifyAlbum,
  SpotifyAlbumDetail,
  SpotifyArtist,
  SpotifyArtistCandidate,
  SpotifyArtistProfile,
  SpotifyRelationship,
  EventType,
  EventFormat,
  YouTubeLiveArchive,
  YouTubePerformance,
  YouTubePerformanceSearchResult,
  YouTubePerformanceFilters,
  LyricsSourceMode,
  WebSongCreated,
} from './types'

const API_BASE = (import.meta.env.VITE_API_BASE_URL || '/api-proxy').replace(/\/$/, '')

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message)
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...init?.headers,
    },
  })

  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string } | null
    throw new ApiError(body?.detail || `요청을 처리하지 못했습니다. (${response.status})`, response.status)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export const api = {
  health: () => request<{ status: string }>('/health'),
  artistAgencies: {
    list: () => request<ArtistAgency[]>('/artist-agencies'),
    create: (name: string) =>
      request<ArtistAgency>('/artist-agencies', { method: 'POST', body: JSON.stringify({ name }) }),
  },
  songs: {
    createFromYouTube: (payload: { artist_id: number; title: string; youtube_url: string; source_mode: LyricsSourceMode; language_code: string }) =>
      request<WebSongCreated>('/songs/from-youtube', { method: 'POST', body: JSON.stringify(payload) }),
    lyricsForSpotifyTracks: (trackIds: string[]) => {
      const params = new URLSearchParams()
      trackIds.forEach((trackId) => params.append('ids', trackId))
      return request<SongLyricsSummary[]>(`/songs/lyrics/by-spotify-tracks?${params.toString()}`)
    },
    lyrics: (songId: number) => request<SongLyricsDetail>(`/songs/${songId}/lyrics`),
    linkSpotifyTrackYouTube: (payload: SpotifyTrackYouTubeLinkCreate) =>
      request<SongLyricsSummary>('/songs/spotify-track-youtube', { method: 'POST', body: JSON.stringify(payload) }),
    updateCredits: (songId: number, payload: SongCreditsUpdate) =>
      request<SongLyricsSummary>(`/songs/${songId}/credits`, { method: 'PATCH', body: JSON.stringify(payload) }),
  },
  artists: {
    list: () => request<Artist[]>('/artists?grouped=true'),
    registrations: () => request<Artist[]>('/artists'),
    create: (payload: ArtistCreate) =>
      request<Artist>('/artists', { method: 'POST', body: JSON.stringify(payload) }),
    update: (id: number, payload: Partial<ArtistCreate>) =>
      request<Artist>(`/artists/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
    remove: (id: number) => request<void>(`/artists/${id}`, { method: 'DELETE' }),
    addSource: (artistId: number, payload: SourceCreate) =>
      request<Source>(`/artists/${artistId}/sources`, {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    removeSource: (artistId: number, sourceId: number) =>
      request<void>(`/artists/${artistId}/sources/${sourceId}`, { method: 'DELETE' }),
  },
  events: {
    list: (status?: CandidateStatus, artistId?: number, eventType?: EventType, eventFormat?: EventFormat) => {
      const params = new URLSearchParams()
      if (status) params.set('status_filter', status)
      if (artistId) params.set('artist_id', String(artistId))
      if (eventType) params.set('event_type', eventType)
      if (eventFormat) params.set('event_format', eventFormat)
      const query = params.toString()
      return request<EventCandidate[]>(
        `/event-candidates${query ? `?${query}` : ''}`,
      )
    },
    create: (payload: EventCandidateCreate) =>
      request<EventCandidate>('/event-candidates', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
  },
  youtubeLives: {
    list: (artistName?: string, limit = 100) => {
      const params = new URLSearchParams({ limit: String(limit) })
      if (artistName) params.set('artist_name', artistName)
      if (artistName) params.set('all_records', 'true')
      return request<YouTubeLiveArchive[]>(`/youtube-lives?${params.toString()}`)
    },
    get: (id: number) => request<YouTubeLiveArchive>(`/youtube-lives/${id}`),
    create: (youtubeUrl: string, artistName: string) => request<YouTubeLiveArchive>('/youtube-lives', {
      method: 'POST', body: JSON.stringify({ youtube_url: youtubeUrl, artist_name: artistName }),
    }),
  },
  youtubeCovers: {
    list: (artistId?: number, collaboratorId?: number, limit = 500) => {
      const params = new URLSearchParams({ limit: String(limit) })
      if (artistId) params.set('artist_id', String(artistId))
      if (collaboratorId) params.set('collaborator_id', String(collaboratorId))
      return request<import('./types').YouTubeCoverVideo[]>(`/youtube-covers?${params.toString()}`)
    },
  },
  youtubePerformances: {
    stats: (groupBy: 'song' | 'original_artist') => request<Array<{ label: string; korean_label: string | null; count: number }>>(`/youtube-performance-stats?group_by=${groupBy}`),
    filters: () => request<YouTubePerformanceFilters>('/youtube-performance-filters'),
    search: (filters: { artists: string[]; songs: string[]; originalArtists: string[] }) => {
      const params = new URLSearchParams({ limit: '500' })
      filters.artists.forEach((value) => params.append('artist_name', value))
      filters.songs.forEach((value) => params.append('song_title', value))
      filters.originalArtists.forEach((value) => params.append('original_artist', value))
      return request<YouTubePerformanceSearchResult[]>(`/youtube-performances?${params.toString()}`)
    },
    update: (id: number, payload: Partial<Pick<YouTubePerformance, 'song_title' | 'song_title_ko' | 'original_artist' | 'original_artist_ko'>>) =>
      request<YouTubePerformance>(`/youtube-performances/${id}`, {
        method: 'PATCH', body: JSON.stringify(payload),
      }),
  },
  google: {
    connectUrl: (discordUserId: string) =>
      `${API_BASE}/auth/google/start?discord_user_id=${encodeURIComponent(discordUserId)}`,
  },
  spotify: {
    artists: () => request<SpotifyArtist[]>('/spotify/artists'),
    artistCandidates: (artistId: number) =>
      request<SpotifyArtistCandidate[]>(`/spotify/artists/${artistId}/candidates`),
    artistProfile: (artistId: number) =>
      request<SpotifyArtistProfile>(`/spotify/artists/${artistId}/profile`),
    syncArtist: (artistId: number, spotifyArtistId: string) =>
      request<SpotifyArtist>(`/spotify/artists/${artistId}/sync?spotify_artist_id=${encodeURIComponent(spotifyArtistId)}`, { method: 'POST' }),
    autoLinkYouTube: (artistId: number) =>
      request<SpotifyArtist>(`/spotify/artists/${artistId}/youtube-auto-link`, { method: 'POST' }),
    excludeArtist: (artistId: number) =>
      request<void>(`/spotify/artists/${artistId}`, { method: 'DELETE' }),
    discography: (artistId: number) =>
      request<SpotifyAlbum[]>(`/spotify/artists/${artistId}/discography`),
    album: (albumId: string) =>
      request<SpotifyAlbumDetail>(`/spotify/albums/${encodeURIComponent(albumId)}`),
    relationships: () => request<SpotifyRelationship[]>('/spotify/relationships'),
  },
}
