import { spawn, type ChildProcess } from 'node:child_process'
import { mkdtemp, mkdir, rm, writeFile } from 'node:fs/promises'
import { createServer, request, type Server } from 'node:http'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { gzipSync } from 'node:zlib'
import { expect, test } from 'vitest'

async function listen(server: Server): Promise<number> {
  server.listen(0, '127.0.0.1')
  await new Promise<void>((resolve, reject) => {
    server.once('listening', resolve)
    server.once('error', reject)
  })
  const address = server.address()
  if (!address || typeof address === 'string') throw new Error('No local port')
  return address.port
}

function rawGet(port: number, path: string): Promise<{ status: number; body: string }> {
  return new Promise((resolve, reject) => {
    const call = request({ hostname: '127.0.0.1', port, path }, (response) => {
      const chunks: Buffer[] = []
      response.on('data', (chunk: Buffer) => chunks.push(chunk))
      response.on('end', () => resolve({ status: response.statusCode ?? 0, body: Buffer.concat(chunks).toString() }))
      response.on('error', reject)
    })
    call.on('error', reject)
    call.end()
  })
}

test('production proxy pins its backend, serves decoded data, and survives malformed URLs', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'schedule-web-server-'))
  await mkdir(join(dir, 'dist'))
  await writeFile(join(dir, 'dist', 'index.html'), '<html>fixture</html>')
  const payload = JSON.stringify({ items: ['stored result'] })
  const compressed = gzipSync(payload)
  let backendCalls = 0
  let foreignCalls = 0
  const backend = createServer((_request, response) => {
    backendCalls++
    response.writeHead(200, {
      'Content-Type': 'application/json',
      'Content-Encoding': 'gzip',
      'Content-Length': compressed.length,
    })
    response.end(compressed)
  })
  const foreign = createServer((_request, response) => {
    foreignCalls++
    response.end('unexpected destination')
  })
  let child: ChildProcess | undefined
  try {
    const backendPort = await listen(backend)
    const foreignPort = await listen(foreign)
    const reservation = createServer()
    const webPort = await listen(reservation)
    await new Promise<void>((resolve) => reservation.close(() => resolve()))
    child = spawn(process.execPath, [fileURLToPath(new URL('../../server.mjs', import.meta.url))], {
      cwd: dir,
      env: { ...process.env, PORT: String(webPort), BACKEND_URL: `http://127.0.0.1:${backendPort}`, BACKEND_API_KEY: 'fixture-key' },
      windowsHide: true,
      stdio: ['ignore', 'pipe', 'pipe'],
    })
    await Promise.race([
      new Promise<void>((resolve, reject) => {
        child?.stdout?.once('data', () => resolve())
        child?.once('error', reject)
        child?.once('exit', () => reject(new Error('Web server exited during startup')))
      }),
      new Promise<never>((_, reject) => setTimeout(() => reject(new Error('Web server startup timeout')), 5000)),
    ])

    const normal = await rawGet(webPort, '/api/artists?q=fixture')
    expect(normal).toEqual({ status: 200, body: payload })
    const absolute = await rawGet(webPort, `http://127.0.0.1:${foreignPort}/api/artists`)
    expect(absolute).toEqual({ status: 200, body: payload })
    expect(backendCalls).toBe(2)
    expect(foreignCalls).toBe(0)
    expect(await rawGet(webPort, '/%')).toMatchObject({ status: 400 })
    expect(await rawGet(webPort, '/')).toEqual({ status: 200, body: '<html>fixture</html>' })
  } finally {
    child?.kill()
    backend.closeAllConnections()
    foreign.closeAllConnections()
    if (backend.listening) await new Promise<void>((resolve) => backend.close(() => resolve()))
    if (foreign.listening) await new Promise<void>((resolve) => foreign.close(() => resolve()))
    await rm(dir, { recursive: true, force: true })
  }
}, 15000)
