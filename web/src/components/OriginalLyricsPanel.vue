<script setup lang="ts">
import { computed } from 'vue'
import { X } from '@lucide/vue'
import type { ExploredSong } from '@/api/types'
import { api } from '@/api/client'
import { useResource } from '@/composables/useResource'
import { Button } from '@/components/ui/button'
import LyricsLines from './LyricsLines.vue'
import ResourceState from './ResourceState.vue'

// Player and lyrics docked beside the original-song list. It stays in view while the page
// scrolls; the lyrics scroll inside the panel.
const props = defineProps<{ song: ExploredSong }>()
const emit = defineEmits<{ close: [] }>()
const videoId = computed(() =>
  /^[A-Za-z0-9_-]{11}$/.test(props.song.youtube_video_id ?? '') ? props.song.youtube_video_id! : '',
)
const embedUrl = computed(() => {
  const params = new URLSearchParams({
    autoplay: '1',
    playsinline: '1',
    rel: '0',
    origin: window.location.origin,
  })
  return `https://www.youtube.com/embed/${videoId.value}?${params}`
})
const recordingId = computed(() => props.song.lyrics_recording_id ?? null)
const { data, loading, error, reload } = useResource(
  (signal) =>
    recordingId.value ? api.lyrics(String(recordingId.value), signal) : Promise.resolve(null),
  [recordingId, () => props.song.lyrics_version],
)
</script>

<template>
  <aside class="original-lyrics-panel" aria-label="재생 중인 곡과 가사">
    <header class="original-lyrics-panel-head">
      <div class="min-w-0">
        <h3>{{ song.title_ko || song.title }}</h3>
        <p>{{ song.artist_name }}</p>
      </div>
      <Button variant="ghost" size="icon" aria-label="가사 패널 닫기" @click="emit('close')">
        <X />
      </Button>
    </header>
    <div v-if="videoId" class="original-lyrics-panel-player">
      <iframe
        :key="videoId"
        :src="embedUrl"
        :title="`${song.title_ko || song.title} YouTube 재생`"
        width="640"
        height="360"
        allow="autoplay; encrypted-media; picture-in-picture; fullscreen"
        allowfullscreen
        referrerpolicy="strict-origin-when-cross-origin"
      />
    </div>
    <div class="original-lyrics-panel-body">
      <ResourceState
        :loading="loading"
        :error="error"
        :empty="!recordingId"
        title="등록된 가사가 없습니다"
        description="가사가 등록되면 여기에 함께 표시됩니다."
        @retry="reload"
      >
        <div v-if="data" class="lyrics-content">
          <LyricsLines :key="recordingId ?? ''" :lyrics="data" />
        </div>
      </ResourceState>
    </div>
  </aside>
</template>
