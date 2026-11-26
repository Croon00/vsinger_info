// World cup results and statistics. Not cached: statistics change with every finished run.
import { isMock } from './config'

export interface WorldcupSongStat {
  video_id: string
  title: string
  title_ko: string | null
  artist_name: string
  appearances: number
  championships: number
  championship_rate: number | null
  match_wins: number
  match_losses: number
  match_win_rate: number | null
}
export interface WorldcupStatsPage {
  items: WorldcupSongStat[]
  total: number
  offset: number
  limit: number
  total_runs: number
}
export type WorldcupStatOrder = 'championships' | 'championship_rate' | 'match_win_rate'
export type WorldcupSongKind = 'original' | 'cover'
export interface WorldcupPoolSummary {
  song_kind: WorldcupSongKind
  total: number
  agencies: { name: string; count: number }[]
  artists: { id: number; count: number }[]
}

export class WorldcupApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message)
  }
}

async function failure(response: Response) {
  if (response.status === 503) return new WorldcupApiError(503, '월드컵 통계를 아직 준비 중이에요.')
  if (response.status === 429)
    return new WorldcupApiError(429, '잠시 후 다시 시도해 주세요. 결과를 너무 자주 보냈어요.')
  return new WorldcupApiError(response.status, '월드컵 통계를 처리하지 못했어요.')
}

export async function submitWorldcup(
  body: unknown,
  signal?: AbortSignal,
): Promise<{ run_id: number; duplicate: boolean; winner: WorldcupSongStat | null }> {
  if (isMock) throw new WorldcupApiError(503, '목업 모드에서는 결과를 저장하지 않아요.')
  const response = await fetch('/api/worldcup/results', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(body),
    signal,
  })
  if (!response.ok) throw await failure(response)
  return response.json()
}

export async function worldcupStats(
  options: {
    songKind?: WorldcupSongKind
    agency?: string
    order?: WorldcupStatOrder
    minAppearances?: number
    videoIds?: string[]
    offset?: number
    limit?: number
  },
  signal?: AbortSignal,
): Promise<WorldcupStatsPage> {
  if (isMock) return { items: [], total: 0, offset: 0, limit: options.limit ?? 50, total_runs: 0 }
  const params = new URLSearchParams({
    song_kind: options.songKind ?? 'original',
    order: options.order ?? 'championships',
    min_appearances: String(options.minAppearances ?? 1),
    offset: String(options.offset ?? 0),
    limit: String(options.limit ?? 50),
  })
  if (options.agency) params.set('agency', options.agency)
  for (const id of options.videoIds ?? []) params.append('video_ids', id)
  const response = await fetch(`/api/worldcup/stats?${params}`, {
    headers: { Accept: 'application/json' },
    cache: 'no-store',
    signal,
  })
  if (!response.ok) throw await failure(response)
  return response.json()
}

/** Playable songs per agency and artist (cached by the server for a few minutes). */
export async function worldcupPoolSummary(
  songKind: WorldcupSongKind,
  signal?: AbortSignal,
): Promise<WorldcupPoolSummary> {
  if (isMock) return { song_kind: songKind, total: 0, agencies: [], artists: [] }
  const response = await fetch(`/api/worldcup/pool-summary?song_kind=${songKind}`, {
    headers: { Accept: 'application/json' },
    signal,
  })
  if (!response.ok) throw await failure(response)
  return response.json()
}

export function percent(value: number | null) {
  return value == null ? '—' : `${(value * 100).toFixed(1)}%`
}
