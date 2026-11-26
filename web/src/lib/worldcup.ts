// Original-song world cup: candidate draw, bracket progress and results.
// Pure functions over plain data so a run can be saved to localStorage and resumed.

export const WORLDCUP_SIZES = [16, 32, 64, 128] as const
export type WorldcupSize = (typeof WORLDCUP_SIZES)[number]
export type WorldcupMode = 'agency' | 'artists' | 'random'
export type WorldcupDraw = 'random' | 'popular'

export interface WorldcupSong {
  key: string
  videoId: string
  title: string
  artist: string
  viewCount: number | null
}

export interface WorldcupMatch {
  round: number
  winner: string
  loser: string
}

export interface WorldcupState {
  version: 2
  label: string
  scopeKind: WorldcupMode
  /** Original MVs or covers; runs saved before covers existed are originals. */
  songKind?: 'original' | 'cover'
  /** Idempotency key for the result submission. */
  submissionId: string
  startedAt: number
  /** Video IDs of every pick, in play order (sent to the statistics API). */
  matches: WorldcupMatch[]
  submitted?: boolean
  size: WorldcupSize
  songs: Record<string, WorldcupSong>
  /** Keys still in the current round, in bracket order (pairs are [0,1], [2,3], ...). */
  round: string[]
  /** Winners already picked in the current round. */
  winners: string[]
  /** Keys eliminated per round size, kept for the final ranking. */
  eliminated: Record<number, string[]>
  /** Previous snapshots for undo (bounded). */
  history: Pick<WorldcupState, 'round' | 'winners' | 'eliminated' | 'matches'>[]
}

export interface SourceSong {
  key: string
  title: string
  title_ko: string | null
  artist_name: string
  youtube_video_id: string | null
  view_count: number | null
}

export type Random = () => number

const VIDEO_ID = /^[A-Za-z0-9_-]{11}$/

/** Playable, de-duplicated candidates (one entry per video). */
export function toCandidates(rows: SourceSong[]): WorldcupSong[] {
  const byVideo = new Map<string, WorldcupSong>()
  for (const row of rows) {
    const videoId = row.youtube_video_id ?? ''
    if (!VIDEO_ID.test(videoId) || byVideo.has(videoId)) continue
    byVideo.set(videoId, {
      key: row.key,
      videoId,
      title: (row.title_ko || row.title).trim(),
      artist: row.artist_name.trim(),
      viewCount: row.view_count,
    })
  }
  return [...byVideo.values()]
}

export function shuffle<T>(items: T[], random: Random = Math.random): T[] {
  const copy = [...items]
  for (let i = copy.length - 1; i > 0; i--) {
    const j = Math.floor(random() * (i + 1))
    ;[copy[i], copy[j]] = [copy[j], copy[i]]
  }
  return copy
}

/** Largest bracket that the candidate count can fill. */
export function availableSizes(count: number): WorldcupSize[] {
  return WORLDCUP_SIZES.filter((size) => size <= count)
}

/**
 * Pick ``size`` songs. ``perArtistCap`` keeps one prolific artist from filling the bracket
 * (used for random mixes); when the cap leaves too few songs it is relaxed.
 */
export function drawSongs(
  candidates: WorldcupSong[],
  size: number,
  draw: WorldcupDraw,
  random: Random = Math.random,
  perArtistCap?: number,
): WorldcupSong[] {
  const ordered =
    draw === 'popular'
      ? [...candidates].sort((a, b) => (b.viewCount ?? -1) - (a.viewCount ?? -1))
      : shuffle(candidates, random)
  if (!perArtistCap) return ordered.slice(0, size)
  const counts = new Map<string, number>()
  const picked: WorldcupSong[] = []
  const skipped: WorldcupSong[] = []
  for (const song of ordered) {
    const used = counts.get(song.artist) ?? 0
    if (picked.length < size && used < perArtistCap) {
      picked.push(song)
      counts.set(song.artist, used + 1)
    } else skipped.push(song)
  }
  return [...picked, ...skipped].slice(0, size)
}

/** Order the first round so the same artist rarely meets itself in round one. */
export function seed(songs: WorldcupSong[], random: Random = Math.random): WorldcupSong[] {
  const order = shuffle(songs, random)
  // A few repair passes: swap the second song of a same-artist pair with a song from any
  // other pair, as long as neither pair ends up with one artist (``j ^ 1`` is j's opponent).
  for (let pass = 0; pass < 4; pass++) {
    let clean = true
    for (let i = 0; i + 1 < order.length; i += 2) {
      if (order[i].artist !== order[i + 1].artist) continue
      clean = false
      for (let j = 0; j < order.length; j++) {
        if (j >> 1 === i >> 1) continue
        if (order[j].artist !== order[i].artist && order[j ^ 1].artist !== order[i + 1].artist) {
          ;[order[i + 1], order[j]] = [order[j], order[i + 1]]
          break
        }
      }
    }
    if (clean) break
  }
  return order
}

