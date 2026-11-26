import type { Lyrics } from './types'
import { ApiError, request } from './http'
import { invalidateReads } from './read-cache'

export type LyricsEditDraft = {
  version: number | null
  original_lyrics: string
  pronunciation_ko: string
  translation_ko: string
  lyrics_source_url: string | null
}
export type SavedLyrics = Lyrics & { recording_id: number; version: number }
const lyricsPath = (id: number) => `/api/recordings/${id}/lyrics`

export const loadLyricsForEdit = (id: number, signal?: AbortSignal) =>
  request<SavedLyrics>(lyricsPath(id), signal)

export async function saveLyrics(id: number, draft: LyricsEditDraft, editorKey: string) {
  const path = lyricsPath(id)
  let response: Response
  try {
    response = await fetch(path, {
      method: 'PUT',
      redirect: 'error',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        'X-Lyrics-Editor-Key': editorKey,
      },
      body: JSON.stringify(draft),
      signal: AbortSignal.timeout(45000),
    })
  } catch {
    throw new ApiError(
      0,
      '가사 저장 결과를 확인하지 못했어요. 같은 내용으로 다시 시도할 수 있어요.',
    )
  }
  if (!response.ok) {
    const messages: Record<number, string> = {
      401: 'API 연결 설정을 확인해 주세요.',
      403: '가사 편집 키가 올바르지 않아요.',
      404: '편집할 오리지널 녹음을 찾지 못했어요.',
      409: '가사가 다른 곳에서 변경됐거나 보관됐어요. 최신 가사를 확인해 주세요.',
      413: '가사 입력이 너무 길어요.',
      422: '가사와 출처 주소의 입력 형식을 확인해 주세요.',
      503: '가사 편집 설정이나 서버 연결을 확인해 주세요.',
    }
    throw new ApiError(response.status, messages[response.status] ?? '가사를 저장하지 못했어요.')
  }
  const saved: SavedLyrics = await response.json()
  invalidateReads(
    (key) =>
      key === path ||
      key.startsWith('/api/explore/songs?') ||
      key.startsWith('/api/albums/') ||
      /\/albums(?:\?|$)/.test(key),
  )
  return saved
}
