export interface Link {
  label: string
  url: string
}
export interface Artist {
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
export interface Statistics extends ReturnType<
  typeof import('@/lib/artist-statistics').artistStatistics
> {
  activity: { month: string; count: number }[]
}
export interface Track {
  lyrics_id?: number
  id: number | string
  song_id?: number
  title: string
  title_ko: string
  duration: string
  has_lyrics: boolean
}
export interface Album {
  id: string
  artist_id: number
  name: string
  album_type: 'album' | 'single' | 'ep' | 'compilation' | 'other'
  release_date: string
  image_url: string
  total_tracks?: number
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
