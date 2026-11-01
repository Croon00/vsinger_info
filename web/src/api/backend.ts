import type {
  Album,
  ExploredSong,
  SongKind,
  Cover,
  Artist,
  Concert,
  Live,
  Lyrics,
  Performance,
  SearchResults,
  SearchOptions,
  Page,
  Statistics,
} from './types'
import type {
  BackendArtist,
  BackendLive,
  BackendPerformance,
  BackendSearchPerformance,
  BackendAlbum,
  BackendLyrics,
  BackendEvent,
} from './backend-types'
import { cachedRead } from './read-cache'
import { normalize } from '@/lib/search'
import { formatTrackLength } from '@/lib/dates'

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
        s.label ||
        (s.source_type === 'official_site'
          ? '공식 사이트'
          : new URL(url).hostname.includes('youtube.com')
            ? 'YouTube'
            : s.source_type === 'x'
              ? 'X'
              : s.source_type === 'spotify'
                ? 'Spotify'
                : s.source_type === 'fanclub'
                  ? '팬클럽'
                  : '관련 사이트')
      return [{ label, url }]
    })
  return {
    id: row.id,
    name: row.name,
    display_name: row.display_name ?? '',
    roman: row.name_latin ?? '',
    theme_color: row.theme_color ?? undefined,
    agency: row.agency ?? '',
    aliases: [
      ...new Set(
        [
          row.name,
          row.display_name ?? '',
          row.name_latin ?? '',
          ...(row.name_aliases ?? []),
        ].filter(Boolean),
      ),
    ],
    related_artist_ids: [...new Set([row.id, ...(row.related_artist_ids ?? [])])],
    image: safeUrl(row.spotify_image_url),
    image_variants: Object.fromEntries(
      Object.entries(row.avatar_variants ?? {})
        .map(([size, url]) => [size, safeUrl(url)])
        .filter(([, url]) => url),
    ),
    image_source: '',
    official_url: links.find((l) => l.label === '공식 사이트')?.url ?? '',
    links,
    birthday: row.birthday ?? null,
    debut_date: row.debut_date ?? null,
    youtube_subscriber_count: row.youtube_subscriber_count ?? null,
    youtube_channel_created_at: row.youtube_channel_created_at ?? null,
    youtube_statistics_updated_at: row.youtube_statistics_updated_at ?? null,
    youtube_statistics_source: row.youtube_statistics_source ?? null,
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
    performance_count: row.performance_count ?? null,
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
    !['scheduled', 'completed', 'postponed', 'ready', 'synced'].includes(row.status) ||
    !['onsite', 'hybrid', 'online'].includes(row.event_format) ||
    (!!startsAt &&
      (!/^\d{4}-\d{2}-\d{2}(?:$|[T ])/.test(startsAt) || !Number.isFinite(Date.parse(starts))))
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
    city: row.city ?? '',
    artist_ids: row.artist_ids ?? [artist.id],
    price_text: row.price_text ?? '',
    source_url: safeUrl(row.source_url),
    ticket_url: safeUrl(row.ticket_url),
    is_sample: false,
    event_format: row.event_format as 'onsite' | 'hybrid' | 'online',
  }
}
function mapAlbum(row: BackendAlbum, artistId: number): Album {
  return {
    id: row.id,
    artist_id: artistId,
    name: row.name,
    album_type: row.album_type as Album['album_type'],
    release_date: row.release_date ?? '',
    image_url: safeUrl(row.image_url),
    source_url: safeUrl(row.spotify_url),
    total_tracks: row.total_tracks,
    is_primary: row.is_primary ?? undefined,
    tracks: [],
    tracks_loaded: false,
    is_sample: false,
  }
}

