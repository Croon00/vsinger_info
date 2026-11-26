<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ArrowUpRight, FileText } from '@lucide/vue'
import type { ExploredSong } from '@/api/types'
import { api } from '@/api/client'
import { useResource } from '@/composables/useResource'
import { cn } from '@/lib/utils'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import LyricsLines from './LyricsLines.vue'
import ResourceState from './ResourceState.vue'

const props = defineProps<{ song: ExploredSong | null }>()
const emit = defineEmits<{ close: [] }>()
const videoId = computed(() =>
  /^[A-Za-z0-9_-]{11}$/.test(props.song?.youtube_video_id ?? '')
    ? props.song!.youtube_video_id!
    : '',
)
const embedUrl = computed(() => {
  if (!videoId.value) return ''
  const params = new URLSearchParams({
    autoplay: '1',
    playsinline: '1',
    rel: '0',
    origin: window.location.origin,
  })
  return `https://www.youtube.com/embed/${videoId.value}?${params}`
})
// Lyrics open beside the player; they scroll on their own while the video keeps playing.
const recordingId = computed(() => props.song?.lyrics_recording_id ?? null)
const showLyrics = ref(false)
watch(
  () => props.song?.key,
  () => {
    showLyrics.value = false
  },
)
const lyrics = useResource(
  (signal) =>
    showLyrics.value && recordingId.value
      ? api.lyrics(String(recordingId.value), signal)
      : Promise.resolve(null),
  [recordingId, showLyrics],
)
</script>
<template>
  <Dialog
    :open="Boolean(song && videoId)"
    @update:open="
      (open) => {
        if (!open) emit('close')
      }
    "
  >
    <DialogContent
      :class="
        cn(
          'song-video-dialog gap-0 overflow-hidden p-0 sm:max-w-[min(94vw,1200px)]',
          showLyrics && 'with-lyrics sm:max-w-[min(96vw,1600px)]',
        )
      "
    >
      <DialogHeader class="p-6 pr-16">
        <DialogTitle>{{ song?.title_ko || song?.title || '영상 재생' }}</DialogTitle>
        <DialogDescription>{{ song?.artist_name }}</DialogDescription>
      </DialogHeader>
      <div class="song-video-body">
        <div v-if="song && embedUrl" class="song-video-player">
          <iframe
            :key="videoId"
            :src="embedUrl"
            :title="`${song.title_ko || song.title} YouTube 재생`"
            class="block size-full"
            width="1280"
            height="720"
            allow="autoplay; encrypted-media; picture-in-picture; fullscreen"
            allowfullscreen
            referrerpolicy="strict-origin-when-cross-origin"
          />
        </div>
        <section v-if="showLyrics" class="song-video-lyrics" aria-label="가사">
          <div class="song-video-lyrics-scroll">
            <ResourceState
              :loading="lyrics.loading.value"
              :error="lyrics.error.value"
              @retry="lyrics.reload"
            >
              <div v-if="lyrics.data.value" class="lyrics-content">
                <LyricsLines :key="recordingId ?? ''" :lyrics="lyrics.data.value" />
              </div>
            </ResourceState>
          </div>
        </section>
      </div>
      <DialogFooter class="p-4">
        <Button
          v-if="recordingId"
          :variant="showLyrics ? 'secondary' : 'outline'"
          size="sm"
          :aria-pressed="showLyrics"
          @click="showLyrics = !showLyrics"
        >
          <FileText data-icon="inline-start" />
          {{ showLyrics ? '가사 닫기' : '가사 보기' }}
        </Button>
        <Button v-if="videoId" as-child variant="ghost" size="sm">
          <a
            :href="`https://www.youtube.com/watch?v=${videoId}`"
            target="_blank"
            rel="noopener noreferrer"
          >
            YouTube에서 보기
            <ArrowUpRight data-icon="inline-end" />
          </a>
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
