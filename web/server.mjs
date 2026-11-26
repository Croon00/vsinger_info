import { createReadStream, existsSync } from 'node:fs'
import { stat } from 'node:fs/promises'
import { createServer } from 'node:http'
import { extname, normalize, resolve, sep } from 'node:path'

const port = Number(process.env.PORT || 3000)
const backendUrl = process.env.BACKEND_URL
const apiKey = process.env.BACKEND_API_KEY
const distDir = resolve('dist')
const lyricsWritePath = /^\/api\/recordings\/[1-9]\d*\/lyrics$/

class BodyTooLarge extends Error {}

async function readBody(request, maxBodyBytes) {
  const chunks = []
  let size = 0
  for await (const chunk of request) {
    size += chunk.length
    if (size > maxBodyBytes) throw new BodyTooLarge()
    chunks.push(chunk)
  }
  return Buffer.concat(chunks)
}

const mimeTypes = {
  '.css': 'text/css; charset=utf-8',
  '.html': 'text/html; charset=utf-8',
  '.ico': 'image/x-icon',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.webmanifest': 'application/manifest+json; charset=utf-8',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.map': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.webp': 'image/webp',
  '.woff2': 'font/woff2',
}

function serveFile(response, filePath) {
  response.writeHead(200, {
    'Content-Type': mimeTypes[extname(filePath)] || 'application/octet-stream',
    'Cache-Control': filePath.startsWith(resolve(distDir, 'assets') + sep)
      ? 'public, max-age=31536000, immutable' : 'no-cache',
  })
  createReadStream(filePath).pipe(response)
}

async function proxyApi(request, response, path, write = false, lyricsEdit = false) {
  if (!backendUrl) {
    response.writeHead(503, { 'Content-Type': 'application/json; charset=utf-8' })
    response.end(JSON.stringify({ detail: 'BACKEND_URL is not configured for the frontend service.' }))
    return
  }

  // Only the path and query may come from the browser. The configured backend
  // remains the destination even for absolute-form HTTP request targets.
  const target = new URL(path, backendUrl)
  const headers = { accept: request.headers.accept || 'application/json' }
  if (apiKey) headers['X-API-Key'] = apiKey
  let requestBody
  if (write) {
    try {
      requestBody = await readBody(request, (lyricsEdit ? 160 : 64) * 1024)
    } catch (error) {
      if (!(error instanceof BodyTooLarge)) throw error
      response.writeHead(413, { 'Content-Type': 'application/json; charset=utf-8' })
      response.end(JSON.stringify({ detail: 'Request body is too large.' }))
      return
    }
    headers['content-type'] = 'application/json'
    if (lyricsEdit && request.headers['x-lyrics-editor-key'])
      headers['x-lyrics-editor-key'] = request.headers['x-lyrics-editor-key']
    // The backend rate-limits by client address; it does not store it.
    const forwarded = request.headers['x-forwarded-for']
    const address = request.socket.remoteAddress || ''
    headers['x-forwarded-for'] = forwarded ? `${forwarded}, ${address}` : address
  }

  try {
    const upstream = await fetch(target, {
      method: request.method, headers, body: requestBody, ...(lyricsEdit ? { redirect: 'error' } : {}),
    })
    const body = Buffer.from(await upstream.arrayBuffer())
    const upstreamHeaders = {}
    for (const [name, value] of upstream.headers) {
      if (!['connection', 'keep-alive', 'transfer-encoding', 'content-encoding', 'content-length'].includes(name.toLowerCase())
          && !(upstream.headers.has('content-encoding') && name.toLowerCase() === 'etag')) {
        upstreamHeaders[name] = value
      }
    }
    response.writeHead(upstream.status, upstreamHeaders)
    response.end(body)
  } catch {
    if (response.headersSent) response.destroy()
    else {
      response.writeHead(502, { 'Content-Type': 'application/json; charset=utf-8' })
      response.end(JSON.stringify({ detail: 'The frontend could not reach the backend service.' }))
    }
  }
}

const server = createServer(async (request, response) => {
  try {
    const method = request.method || 'GET'
    const parsed = new URL(request.url || '/', 'http://localhost')
    const pathname = parsed.pathname

    if (pathname.startsWith('/api/')) {
      const lyricsEdit = method === 'PUT' && lyricsWritePath.test(pathname)
      if (lyricsEdit || (method === 'POST' && pathname === '/api/worldcup/results')) {
        await proxyApi(request, response, pathname + parsed.search, true, lyricsEdit)
        return
      }
      if (!['GET', 'HEAD'].includes(method)) {
        response.writeHead(405, { Allow: 'GET, HEAD', 'Content-Type': 'application/json; charset=utf-8' })
        response.end(JSON.stringify({ detail: 'Read-only frontend proxy' }))
        return
      }
      await proxyApi(request, response, pathname + parsed.search)
      return
    }

    const relativePath = normalize(decodeURIComponent(pathname)).replace(/^[\\/]+/, '')
    const candidate = resolve(distDir, relativePath || 'index.html')
    if ((candidate === distDir || candidate.startsWith(distDir + sep))
        && existsSync(candidate) && (await stat(candidate)).isFile()) {
      serveFile(response, candidate)
      return
    }
    serveFile(response, resolve(distDir, 'index.html'))
  } catch (error) {
    if (response.headersSent) response.destroy()
    else {
      response.writeHead(error instanceof URIError || error instanceof TypeError ? 400 : 500,
        { 'Content-Type': 'application/json; charset=utf-8' })
      response.end(JSON.stringify({ detail: 'Unable to handle request.' }))
    }
  }
})

server.listen(port, '0.0.0.0', () => {
  console.log(`Frontend listening on port ${port}`)
})
