export type SourceType = 'x' | 'official_site' | 'ticket_site' | 'rss' | 'other'
export type ArtistKind = 'vtuber' | 'singer'

export interface ArtistAgency {
  id: number
  name: string
  created_at: string
}

export type LyricsSourceMode = 'caption' | 'description' | 'comment' | 'audio'

export interface WebSongCreated {
  id: number
  artist_name: string
  title: string
  lyrics_source_type: string
  needs_review: boolean
  spotify_track_id: string | null
}

export interface SongLyricsSummary {
  song_id: number
  spotify_track_id: string
  youtube_url: string
  has_lyrics: boolean
  lyricist: string | null
  composer: string | null
  arranger: string | null
}

export interface SongCreditsUpdate {
  lyricist: string | null
  composer: string | null
  arranger: string | null
}

export interface SpotifyTrackYouTubeLinkCreate {
  spotify_track_id: string
  title: string
  artist_name: string
  album_name?: string | null
  youtube_url: string
}

export interface SongLyricsDetail {
  song_id: number
  original_title: string
  title_ko: string | null
  artist_name: string
  album_name: string | null
  youtube_url: string
  original_lyrics: string
  translation_ko: string
  pronunciation_ko: string
  lyrics_source_type: string
  lyrics_source_url: string | null
  needs_review: boolean
}
export type CandidateStatus = 'needs_review' | 'ready' | 'synced' | 'ignored'
export type EventType = 'live_event' | 'ticket'
export type EventFormat = 'onsite' | 'hybrid' | 'online' | 'unknown'

export interface Source {
  id: number
  artist_id: number
  source_type: SourceType
  label: string | null
  value: string
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface Artist {
  related_artist_ids?: number[]
  name_aliases?: string[]
  id: number
  name: string
  display_name: string | null
  artist_kind: ArtistKind
  agency: string | null
  show_in_spotify: boolean
  show_in_lyrics: boolean
  show_in_youtube_lives: boolean
  notes: string | null
  profile_intro: string | null
  debut_date: string | null
  spotify_image_url: string | null
  representative_youtube_url: string | null
  created_at: string
  updated_at: string
  sources: Source[]
}

export interface ArtistCreate {
  name: string
  display_name?: string
  artist_kind?: ArtistKind
  agency?: string
  show_in_spotify?: boolean
  show_in_lyrics?: boolean
  show_in_youtube_lives?: boolean
  notes?: string
  profile_intro?: string
  debut_date?: string
  x_username?: string
}

export interface SourceCreate {
  source_type: SourceType
  label?: string
  value: string
  is_active: boolean
}

export interface EventCandidate {
  id: number
  artist_id: number | null
  source_id: number | null
  event_type: EventType
  event_format: EventFormat
  title: string
  starts_at: string | null
  venue: string | null
  ticket_opens_at: string | null
  ticket_closes_at: string | null
  ticket_url: string | null
  price_text: string | null
  capacity_text: string | null
  setlist_json: string | null
  merchandise_json: string | null
  source_url: string | null
  raw_text: string | null
  status: CandidateStatus
  created_at: string
  updated_at: string
}

export type EventCandidateCreate = Omit<EventCandidate, 'id' | 'created_at' | 'updated_at'>

export interface SpotifyArtist {
  related_artist_ids?: number[]
  local_artist_id: number
  local_name: string
  artist_kind: ArtistKind
  agency: string | null
  spotify_artist_id: string | null
  spotify_name: string | null
  image_url: string | null
  spotify_url: string | null
  matched: boolean
  youtube_auto_linked?: number
  youtube_auto_unmatched?: number
  youtube_auto_link_enabled?: boolean
}

export interface SpotifyArtistCandidate {
  local_artist_id: number
  spotify_artist_id: string
  name: string
  image_url: string | null
  spotify_url: string | null
  genres: string[]
}

export interface SpotifyArtistProfile extends SpotifyArtistCandidate {}

export interface SpotifyAlbum {
  id: string
  name: string
  album_type: string
  release_date: string | null
  release_date_precision: string | null
  total_tracks: number
  image_url: string | null
  spotify_url: string | null
  artists: string[]
  artist_ids: string[]
}

export interface SpotifyTrack {
  id: string
  name: string
  name_ko: string | null
  track_number: number
  disc_number: number
  duration_ms: number | null
  explicit: boolean
  spotify_url: string | null
  artists: string[]
  artist_ids: string[]
}

export interface SpotifyAlbumDetail extends SpotifyAlbum {
  tracks: SpotifyTrack[]
}

export interface SpotifyRelationship {
  source_artist_id: number
  target_artist_id: number
  strength: number
  shared_releases: string[]
}

export interface YouTubePerformance {
  id: number; performed_on: string; start_seconds: number; timestamp_text: string; song_title: string
  song_title_ko: string | null; original_artist: string | null; original_artist_ko: string | null
  tj_number: string; ky_number: string
}

export interface YouTubePerformanceSearchResult extends YouTubePerformance {
  archive_id: number
  artist_name: string
  youtube_url: string
  video_title: string | null
}

export interface YouTubePerformanceFilters {
  performers: string[]
  original_artists: string[]
  songs: string[]
}

export interface YouTubeLiveArchive {
  id: number; youtube_url: string; video_title: string | null; artist_name: string
  status: 'pending' | 'ready'; published_at: string | null; broadcast_at: string | null
  setlist: Array<{ timestamp: string; title: string }>; performances?: YouTubePerformance[]
  last_checked_at: string | null
}

export interface YouTubeCoverVideo {
  id: number
  artist_id: number
  artist_name: string
  youtube_video_id: string
  youtube_url: string
  video_title: string
  video_description: string | null
  published_at: string | null
  collaborators: Array<{ id: number; name: string }>
}
