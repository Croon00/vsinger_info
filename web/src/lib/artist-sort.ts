import type { Artist } from '@/api/types'

export type ArtistSort = '' | 'channel-created' | 'subscribers' | 'name'
const koreanNames = new Intl.Collator('ko', { sensitivity: 'base', numeric: true })
const defaultNames = new Intl.Collator('en', { sensitivity: 'base', numeric: true })
export function sortArtists(artists: Artist[], order: ArtistSort, favorites = new Set<number>()) {
  return [...artists].sort((a, b) => {
    const name = () =>
      koreanNames.compare(a.display_name || a.name, b.display_name || b.name) || a.id - b.id
    if (order === 'name') return name()
    if (order === 'channel-created') {
      const first = a.youtube_channel_created_at || null
      const second = b.youtube_channel_created_at || null
      return (
        Number(first === null) - Number(second === null) ||
        (first && second ? first.localeCompare(second) : 0) ||
        name()
      )
    }
    if (order === 'subscribers') {
      const first = a.youtube_subscriber_count ?? null
      const second = b.youtube_subscriber_count ?? null
      return (
        Number(first === null) - Number(second === null) ||
        (first !== null && second !== null ? second - first : 0) ||
        name()
      )
    }
    return (
      Number(favorites.has(b.id)) - Number(favorites.has(a.id)) ||
      defaultNames.compare(a.roman || a.name, b.roman || b.name) ||
      a.id - b.id
    )
  })
}
