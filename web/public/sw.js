// Only the offline notice is stored. API responses, media and app bundles stay online.
const CACHE = 'utamowa-offline-v1'
const OFFLINE = '/offline.html'
self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.add(OFFLINE)))
})
self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    for (const key of await caches.keys()) {
      if (key.startsWith('utamowa-offline-') && key !== CACHE) await caches.delete(key)
    }
    await self.clients.claim()
  })())
})
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url)
  if (event.request.method !== 'GET' || url.origin !== self.location.origin ||
      url.pathname === '/api' || url.pathname.startsWith('/api/') ||
      event.request.mode !== 'navigate') return
  event.respondWith(fetch(event.request).catch(async () =>
    (await caches.match(OFFLINE)) || Response.error(),
  ))
})
