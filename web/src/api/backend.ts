import type {
  Album,
  Artist,
  Concert,
  Live,
  Lyrics,
  Performance,
  SearchResults,
  Page,
  Statistics,
} from './types'
import type {
  BackendArtist,
  BackendLive,
  BackendPerformance,
  BackendSearchPerformance,
  BackendAlbum,
  BackendLyricsSummary,
  BackendLyrics,
  BackendEvent,
} from './backend-types'
import { cachedRead } from './read-cache'
import { normalize } from '@/lib/search'
import { formatTime } from '@/lib/dates'

export function safeUrl(value?: string | null) {
  try {
    const url = new URL(value ?? '')
    return ['http:', 'https:'].includes(url.protocol) ? url.href : ''
  } catch {
    return ''
  }
}
export function videoId(value: string) {
  try {
    const url = new URL(value)
    const host = url.hostname.replace(/^www\./, '')
    const id =
      host === 'youtu.be'
        ? url.pathname.slice(1)
        : ['youtube.com', 'm.youtube.com', 'youtube-nocookie.com'].includes(host)
          ? url.searchParams.get('v') ||
            url.pathname.match(/^\/(?:embed|live|shorts)\/([^/]+)/)?.[1]
          : ''
    return id && /^[\w-]{11}$/.test(id) ? id : ''
  } catch {
    return ''
  }
}
export function mapArtist(row: BackendArtist): Artist {
  const links = (row.sources ?? [])
    .filter((s) => s.is_active)
    .flatMap((s) => {
      const url = safeUrl(
        s.source_type === 'x' && !s.value.startsWith('http')
          ? `https://x.com/${s.value.replace(/^@/, '')}`
          : s.value,
      )
      if (!url) return []
      const label =
        s.source_type === 'official_site'
          ? '공식 사이트'
          : new URL(url).hostname.includes('youtube.com')
            ? 'YouTube'
            : s.source_type === 'x'
              ? 'X'
              : s.label || '관련 사이트'
      return [{ label, url }]
    })
  return {
    id: row.id,
    name: row.name,
    display_name: '',
    roman: '',
    agency: row.agency ?? '',
    aliases: [
      ...new Set([row.name, row.display_name ?? '', ...(row.name_aliases ?? [])].filter(Boolean)),
    ],
    related_artist_ids: [...new Set([row.id, ...(row.related_artist_ids ?? [])])],
    image: safeUrl(row.spotify_image_url),
    image_source: '',
    official_url: links.find((l) => l.label === '공식 사이트')?.url ?? '',
    links,
    birthday: null,
    intro: row.profile_intro ?? '',
  }
}
export function matchArtist(name: string, artists: Artist[]) {
  const key = normalize(name)
  if (!key) return undefined
  const matches = artists.filter((a) =>
    [a.name, ...(a.aliases ?? [])].some((alias) => normalize(alias) === key),
  )
  return matches.length === 1 ? matches[0] : undefined
}
export function mapPerformance(row: BackendPerformance): Performance {
  return {
    id: row.id,
    song_title: row.song_title,
    song_title_ko: row.song_title_ko ?? '',
    original_artist: row.original_artist ?? '',
    original_artist_ko: row.original_artist_ko ?? '',
    start_seconds: Math.max(0, row.start_seconds ?? 0),
  }
}
export function mapLive(row: BackendLive, artist?: Artist): Live {
  return {
    id: row.id,
    artist_id: artist?.id ?? row.artist_id ?? null,
    title: row.video_title || row.artist_name || '라이브 아카이브',
    title_ko: '',
    video_id:
      videoId(row.youtube_url) ||
      (/^[\w-]{11}$/.test(row.youtube_video_id ?? '') ? row.youtube_video_id! : ''),
    broadcast_at: row.broadcast_at || row.published_at || '',
    duration_seconds: row.duration_seconds ?? 0,
    performances: (row.performances ?? [])
      .map(mapPerformance)
      .sort((a, b) => a.start_seconds - b.start_seconds),
    source_url: safeUrl(row.youtube_url),
  }
}
export function mapEvent(row: BackendEvent, artists: Artist[]): Concert | null {
  // A local datetime without an offset cannot be safely converted to Seoul time.
  // Keep its stated day, but do not invent a time or timezone.
  const startsAt = row.starts_at?.trim() ?? ''
  const hasOffset = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(startsAt)
  const starts = hasOffset ? startsAt : startsAt.slice(0, 10)
  if (
    row.event_type !== 'live_event' ||
    !['ready', 'synced'].includes(row.status) ||
    !['onsite', 'hybrid'].includes(row.event_format) ||
    !/^\d{4}-\d{2}-\d{2}(?:$|[T ])/.test(startsAt) ||
    !Number.isFinite(Date.parse(starts))
  )
    return null
  const artist = artists.find((a) => (a.related_artist_ids ?? [a.id]).includes(row.artist_id ?? -1))
  if (!artist) return null
  return {
    id: row.id,
    artist_id: artist.id,
    title: row.title,
    starts_at: starts,
    venue: row.venue ?? '',
    city: '',
    price_text: row.price_text ?? '',
    source_url: safeUrl(row.source_url),
    ticket_url: safeUrl(row.ticket_url),
    is_sample: false,
    event_format: row.event_format as 'onsite' | 'hybrid',
  }
}
function mapAlbum(row: BackendAlbum, artistId: number): Album {
  return {
    id: row.id,
    artist_id: artistId,
    name: row.name,
    album_type: row.album_type === 'single' ? 'single' : 'album',
    release_date: row.release_date ?? '',
    image_url: safeUrl(row.image_url),
    source_url: safeUrl(row.spotify_url),
    total_tracks: row.total_tracks,
    tracks: [],
    tracks_loaded: false,
    is_sample: false,
  }
}

