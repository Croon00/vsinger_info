import type { Artist, Live, SearchResults } from '@/api/types'
import { normalize } from '@/lib/search'
export function searchCatalog(query: string, artists: Artist[], lives: Live[]): SearchResults {
  const q = normalize(query.trim())
  if (!q) return { artists: [], performances: [] }
  const matches = (...values: (string | undefined)[]) =>
    values.some((v) => v && normalize(v).includes(q))
  return {
    artists: artists.filter((a) => matches(a.name, a.display_name, a.roman)),
    performances: lives.flatMap((live) => {
      const artist = artists.find((a) => a.id === live.artist_id)
      if (!artist) return []
      return live.performances
        .filter((p) =>
          matches(
            p.song_title,
            p.song_title_ko,
            p.original_artist,
            p.original_artist_ko,
            artist.name,
            artist.display_name,
            artist.roman,
          ),
        )
        .map((p) => ({ ...p, live, artist }))
    }),
  }
}
