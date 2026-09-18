import { describe, expect, it } from 'vitest'
import type { YouTubeLiveArchive, YouTubePerformance } from '@/api/types'
import { buildSongStats } from './songStats'

function archive(id: number, title: string, korean: string | null = null, artistKo: string | null = null): YouTubeLiveArchive {
  return {
    id, youtube_url: `https://www.youtube.com/watch?v=${id}`, video_title: '歌枠',
    artist_name: 'HACHI', status: 'ready', published_at: null, broadcast_at: null,
    last_checked_at: null, setlist: [], performances: [{
      id, song_title: title, song_title_ko: korean, original_artist: '青葉市子', original_artist_ko: artistKo,
      start_seconds: 0, timestamp_text: '0:00', tj_number: '12345', ky_number: '등록X',
    } as YouTubePerformance],
  }
}

describe('full archive statistics', () => {
  it('excludes broadcast chapters for every artist and both setlist formats', () => {
    const chapters = ['開始', '1開始 (시작)', '2お知らせ (공지사항)', '3Cパート (C파트)',
      '4🗓️今週のスケジュール (이번 주 스케줄)', '5🐺 ((・△・))', '雑談', '配信終了', '01. お知らせ', '🗓️来週の予定']
    const rows = chapters.flatMap((title, index) => {
      const performance = archive(index, title)
      performance.artist_name = `Artist ${index}`
      const fallback = { ...performance, id: index + 100, performances: [], setlist: [{ title, timestamp: '1:00' }] }
      return [performance, fallback]
    })
    expect(buildSongStats(rows, '', 'desc')).toEqual([])
  })
  it('keeps song titles containing chapter words and numeric titles', () => {
    const titles = ['始まりの歌', 'お知らせの歌', 'START DASH', 'The Beginning', 'Cパートの歌', '366日', 'アイドル']
    expect(buildSongStats(titles.map((title, index) => archive(index, title)), '', 'desc')).toHaveLength(titles.length)
  })
  it('counts older broadcasts beyond the first hundred before sorting or rendering', () => {
    const rows = Array.from({ length: 123 }, (_, index) => archive(index, 'いきのこり●ぼくら'))
    const stats = buildSongStats(rows, '', 'asc')
    expect(stats[0]?.count).toBe(123)
    expect(stats[0]?.occurrences).toHaveLength(123)
  })
  it('uses a later translation and keeps it when a shorter untranslated title appears', () => {
    const rows = [archive(1, 'いきのこり●ぼくら'), archive(2, 'いきのこり ぼくら', '살아남은 우리', '아오바 이치코'), archive(3, 'いきのこりぼくら')]
    const stats = buildSongStats(rows, '살아남은', 'desc')
    expect(stats).toHaveLength(1)
    expect(stats[0]).toMatchObject({ count: 3, titleKo: '살아남은 우리', originalArtistKo: '아오바 이치코' })
    expect(buildSongStats(rows, '아오바', 'asc')).toHaveLength(1)
  })
  it('finds the song despite the decorative dot in its stored title', () => {
    expect(buildSongStats([archive(1, 'いきのこり●ぼくら')], 'いきのこり ぼくら', 'asc')).toHaveLength(1)
  })
  it('keeps a TJ number with the aggregated song', () => {
    expect(buildSongStats([archive(1, 'Song')], '', 'desc')[0]?.tjNumbers).toEqual(['12345'])
  })
})
