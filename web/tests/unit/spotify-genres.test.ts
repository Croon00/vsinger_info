import { describe, expect, it } from 'vitest'
import { spotifyGenreLabels } from '@/lib/spotify-genres'
import { mapArtist } from '@/api/backend'

describe('spotifyGenreLabels', () => {
  it('labels common market genres and keeps Spotify order', () => {
    expect(spotifyGenreLabels(['j-pop', 'anime', 'vocaloid', 'j-rock'])).toEqual([
      'J-Pop',
      '애니송',
      '보카로',
      'J-Rock',
    ])
  })
  it('title-cases unknown names and drops duplicate labels', () => {
    expect(spotifyGenreLabels(['space music', 'anime', 'anison'])).toEqual(['Space Music', '애니송'])
  })
  it('handles missing genres', () => {
    expect(spotifyGenreLabels(undefined)).toEqual([])
    expect(spotifyGenreLabels([])).toEqual([])
  })
})

describe('mapArtist spotify genres', () => {
  it('defaults to an empty list and drops blank names', () => {
    expect(mapArtist({ id: 1, name: 'a' }).spotify_genres).toEqual([])
    expect(mapArtist({ id: 1, name: 'a', spotify_genres: ['j-pop', ' '] }).spotify_genres).toEqual(['j-pop'])
  })
})
