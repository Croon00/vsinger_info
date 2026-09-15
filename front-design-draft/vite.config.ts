import { fileURLToPath, URL } from 'node:url'
import { defineConfig, type Plugin } from 'vite'
import type { IncomingMessage, ServerResponse } from 'node:http'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'

// YouTube rejects numeric loopback referrers in local embeds. Redirect the
// document itself so the browser sends the real localhost origin, without
// spoofing YouTube headers or proxying video traffic.
function redirectLoopback(req: IncomingMessage, res: ServerResponse, next: () => void) {
  const host = req.headers.host ?? ''
  if (
    req.method === 'GET' &&
    /^127\.0\.0\.1(?::\d+)?$/.test(host) &&
    req.headers.accept?.includes('text/html')
  ) {
    const destination = new URL(req.url ?? '/', `http://${host}`)
    destination.hostname = 'localhost'
    res.writeHead(307, { Location: destination.href, 'Cache-Control': 'no-store' })
    res.end()
    return
  }
  next()
}
const localPlayerOrigin: Plugin = {
  name: 'local-player-origin',
  configureServer(server) {
    server.middlewares.use(redirectLoopback)
  },
  configurePreviewServer(server) {
    server.middlewares.use(redirectLoopback)
  },
}

export default defineConfig({
  plugins: [localPlayerOrigin, vue(), tailwindcss()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
})
