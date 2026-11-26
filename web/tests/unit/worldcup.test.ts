import { describe, expect, it } from 'vitest'
import {
  availableSizes,
  choose,
  currentPair,
  drawSongs,
  isFinished,
  progress,
  ranking,
  seed,
  start,
  submission,
  toCandidates,
  undo,
  type WorldcupSong,
} from '@/lib/worldcup'

function rng(seedValue = 1) {
  let value = seedValue
  return () => {
    value = (value * 16807) % 2147483647
    return value / 2147483647
  }
}
const song = (n: number, artist = `A${n % 5}`, views: number | null = n): WorldcupSong => ({
  key: `recording:${n}`,
  videoId: `video${String(n).padStart(6, '0')}`,
  title: `Song ${n}`,
  artist,
  viewCount: views,
})

describe('candidates', () => {
  it('keeps playable videos once and prefers the Korean title', () => {
    const rows = [
      {
        key: 'recording:1',
        title: 'Original',
        title_ko: '원제',
        artist_name: 'A',
        youtube_video_id: 'abcdefghijk',
        view_count: 3,
      },
      {
        key: 'recording:2',
        title: 'Same MV',
        title_ko: null,
        artist_name: 'A',
        youtube_video_id: 'abcdefghijk',
        view_count: 3,
      },
      {
        key: 'recording:3',
        title: 'No MV',
        title_ko: null,
        artist_name: 'B',
        youtube_video_id: null,
        view_count: null,
      },
      {
        key: 'recording:4',
        title: 'Bad id',
        title_ko: null,
        artist_name: 'B',
        youtube_video_id: 'short',
        view_count: null,
      },
    ]
    expect(toCandidates(rows)).toEqual([
      { key: 'recording:1', videoId: 'abcdefghijk', title: '원제', artist: 'A', viewCount: 3 },
    ])
  })
  it('offers only sizes the pool can fill, up to 128', () => {
    expect(availableSizes(15)).toEqual([])
    expect(availableSizes(40)).toEqual([16, 32])
    expect(availableSizes(500)).toEqual([16, 32, 64, 128])
  })
  it('draws popular songs by views with unknown counts last', () => {
    const pool = [song(1, 'A', null), song(2, 'B', 50), song(3, 'C', 900)]
    expect(drawSongs(pool, 2, 'popular').map((s) => s.key)).toEqual(['recording:3', 'recording:2'])
  })
  it('caps one artist in random mixes and relaxes the cap when the pool is short', () => {
    const pool = [
      ...Array.from({ length: 20 }, (_, i) => song(i, 'Prolific')),
      song(100, 'Other'),
      song(101, 'Third'),
    ]
    const capped = drawSongs(pool, 16, 'random', rng(3), 4)
    expect(capped).toHaveLength(16)
    expect(capped.filter((s) => s.artist !== 'Prolific')).toHaveLength(2)
  })
})

describe('bracket', () => {
  it('seeds round one without same-artist pairs when possible', () => {
    const songs = Array.from({ length: 32 }, (_, i) => song(i, `A${i % 4}`))
    for (let seedValue = 1; seedValue <= 30; seedValue++) {
      const order = seed(songs, rng(seedValue))
      for (let i = 0; i < order.length; i += 2)
        expect(order[i].artist).not.toBe(order[i + 1].artist)
      expect(new Set(order.map((s) => s.key)).size).toBe(32)
    }
  })
  it.each([16, 32, 64, 128])(
    'plays a %i bracket in size - 1 picks and ranks the finalists',
    (size) => {
      let state = start(
        'test',
        Array.from({ length: size }, (_, i) => song(i)),
        rng(size),
      )
      let picks = 0
      while (!isFinished(state)) {
        expect(currentPair(state)).not.toBeNull()
        state = choose(state, (picks % 2) as 0 | 1)
        picks++
      }
      expect(picks).toBe(size - 1)
      const result = ranking(state)!
      expect(result.winner).toBeTruthy()
      expect(result.runnerUp).toBeTruthy()
      expect(result.semifinal).toHaveLength(2)
      expect(result.quarterfinal).toHaveLength(4)
    },
  )
  it('reports progress and undoes the last pick across a round boundary', () => {
    let state = start(
      'test',
      Array.from({ length: 16 }, (_, i) => song(i)),
      rng(2),
    )
    expect(progress(state)).toMatchObject({
      round: '16강',
      match: 1,
      matches: 8,
      done: 0,
      total: 15,
    })
    for (let i = 0; i < 8; i++) state = choose(state, 0)
    expect(progress(state)).toMatchObject({ round: '8강', match: 1, matches: 4, done: 8 })
    const back = undo(state)
    expect(progress(back)).toMatchObject({ round: '16강', match: 8, done: 7 })
    expect(
      undo(
        start(
          't',
          Array.from({ length: 16 }, (_, i) => song(i)),
        ),
      ),
    ).toMatchObject({ round: expect.any(Array) })
  })
  it('records picks as video matches, undoes them and builds the submission body', () => {
    let state = start(
      'Label · 16강',
      Array.from({ length: 16 }, (_, i) => song(i)),
      rng(4),
      'agency',
      1000,
    )
    while (!isFinished(state)) state = choose(state, 0)
    expect(state.matches).toHaveLength(15)
    expect(state.matches.map((m) => m.round)).toEqual([
      16, 16, 16, 16, 16, 16, 16, 16, 8, 8, 8, 8, 4, 4, 2,
    ])
    expect(state.matches.at(-1)!.winner).toBe(ranking(state)!.winner.videoId)
    const back = undo(state)
    expect(back.matches).toHaveLength(14)
    const body = submission(state, 'client', 1000 + 95_400)
    expect(body).toMatchObject({
      scope_kind: 'agency',
      scope_label: 'Label · 16강',
      size: 16,
      duration_seconds: 95,
    })
    expect(body.submission_id).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
    )
    expect(body.matches).toBe(state.matches)
  })
  it('rejects unsupported sizes', () => {
    expect(() =>
      start(
        'bad',
        Array.from({ length: 12 }, (_, i) => song(i)),
      ),
    ).toThrow()
  })
})
