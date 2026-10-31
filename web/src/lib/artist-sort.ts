import type { Artist } from '@/api/types'

export type ArtistSort =
  'channel-created' | 'channel-recent' | 'subscribers' | 'subscribers-low' | 'name'
const koreanNames = new Intl.Collator('ko', { sensitivity: 'base', numeric: true })
export function sortArtists(artists: Artist[], order: ArtistSort = 'name') {
  return [...artists].sort((a, b) => {
    const name = () =>
      koreanNames.compare(a.display_name || a.name, b.display_name || b.name) || a.id - b.id
    if (order === 'name') return name()
    if (order === 'channel-created' || order === 'channel-recent') {
      const first = a.youtube_channel_created_at ? Date.parse(a.youtube_channel_created_at) : NaN
      const second = b.youtube_channel_created_at ? Date.parse(b.youtube_channel_created_at) : NaN
      return (
        Number(!Number.isFinite(first)) - Number(!Number.isFinite(second)) ||
        (Number.isFinite(first) && Number.isFinite(second)
          ? (first - second) * (order === 'channel-recent' ? -1 : 1)
          : 0) ||
        name()
      )
    }
    if (order === 'subscribers' || order === 'subscribers-low') {
      const first = a.youtube_subscriber_count ?? null
      const second = b.youtube_subscriber_count ?? null
      return (
        Number(first === null) - Number(second === null) ||
        (first !== null && second !== null
          ? (second - first) * (order === 'subscribers-low' ? -1 : 1)
          : 0) ||
        name()
      )
    }
    return name()
  })
}
