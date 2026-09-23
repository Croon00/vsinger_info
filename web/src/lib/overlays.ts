import type { Router, RouteLocationNormalizedLoaded } from 'vue-router'
export function openOverlay(
  router: Router,
  route: RouteLocationNormalizedLoaded,
  type: 'event' | 'lyrics',
  id: number,
) {
  return router.push({
    path: route.path,
    query: { ...route.query, event: undefined, lyrics: undefined, [type]: String(id) },
    state: { draftOverlay: true },
  })
}
