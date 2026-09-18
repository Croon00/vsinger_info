import { http, HttpResponse, delay } from 'msw'
import { artists, lives, albums, concerts, lyricsFor } from './fixtures'
import { searchCatalog } from './search'

function scenario() {
  return typeof window !== 'undefined'
    ? new URLSearchParams(window.location.search).get('scenario')
    : null
}
async function respond(value: unknown, empty?: unknown) {
  const mode = scenario()
  await delay(mode === 'slow' ? 1800 : 220)
  if (mode === 'error') return HttpResponse.json({ detail: 'Simulated error' }, { status: 503 })
  if (value === undefined) return HttpResponse.json({ detail: 'Not found' }, { status: 404 })
  const payload = mode === 'empty' ? (empty ?? (Array.isArray(value) ? [] : value)) : value
  return new HttpResponse(JSON.stringify(payload), {
    headers: { 'Content-Type': 'application/json' },
  })
}
export const handlers = [
  http.get('/api/draft/artists', () =>
    respond(
      scenario() === 'broken-images'
        ? artists.map((a) => ({ ...a, image: `/images/unavailable-${a.id}.png` }))
        : artists,
    ),
  ),
  http.get('/api/draft/artists/:id', ({ params }) =>
    respond(
      artists.find((a) => String(a.id) === params.id),
      undefined,
    ),
  ),
  http.get('/api/draft/lives', ({ request }) => {
    const id = new URL(request.url).searchParams.get('artist_id')
    return respond(
      lives
        .filter((l) => !id || l.artist_id === Number(id))
        .sort((a, b) => b.broadcast_at.localeCompare(a.broadcast_at)),
    )
  }),
  http.get('/api/draft/lives/:id', ({ params }) =>
    respond(
      lives.find((l) => String(l.id) === params.id),
      undefined,
    ),
  ),
  http.get('/api/draft/albums', ({ request }) =>
    respond(
      albums.filter(
        (a) => a.artist_id === Number(new URL(request.url).searchParams.get('artist_id')),
      ),
    ),
  ),
  http.get('/api/draft/concerts', () => respond(concerts)),
  http.get('/api/songs/:id/lyrics', ({ params }) =>
    respond(lyricsFor(Number(params.id)), undefined),
  ),
  http.get('/api/draft/search', ({ request }) =>
    respond(searchCatalog(new URL(request.url).searchParams.get('q') ?? '', artists, lives), {
      artists: [],
      performances: [],
    }),
  ),
  // Compatibility examples preserve the backend's existing artist/event fields.
  http.get('/api/artists', () =>
    respond(
      artists.map((a) => ({
        id: a.id,
        name: a.name,
        display_name: a.display_name,
        artist_kind: 'vsinger',
        agency: a.agency,
        profile_intro: a.intro,
        spotify_image_url: a.image,
        notes: null,
        debut_date: null,
        created_at: '2026-09-15T00:00:00Z',
        updated_at: '2026-09-15T00:00:00Z',
        sources: a.links.map((l, i) => ({
          id: a.id * 10 + i,
          artist_id: a.id,
          source_type: 'website',
          label: l.label,
          value: l.url,
          is_active: true,
        })),
      })),
    ),
  ),
  http.get('/api/event-candidates', () =>
    respond(concerts.map((c) => ({ ...c, event_type: 'live_event', status: 'ready' }))),
  ),
  http.all('/api/*', () =>
    HttpResponse.json(
      { detail: 'This design draft has no handler for this API.' },
      { status: 501 },
    ),
  ),
]
