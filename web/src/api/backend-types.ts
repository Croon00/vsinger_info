// Read contracts verified against app/api/routers and their response builders.
export interface BackendArtist {
  id: number
  name: string
  display_name?: string | null
  name_latin?: string | null
  birthday?: string | null
  theme_color?: string | null
  agency?: string | null
  profile_intro?: string | null
  spotify_image_url?: string | null
  avatar_variants?: Record<string, string>
  related_artist_ids?: number[]
  name_aliases?: string[]
  sources?: { source_type: string; value: string; label?: string | null; is_active: boolean }[]
}
export interface BackendPerformance {
  id: number
  song_title: string
  song_title_ko?: string | null
  original_artist?: string | null
  original_artist_ko?: string | null
  start_seconds: number
}
export interface BackendLive {
  artist_id?: number | null
  id: number
  artist_name: string
  youtube_url: string
  youtube_video_id?: string | null
  video_title?: string | null
  broadcast_at?: string | null
  published_at?: string | null
  duration_seconds?: number | null
  performance_count?: number | null
  performances?: BackendPerformance[]
}
export interface BackendSearchPerformance extends BackendPerformance {
  artist_id?: number | null
  archive_id: number
  performed_on?: string | null
  broadcast_at?: string | null
  artist_name_ko?: string | null
  youtube_url: string
  video_title?: string | null
  artist_name: string
}
export interface BackendAlbum {
  id: string
  name: string
  album_type: string
  release_date?: string | null
  release_date_precision?: string | null
  total_tracks: number
  image_url?: string | null
  spotify_url?: string | null
  tracks?: {
    id: string
    recording_id: number
    song_id?: number | null
    has_lyrics: boolean
    name: string
    name_ko?: string | null
    duration_ms?: number | null
    track_number: number
    disc_number: number
  }[]
}
export interface BackendLyricsSummary {
  song_id: number
  spotify_track_id: string
  has_lyrics: boolean
}
export interface BackendLyrics {
  recording_id: number
  song_id: number | null
  original_title: string
  artist_name: string
  original_lyrics: string
  translation_ko: string
  pronunciation_ko: string
  needs_review: boolean
  lyrics_source_type: string
  lyrics_source_url?: string | null
}
export interface BackendEvent {
  id: number
  artist_id?: number | null
  title: string
  starts_at?: string | null
  city?: string | null
  artist_ids?: number[]
  venue?: string | null
  price_text?: string | null
  source_url?: string | null
  ticket_url?: string | null
  status: string
  event_type: string
  event_format: string
}
