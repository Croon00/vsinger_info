import { fileURLToPath, URL } from 'node:url'
import { defineConfig, loadEnv, type Plugin } from 'vite'
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

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const target = env.BACKEND_URL || 'http://127.0.0.1:8000'
  const apiKey = env.BACKEND_API_KEY
  const readOnlyApi: Plugin = {
    name: 'read-only-backend-proxy',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        if (req.url?.startsWith('/api/') && !['GET', 'HEAD'].includes(req.method ?? '')) {
          res.writeHead(405, { 'Content-Type': 'application/json' })
          res.end('{"detail":"Read-only frontend proxy"}')
          return
        }
        next()
      })
    },
  }
  return {
    define: {
      'import.meta.env.VITE_DATA_MODE': JSON.stringify(
        mode === 'mock' ? 'mock' : mode === 'integration' ? 'real' : env.VITE_DATA_MODE || 'real',
      ),
    },
    server: {
      proxy: {
        '/api': {
          target,
          changeOrigin: true,
          ...(apiKey ? { headers: { 'X-API-Key': apiKey } } : {}),
        },
      },
    },
    plugins: [localPlayerOrigin, readOnlyApi, vue(), tailwindcss()],
    resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  }
})