export function start(
  label: string,
  songs: WorldcupSong[],
  random: Random = Math.random,
  scopeKind: WorldcupMode = 'agency',
  now = Date.now(),
  songKind: 'original' | 'cover' = 'original',
): WorldcupState {
  const size = songs.length as WorldcupSize
  if (!WORLDCUP_SIZES.includes(size)) throw new Error('Unsupported bracket size')
  const seeded = seed(songs, random)
  return {
    version: 2,
    label,
    scopeKind,
    songKind,
    submissionId: newId(random),
    startedAt: now,
    matches: [],
    size,
    songs: Object.fromEntries(seeded.map((song) => [song.key, song])),
    round: seeded.map((song) => song.key),
    winners: [],
    eliminated: {},
    history: [],
  }
}

export function currentPair(state: WorldcupState): [WorldcupSong, WorldcupSong] | null {
  const index = state.winners.length * 2
  if (state.round.length < 2 || index + 1 >= state.round.length) return null
  return [state.songs[state.round[index]], state.songs[state.round[index + 1]]]
}

export function isFinished(state: WorldcupState) {
  return state.round.length === 1
}

export function roundName(remaining: number) {
  return remaining === 2 ? '결승' : remaining === 4 ? '준결승' : `${remaining}강`
}

export function progress(state: WorldcupState) {
  const matches = state.round.length / 2
  return {
    round: roundName(state.round.length),
    match: Math.min(state.winners.length + 1, matches),
    matches,
    /** Matches finished over the whole bracket, out of size - 1. */
    done: state.size - state.round.length + state.winners.length,
    total: state.size - 1,
  }
}

const HISTORY_LIMIT = 300

export function choose(state: WorldcupState, side: 0 | 1): WorldcupState {
  const pair = currentPair(state)
  if (!pair) return state
  const winner = pair[side]
  const loser = pair[side ? 0 : 1]
  const size = state.round.length
  const eliminated = { ...state.eliminated, [size]: [...(state.eliminated[size] ?? []), loser.key] }
  const winners = [...state.winners, winner.key]
  const matches = [...state.matches, { round: size, winner: winner.videoId, loser: loser.videoId }]
  const snapshot = {
    round: state.round,
    winners: state.winners,
    eliminated: state.eliminated,
    matches: state.matches,
  }
  const history = [...state.history, snapshot].slice(-HISTORY_LIMIT)
  if (winners.length * 2 < state.round.length)
    return { ...state, winners, eliminated, matches, history }
  return { ...state, round: winners, winners: [], eliminated, matches, history }
}

export function undo(state: WorldcupState): WorldcupState {
  const previous = state.history.at(-1)
  if (!previous) return state
  return { ...state, ...previous, history: state.history.slice(0, -1) }
}

/** Body for POST /api/worldcup/results once the bracket is finished. */
export function submission(state: WorldcupState, clientId: string, now = Date.now()) {
  return {
    submission_id: state.submissionId,
    client_id: clientId,
    song_kind: state.songKind ?? 'original',
    scope_kind: state.scopeKind,
    scope_label: state.label.slice(0, 200),
    size: state.size,
    duration_seconds: Math.min(604800, Math.max(0, Math.floor((now - state.startedAt) / 1000))),
    matches: state.matches,
  }
}

function newId(random: Random) {
  if (random === Math.random && typeof crypto !== 'undefined' && 'randomUUID' in crypto)
    return crypto.randomUUID()
  const hex = Array.from({ length: 32 }, () => Math.floor(random() * 16).toString(16))
  hex[12] = '4'
  hex[16] = ((parseInt(hex[16], 16) & 3) | 8).toString(16)
  const s = hex.join('')
  return `${s.slice(0, 8)}-${s.slice(8, 12)}-${s.slice(12, 16)}-${s.slice(16, 20)}-${s.slice(20)}`
}

const CLIENT_KEY = 'utamowa-client-id'

/** Anonymous per-browser ID used only to de-duplicate and rate-limit submissions. */
export function clientId(): string {
  try {
    const saved = localStorage.getItem(CLIENT_KEY)
    if (saved && /^[0-9a-f-]{36}$/.test(saved)) return saved
    const created = newId(Math.random)
    localStorage.setItem(CLIENT_KEY, created)
    return created
  } catch {
    return newId(Math.random)
  }
}

/** Winner, runner-up and semi-finalists for the result screen. */
export function ranking(state: WorldcupState) {
  if (!isFinished(state)) return null
  return {
    winner: state.songs[state.round[0]],
    runnerUp: (state.eliminated[2] ?? []).map((key) => state.songs[key])[0] ?? null,
    semifinal: (state.eliminated[4] ?? []).map((key) => state.songs[key]),
    quarterfinal: (state.eliminated[8] ?? []).map((key) => state.songs[key]),
  }
}

const STORAGE_KEY = 'utamowa-worldcup-v2'

export function save(state: WorldcupState | null) {
  try {
    if (state) localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
    else localStorage.removeItem(STORAGE_KEY)
  } catch {
    // Private mode or full storage: the run continues without resume support.
  }
}

export function load(): WorldcupState | null {
  try {
    const value = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? 'null')
    if (
      value?.version === 2 &&
      Array.isArray(value.matches) &&
      Array.isArray(value.round) &&
      value.round.every((key: unknown) => typeof key === 'string' && key in value.songs)
    )
      return value as WorldcupState
  } catch {
    // Corrupt or unavailable storage is ignored.
  }
  return null
}
