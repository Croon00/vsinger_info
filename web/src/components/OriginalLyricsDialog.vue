<script setup lang="ts">
import { computed } from 'vue'
import { ArrowUpRight, PanelRight } from '@lucide/vue'
import type { ExploredSong } from '@/api/types'
import { api } from '@/api/client'
import { safeUrl } from '@/api/backend'
import { useResource } from '@/composables/useResource'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import LyricsLines from './LyricsLines.vue'
import ResourceState from './ResourceState.vue'

// Lyrics of one original song. "들으면서 보기" docks the player and lyrics beside the list.
const props = defineProps<{ song: ExploredSong | null; canListen: boolean }>()
const emit = defineEmits<{ close: []; listen: [song: ExploredSong] }>()
const recordingId = computed(() => props.song?.lyrics_recording_id ?? null)
const { data, loading, error, reload } = useResource(
  (signal) =>
    recordingId.value ? api.lyrics(String(recordingId.value), signal) : Promise.resolve(null),
  [recordingId],
)
</script>

<template>
  <Dialog
    :open="Boolean(song && recordingId)"
    @update:open="
      (open) => {
        if (!open) emit('close')
      }
    "
  >
    <DialogContent class="original-lyrics-dialog sm:max-w-2xl">
      <DialogHeader class="pr-8">
        <DialogTitle>{{ song?.title_ko || song?.title || '가사' }}</DialogTitle>
        <DialogDescription>{{ song?.artist_name }}</DialogDescription>
      </DialogHeader>
      <div class="overlay-scroll">
        <ResourceState :loading="loading" :error="error" @retry="reload">
          <div v-if="data" class="lyrics-content">
            <LyricsLines :key="recordingId ?? ''" :lyrics="data" />
          </div>
        </ResourceState>
      </div>
      <DialogFooter class="original-lyrics-footer">
        <Button v-if="data && safeUrl(data.lyrics_source_url)" as-child variant="ghost" size="sm">
          <a :href="safeUrl(data.lyrics_source_url)" target="_blank" rel="noopener noreferrer">
            가사 출처
            <ArrowUpRight data-icon="inline-end" />
          </a>
        </Button>
        <Button v-if="song && canListen" size="sm" @click="emit('listen', song)">
          <PanelRight data-icon="inline-start" />
          들으면서 보기
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