async function artists(signal?: AbortSignal) {
  return (await cachedRead<BackendArtist[]>('/api/artists', signal)).map(mapArtist)
}
async function artist(id: string, signal?: AbortSignal) {
  const all = await artists(signal)
  return (
    all.find((a) => (a.related_artist_ids ?? [a.id]).includes(Number(id))) ??
    mapArtist(await cachedRead<BackendArtist>(`/api/artists/${encodeURIComponent(id)}`, signal))
  )
}
export const backendApi = {
  songPerformers(
    songKey: string,
    agency = 'all',
    signal?: AbortSignal,
  ): Promise<Pick<Artist, 'id' | 'name' | 'display_name'>[]> {
    return cachedRead(
      `/api/explore/song-performers?${new URLSearchParams({ song_key: songKey, agency })}`,
      signal,
    )
  },
  searchPerformers(
    q: string,
    agency = 'all',
    artistId?: number,
    signal?: AbortSignal,
  ): Promise<Pick<Artist, 'id' | 'name' | 'display_name'>[]> {
    const params = new URLSearchParams({ q, agency })
    if (artistId) params.set('artist_id', String(artistId))
    return cachedRead(`/api/search/performers?${params}`, signal)
  },
  songPage(
    kind: SongKind,
    agency: string,
    q: string,
    order: string,
    offset = 0,
    signal?: AbortSignal,
    artistIds: number[] = [],
    period: { start?: string; end?: string } = {},
  ): Promise<Page<ExploredSong>> {
    const params = new URLSearchParams({
      kind,
      agency,
      q,
      order,
      offset: String(offset),
      limit: '24',
    })
    for (const id of artistIds) params.append('artist_ids', String(id))
    if (period.start) params.set('start', period.start)
    if (period.end) params.set('end', period.end)
    return cachedRead<Page<ExploredSong>>(`/api/explore/songs?${params}`, signal)
  },
  artists,
  artist,
  coverPage(artistId: number, offset = 0, limit = 12, signal?: AbortSignal): Promise<Page<Cover>> {
    return cachedRead<Page<Cover>>(
      `/api/artists/${artistId}/covers?offset=${offset}&limit=${limit}`,
      signal,
    )
  },
  async livePage(
    artistId: number,
    offset = 0,
    limit = 6,
    signal?: AbortSignal,
  ): Promise<Page<Live>> {
    const result = await cachedRead<Page<BackendLive>>(
      `/api/artists/${artistId}/lives?offset=${offset}&limit=${limit}`,
      signal,
    )
    return { ...result, items: result.items.map((row) => mapLive(row)) }
  },
  async statistics(artistId: number, signal?: AbortSignal): Promise<Statistics> {
    const result = await cachedRead<Statistics>(`/api/artists/${artistId}/statistics`, signal)
    return {
      ...result,
      songs: result.songs.map((song) => ({ ...song, searchText: normalize(song.searchText) })),
    }
  },
  async live(id: string, signal?: AbortSignal) {
    return mapLive(await cachedRead<BackendLive>(`/api/lives/${encodeURIComponent(id)}`, signal))
  },
  async albums(artistId: number, signal?: AbortSignal) {
    return (await cachedRead<BackendAlbum[]>(`/api/artists/${artistId}/albums`, signal)).map(
      (row) => mapAlbum(row, artistId),
    )
  },
  async album(id: string, artistId: number, signal?: AbortSignal): Promise<Album> {
    const row = await cachedRead<BackendAlbum>(`/api/albums/${encodeURIComponent(id)}`, signal)
    const tracks = [...(row.tracks ?? [])].sort(
      (a, b) => a.disc_number - b.disc_number || a.track_number - b.track_number,
    )
    return {
      ...mapAlbum(row, artistId),
      tracks_loaded: true,
      tracks: tracks.map((t) => {
        return {
          id: t.id,
          song_id: t.song_id ?? undefined,
          lyrics_id: t.recording_id,
          title: t.name,
          title_ko: t.name_ko ?? '',
          duration: t.duration_ms ? formatTrackLength(t.duration_ms) : '',
          duration_ms: t.duration_ms ?? undefined,
          disc_number: t.disc_number,
          track_number: t.track_number,
          has_lyrics: t.has_lyrics,
          youtube_url: videoId(t.youtube_url ?? '')
            ? `https://www.youtube.com/watch?v=${videoId(t.youtube_url ?? '')}`
            : undefined,
          artists: (t.artists ?? []).map((a) => ({
            id: a.artist_id ?? undefined,
            name: a.name,
            name_ko: a.name_ko ?? '',
          })),
        }
      }),
    }
  },
  async lyrics(id: string, signal?: AbortSignal): Promise<Lyrics> {
    const row = await cachedRead<BackendLyrics>(
      `/api/recordings/${encodeURIComponent(id)}/lyrics`,
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
      const page = await cachedRead<Page<BackendEvent>>(`/api/concerts?${query}`, signal)
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
      cachedRead<BackendEvent>(`/api/concerts/${encodeURIComponent(id)}`, signal),
      artists(signal),
    ])
    const result = mapEvent(row, all)
    if (!result) throw new Error('찾으시는 공연이 없어요.')
    return result
  },
  async search(
    q: string,
    signal?: AbortSignal,
    offset = 0,
    options: SearchOptions = {},
  ): Promise<SearchResults> {
    if (!q.trim()) return { artists: [], performances: [], total: 0 }
    const query = q.trim()
    const params = new URLSearchParams({ q: query, offset: String(offset), limit: '50' })
    if (options.artistId) params.set('artist_id', String(options.artistId))
    if (options.songKey) params.set('song_key', options.songKey)
    if (options.agency) params.set('agency', options.agency)
    for (const id of options.artistIds ?? []) params.append('artist_ids', String(id))
    if (options.start) params.set('start', options.start)
    if (options.end) params.set('end', options.end)
    const [all, result] = await Promise.all([
      artists(signal),
      cachedRead<Page<BackendSearchPerformance>>(`/api/search?${params}`, signal),
    ])
    return {
      artists:
        options.artistId ||
        options.songKey ||
        options.artistIds?.length ||
        options.start ||
        options.end
          ? []
          : all.filter((a) =>
              [a.name, ...(a.aliases ?? [])].some((name) =>
                normalize(name).includes(normalize(query)),
              ),
            ),
      total: result.total,
      performances: result.items.map((row) => {
        const owner = all.find((a) =>
          (a.related_artist_ids ?? [a.id]).includes(options.artistId ?? row.artist_id ?? -1),
        )
        return {
          ...mapPerformance(row),
          artist: owner ?? {
            id: null,
            name: row.artist_name,
            display_name: row.artist_name_ko ?? '',
          },
          live: mapLive(
            { ...row, id: row.archive_id, broadcast_at: row.broadcast_at || row.performed_on },
            owner,
          ),
        }
      }),
    }
  },
}
