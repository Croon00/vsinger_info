<script setup lang="ts">
import { computed } from 'vue'
import { ArrowUpRight } from '@lucide/vue'
import type { ExploredSong } from '@/api/types'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
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
    <DialogContent class="song-video-dialog gap-0 overflow-hidden p-0 sm:max-w-4xl">
      <DialogHeader class="p-6 pr-16">
        <DialogTitle>{{ song?.title_ko || song?.title || '영상 재생' }}</DialogTitle>
        <DialogDescription>{{ song?.artist_name }}</DialogDescription>
      </DialogHeader>
      <div v-if="song && embedUrl" class="aspect-video min-h-50 w-full">
        <iframe
          :key="videoId"
          :src="embedUrl"
          :title="`${song.title_ko || song.title} YouTube 재생`"
          class="block size-full"
          width="960"
          height="540"
          allow="autoplay; encrypted-media; picture-in-picture; fullscreen"
          allowfullscreen
          referrerpolicy="strict-origin-when-cross-origin"
        />
      </div>
      <DialogFooter class="p-4">
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
