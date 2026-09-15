import { createApp } from 'vue'
import App from './App.vue'
import './style.css'
import { router } from './app/router'

async function start() {
  const { worker } = await import('./mocks/browser')
  await worker.start({
    quiet: true,
    onUnhandledRequest(request, print) {
      if (new URL(request.url).pathname.startsWith('/api/')) print.error()
    },
  })
  const app = createApp(App).use(router)
  await router.isReady()
  app.mount('#app')
}
start().catch(() => {
  const element = document.querySelector('#app')!
  element.textContent =
    '프리뷰를 시작하지 못했어요. 브라우저에서 Service Worker를 허용하고 새로고침해 주세요.'
})