async function artists(signal?: AbortSignal) {
  return (await cachedRead<BackendArtist[]>('/api/v2/artists', signal)).map(mapArtist)
}
async function artist(id: string, signal?: AbortSignal) {
  const all = await artists(signal)
  return (
    all.find((a) => (a.related_artist_ids ?? [a.id]).includes(Number(id))) ??
    mapArtist(await cachedRead<BackendArtist>(`/api/v2/artists/${encodeURIComponent(id)}`, signal))
  )
}
export const backendApi = {
  artists,
  artist,
  async livePage(
    artistId: number,
    offset = 0,
    limit = 6,
    signal?: AbortSignal,
  ): Promise<Page<Live>> {
    const result = await cachedRead<Page<BackendLive>>(
      `/api/v2/artists/${artistId}/lives?offset=${offset}&limit=${limit}`,
      signal,
    )
    return { ...result, items: result.items.map((row) => mapLive(row)) }
  },
  async statistics(artistId: number, signal?: AbortSignal): Promise<Statistics> {
    const result = await cachedRead<Statistics>(`/api/v2/artists/${artistId}/statistics`, signal)
    return {
      ...result,
      songs: result.songs.map((song) => ({ ...song, searchText: normalize(song.searchText) })),
    }
  },
  async live(id: string, signal?: AbortSignal) {
    const [row, all] = await Promise.all([
      cachedRead<BackendLive>(`/api/v2/lives/${encodeURIComponent(id)}`, signal),
      artists(signal),
    ])
    return mapLive(row, matchArtist(row.artist_name, all))
  },
  async albums(artistId: number, signal?: AbortSignal) {
    return (
      await cachedRead<BackendAlbum[]>(`/api/v2/spotify/artists/${artistId}/discography`, signal)
    ).map((row) => mapAlbum(row, artistId))
  },
  async album(id: string, artistId: number, signal?: AbortSignal): Promise<Album> {
    const row = await cachedRead<BackendAlbum>(
      `/api/v2/spotify/albums/${encodeURIComponent(id)}`,
      signal,
    )
    const tracks = [...(row.tracks ?? [])].sort(
      (a, b) => a.disc_number - b.disc_number || a.track_number - b.track_number,
    )
    const summaries: BackendLyricsSummary[] = []
    // Bound URL size; these are reads of stored lyrics, never generation requests.
    for (let offset = 0; offset < tracks.length; offset += 50) {
      const query = new URLSearchParams()
      tracks.slice(offset, offset + 50).forEach((t) => query.append('ids', t.id))
      summaries.push(
        ...(await cachedRead<BackendLyricsSummary[]>(
          `/api/songs/lyrics/by-spotify-tracks?${query}`,
          signal,
        )),
      )
    }
    return {
      ...mapAlbum(row, artistId),
      tracks_loaded: true,
      tracks: tracks.map((t) => {
        const lyrics = summaries.find((l) => l.spotify_track_id === t.id)
        return {
          id: t.id,
          song_id: lyrics?.song_id,
          title: t.name,
          title_ko: t.name_ko ?? '',
          duration: t.duration_ms ? formatTime(t.duration_ms / 1000) : '',
          has_lyrics: !!lyrics?.has_lyrics,
        }
      }),
    }
  },
  async lyrics(id: string, signal?: AbortSignal): Promise<Lyrics> {
    const row = await cachedRead<BackendLyrics>(
      `/api/songs/${encodeURIComponent(id)}/lyrics`,
      signal,
    )
    return { ...row, is_sample: false }
  },
  async concerts(
    signal?: AbortSignal,
    options: { artistId?: number; start?: string; end?: string } = {},
  ) {
    const all = await artists(signal)
    const rows: BackendEvent[] = []
    for (let offset = 0; ; offset += 100) {
      const query = new URLSearchParams({ offset: String(offset), limit: '100' })
      if (options.artistId) query.set('artist_id', String(options.artistId))
      if (options.start) query.set('start', options.start)
      if (options.end) query.set('end', options.end)
      const page = await cachedRead<Page<BackendEvent>>(`/api/v2/concerts?${query}`, signal)
      rows.push(...page.items)
      if (!page.items.length || offset + page.items.length >= page.total) break
    }
    return rows.flatMap((row) => {
      const event = mapEvent(row, all)
      return event ? [event] : []
    })
  },
  async concert(id: string, signal?: AbortSignal): Promise<Concert> {
    const [row, all] = await Promise.all([
      cachedRead<BackendEvent>(`/api/v2/concerts/${encodeURIComponent(id)}`, signal),
      artists(signal),
    ])
    const result = mapEvent(row, all)
    if (!result) throw new Error('찾으시는 공연이 없어요.')
    return result
  },
  async search(q: string, signal?: AbortSignal, offset = 0): Promise<SearchResults> {
    if (!q.trim()) return { artists: [], performances: [], total: 0 }
    const query = q.trim()
    const [all, result] = await Promise.all([
      artists(signal),
      cachedRead<Page<BackendSearchPerformance>>(
        `/api/v2/search?${new URLSearchParams({ q: query, offset: String(offset), limit: '50' })}`,
        signal,
      ),
    ])
    return {
      artists: all.filter((a) =>
        [a.name, ...(a.aliases ?? [])].some((name) => normalize(name).includes(normalize(query))),
      ),
      total: result.total,
      performances: result.items.map((row) => {
        const owner =
          all.find((a) => (a.related_artist_ids ?? [a.id]).includes(row.artist_id ?? -1)) ??
          matchArtist(row.artist_name, all)
        return {
          ...mapPerformance(row),
          artist: owner ?? { id: null, name: row.artist_name, display_name: '' },
          live: mapLive({ ...row, id: row.archive_id, broadcast_at: row.performed_on }, owner),
        }
      }),
    }
  },
}
