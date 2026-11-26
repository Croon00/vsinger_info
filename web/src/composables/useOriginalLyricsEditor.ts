import { nextTick, ref, shallowRef } from 'vue'
import type { SavedLyrics } from '@/api/lyrics-editor'
import type { ExploredSong } from '@/api/types'

export function useOriginalLyricsEditor() {
  const editingSong = shallowRef<ExploredSong | null>(null)
  const savedLyrics = ref(new Map<string, SavedLyrics>())
  const saveStatus = ref('')
  let trigger: HTMLElement | null = null

  function openEditor(song: ExploredSong, event: MouseEvent) {
    trigger = event.currentTarget as HTMLElement
    saveStatus.value = ''
    editingSong.value = withLyrics(song)
  }

  function closeEditor() {
    editingSong.value = null
    nextTick(() => {
      if (trigger?.isConnected) trigger.focus()
    })
  }

  function onLyricsSaved(song: ExploredSong, lyrics: SavedLyrics) {
    savedLyrics.value.set(song.key, lyrics)
    saveStatus.value = `${song.title_ko || song.title} 가사를 저장했어요.`
    closeEditor()
  }

  function withLyrics(song: ExploredSong): ExploredSong {
    const saved = savedLyrics.value.get(song.key)
    return saved
      ? {
          ...song,
          lyrics_recording_id: saved.recording_id,
          lyrics_version: saved.version,
        }
      : song
  }

  return { editingSong, openEditor, closeEditor, onLyricsSaved, saveStatus, withLyrics }
}
