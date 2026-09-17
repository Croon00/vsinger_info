export interface Link {
  label: string
  url: string
}
export interface Artist {
  id: number
  name: string
  display_name: string
  roman: string
  agency: string
  image: string
  image_source: string
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
  artist_id: number
  title: string
  title_ko: string
  video_id: string
  broadcast_at: string
  duration_seconds: number
  performances: Performance[]
  source_url: string
  metadata_note?: string
}
export interface SearchPerformance extends Performance {
  live: Live
  artist: Artist
}
export interface SearchResults {
  artists: Artist[]
  performances: SearchPerformance[]
}
export interface Track {
  id: number
  title: string
  title_ko: string
  duration: string
  has_lyrics: boolean
}
export interface Album {
  id: string
  artist_id: number
  name: string
  album_type: 'album' | 'single'
  release_date: string
  image_url: string
  tracks: Track[]
  source_url: string
  is_sample: boolean
}
export interface Lyrics {
  song_id: number
  original_title: string
  artist_name: string
  original_lyrics: string
  translation_ko: string
  pronunciation_ko: string
  is_sample: boolean
}
export interface Concert {
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
