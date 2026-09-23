// Share in-flight reads without allowing one component's abort to cancel others.
// Successful results expire quickly; errors are never cached. Every underlying
// request has a timeout, including when all subscribers navigate away.
import { request } from './http'
const entries = new Map<string, { expires: number; promise: Promise<unknown> }>()
export function cachedRead<T>(path: string, signal?: AbortSignal, ttl = 30_000): Promise<T> {
  if (signal?.aborted) return Promise.reject(new DOMException('Aborted', 'AbortError'))
  let entry = entries.get(path)
  if (!entry || entry.expires < Date.now()) {
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), 60_000)
    entry = { expires: Infinity, promise: Promise.resolve() }
    const created = entry
    entry.promise = request<T>(path, controller.signal)
      .then((value) => {
        created.expires = Date.now() + ttl
        return value
      })
      .catch((error) => {
        if (entries.get(path) === created) entries.delete(path)
        throw error
      })
      .finally(() => clearTimeout(timeout))
    entries.set(path, entry)
    if (entries.size > 128) entries.delete(entries.keys().next().value!)
  }
  return new Promise<T>((resolve, reject) => {
    const abort = () => reject(new DOMException('Aborted', 'AbortError'))
    signal?.addEventListener('abort', abort, { once: true })
    entry!.promise
      .then((value) => {
        if (!signal?.aborted) resolve(value as T)
      }, reject)
      .finally(() => signal?.removeEventListener('abort', abort))
  })
}
