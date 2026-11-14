export interface StreamGroup {
  key: string
  name: string
  kind: 'agency' | 'group'
  account_ids: number[]
}

export interface LiveStream {
  account_id: number
  channel_id: string
  artist_id: number
  artist_name: string
  video_id: string
  title: string
  status?: 'live' | 'upcoming'
  started_at: string | null
  scheduled_at?: string | null
  avatar_url?: string
  avatar_variants?: Record<string, string>
  checked_at: string
}

export interface SearchOptions {
  artistId?: number
  artistIds?: number[]
  songKey?: string
  agency?: string
  start?: string
  end?: string
}
export interface Link {
  label: string
  url: string
}
export interface Artist {
  original_song_group?: { id: number; name: string; agency: string | null } | null
  theme_color?: string
  id: number
  name: string
  display_name: string
  aliases?: string[]
  related_artist_ids?: number[]
  member_birthdays?: { name: string; date: string }[]
  roman: string
  agency: string
  image: string
  image_source: string
  image_variants?: Record<string, string>
  image_position?: string
  official_url: string
  links: Link[]
  birthday: string | null
  debut_date?: string | null
  youtube_subscriber_count?: number | null
  youtube_channel_created_at?: string | null
  youtube_statistics_updated_at?: string | null
  youtube_statistics_source?: string | null
  intro: string
}
export interface Performance {
  id: number
  song_title: string
  song_title_ko?: string
  original_artist: string
  original_artist_ko?: string
  start_seconds: number
}
export interface Live {
  is_sample?: boolean
  id: number
  artist_id: number | null
  title: string
  title_ko: string
  video_id: string
  broadcast_at: string
  duration_seconds: number
  performance_count?: number | null
  performances: Performance[]
  source_url: string
  metadata_note?: string
}
export interface SearchPerformance extends Performance {
  live: Live
  artist: Pick<Artist, 'name' | 'display_name'> & { id: number | null }
}
export interface SearchResults {
  total?: number
  limited?: boolean
  artists: Artist[]
  performances: SearchPerformance[]
}
export interface Page<T> {
  items: T[]
  total: number
  offset: number
  limit: number
}
export type SongKind = 'utawaku' | 'cover' | 'original'
export interface ExploredSong {
  key: string
  title: string
  title_ko: string | null
  artist_name: string
  youtube_video_id: string | null
  view_count: number | null
  views_updated_at: string | null
  performance_count: number | null
  artist_count: number | null
  archive_id: number | null
  start_seconds: number | null
  published_at: string | null
}
export interface Statistics extends ReturnType<
  typeof import('@/lib/artist-statistics').artistStatistics
> {
  activity: { month: string; count: number }[]
}
export interface Track {
  youtube_url?: string
  lyrics_id?: number
  id: number | string
  song_id?: number
  title: string
  title_ko: string
  duration: string
  duration_ms?: number
  disc_number?: number
  track_number?: number
  has_lyrics: boolean
  // Track performers; empty means no known performer.
  artists?: { id?: number; name: string; name_ko: string }[]
}
export interface Album {
  id: string
  artist_id: number
  name: string
  album_type: 'album' | 'single' | 'ep' | 'compilation' | 'other'
  release_date: string
  image_url: string
  total_tracks?: number
  // Artist listings only: false when the artist is credited on tracks only (appears on).
  is_primary?: boolean
  tracks_loaded?: boolean
  tracks: Track[]
  source_url: string
  is_sample: boolean
}
export interface Lyrics {
  recording_id?: number
  needs_review?: boolean
  lyrics_source_url?: string | null
  lyrics_source_type?: string
  song_id: number | null
  original_title: string
  artist_name: string
  original_lyrics: string
  translation_ko: string
  pronunciation_ko: string
  is_sample: boolean
}
export interface Concert {
  artist_ids?: number[]
  ticket_url?: string
  id: number
  artist_id: number
  title: string
  starts_at: string
  venue: string
  city: string
  price_text: string
  source_url: string
  is_sample: boolean
  event_format: 'onsite' | 'hybrid' | 'online'
}
export interface CalendarEvent {
  id: string
  artist_id: number
  title: string
  date: string
  kind: 'concert' | 'birthday'
  concert?: Concert
  person?: string
}
export interface Cover {
  id: number
  youtube_video_id: string
  youtube_url: string
  title: string
  published_at: string | null
  duration_seconds: number | null
}
