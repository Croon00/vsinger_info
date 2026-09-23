import { createReadStream, existsSync } from 'node:fs'
import { stat } from 'node:fs/promises'
import { createServer } from 'node:http'
import { extname, normalize, resolve } from 'node:path'

const port = Number(process.env.PORT || 3000)
const backendUrl = process.env.BACKEND_URL
const apiKey = process.env.BACKEND_API_KEY
const distDir = resolve('dist')

const mimeTypes = {
  '.css': 'text/css; charset=utf-8',
  '.html': 'text/html; charset=utf-8',
  '.ico': 'image/x-icon',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.map': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.webp': 'image/webp',
  '.woff2': 'font/woff2',
}

function serveFile(response, filePath) {
  response.writeHead(200, {
    'Content-Type': mimeTypes[extname(filePath)] || 'application/octet-stream',
    'Cache-Control': filePath.endsWith('index.html') ? 'no-cache' : 'public, max-age=31536000, immutable',
  })
  createReadStream(filePath).pipe(response)
}

async function proxyApi(request, response) {
  if (!backendUrl) {
    response.writeHead(503, { 'Content-Type': 'application/json; charset=utf-8' })
    response.end(JSON.stringify({ detail: 'BACKEND_URL is not configured for the frontend service.' }))
    return
  }

  const target = new URL(request.url || '/', backendUrl)
  const headers = { accept: request.headers.accept || 'application/json' }
  if (apiKey) headers['X-API-Key'] = apiKey

  try {
    const upstream = await fetch(target, { method: request.method, headers })
    const upstreamHeaders = {}
    for (const [name, value] of upstream.headers) {
      if (!['connection', 'keep-alive', 'transfer-encoding'].includes(name.toLowerCase())) {
        upstreamHeaders[name] = value
      }
    }
    response.writeHead(upstream.status, upstreamHeaders)
    response.end(Buffer.from(await upstream.arrayBuffer()))
  } catch {
    response.writeHead(502, { 'Content-Type': 'application/json; charset=utf-8' })
    response.end(JSON.stringify({ detail: 'The frontend could not reach the backend service.' }))
  }
}

const server = createServer(async (request, response) => {
  const method = request.method || 'GET'
  const pathname = new URL(request.url || '/', 'http://localhost').pathname

  if (pathname.startsWith('/api/')) {
    if (!['GET', 'HEAD'].includes(method)) {
      response.writeHead(405, { Allow: 'GET, HEAD', 'Content-Type': 'application/json; charset=utf-8' })
      response.end(JSON.stringify({ detail: 'Read-only frontend proxy' }))
      return
    }
    await proxyApi(request, response)
    return
  }

  const relativePath = normalize(decodeURIComponent(pathname)).replace(/^[\\/]+/, '')
  const candidate = resolve(distDir, relativePath || 'index.html')
  if (candidate.startsWith(distDir) && existsSync(candidate) && (await stat(candidate)).isFile()) {
    serveFile(response, candidate)
    return
  }
  serveFile(response, resolve(distDir, 'index.html'))
})

server.listen(port, '0.0.0.0', () => {
  console.log(`Frontend listening on port ${port}`)
})
