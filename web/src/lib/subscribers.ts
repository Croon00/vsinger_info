/** Compact Korean counts, using only the published count without rounding up. */
export function formatSubscribers(count?: number | null): string {
  if (count == null || !Number.isFinite(count) || count < 0) return '—'
  if (count >= 100000000) return `${Math.floor(count / 10000000) / 10}억`
  if (count >= 10000) return `${Math.floor(count / 1000) / 10}만`
  return Math.floor(count).toLocaleString('ko-KR')
}
