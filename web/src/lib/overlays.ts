import type { Router, RouteLocationNormalizedLoaded } from 'vue-router'
export type OverlayType = 'event' | 'lyrics' | 'album'
/**
 * Open a query-backed overlay. Opening lyrics keeps an open album in the query, so
 * closing the lyrics (Back) returns to that album.
 */
export function openOverlay(
  router: Router,
  route: RouteLocationNormalizedLoaded,
  type: OverlayType,
  id: number | string,
) {
  return router.push({
    path: route.path,
    query: { ...route.query, event: undefined, lyrics: undefined, [type]: String(id) },
    state: { draftOverlay: true },
  })
}
