import { createApp } from 'vue'
import App from './App.vue'
import './style.css'
import { isMock } from './api/config'
import { router } from './app/router'

async function start() {
  if (isMock) {
    const { worker } = await import('./mocks/browser')
    await worker.start({
      quiet: true,
      onUnhandledRequest(request, print) {
        if (new URL(request.url).pathname.startsWith('/api/')) print.error()
      },
    })
  } else if ('serviceWorker' in navigator) {
    const registrations = await navigator.serviceWorker.getRegistrations()
    const isMockWorker = (worker: ServiceWorker | null) =>
      worker &&
      new URL(worker.scriptURL).origin === location.origin &&
      new URL(worker.scriptURL).pathname.endsWith('/mockServiceWorker.js')
    const stale = registrations.filter(
      (r) => isMockWorker(r.active) || isMockWorker(r.waiting) || isMockWorker(r.installing),
    )
    await Promise.all(stale.map((r) => r.unregister()))
    if (stale.length && isMockWorker(navigator.serviceWorker.controller)) {
      location.reload()
      return
    }
  }
  const app = createApp(App).use(router)
  await router.isReady()
  app.mount('#app')
}
start().catch(() => {
  const element = document.querySelector('#app')!
  element.textContent = isMock
    ? '프리뷰를 시작하지 못했어요. 브라우저에서 Service Worker를 허용하고 새로고침해 주세요.'
    : '앱을 시작하지 못했어요. 새로고침해 주세요.'
})
