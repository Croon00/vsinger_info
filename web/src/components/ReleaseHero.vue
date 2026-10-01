<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowUpRight } from '@lucide/vue'
import { api } from '@/api/client'
import type { Album } from '@/api/types'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { useResource } from '@/composables/useResource'
import { formatDate } from '@/lib/dates'
import {
  HERO_PREVIEW_TRACKS,
  releaseLength,
  releaseLinkLabel,
  releaseTypeLabel,
} from '@/lib/discography'
import { openOverlay } from '@/lib/overlays'
import AlbumCover from './AlbumCover.vue'
import ReleaseTracks from './ReleaseTracks.vue'

const props = defineProps<{ album: Album; artistId: number; themeColor?: string }>()
const route = useRoute()
const router = useRouter()
// The listing has no tracks; the hero reads only this one release's detail.
const { data: detail } = useResource(
  (signal) =>
    props.album.tracks_loaded === false
      ? api.album(props.album.id, props.artistId, signal)
      : Promise.resolve(props.album),
  [() => props.album.id],
)
const tracks = computed(() => detail.value?.tracks ?? [])
const meta = computed(() =>
  [
    releaseTypeLabel(props.album.album_type),
    formatDate(props.album.release_date),
    tracks.value.length > 1 ? `${tracks.value.length}곡` : '',
    releaseLength(tracks.value),
  ]
    .filter(Boolean)
    .join(' · '),
)
// Same validity rule as the calendar's artist colors.
const tint = computed(() => {
  const color = props.themeColor?.trim()
  return color && /^#[0-9a-f]{6}$/i.test(color) ? color : ''
})
function openDetail() {
  openOverlay(router, route, 'album', props.album.id)
}
</script>
<template>
  <Card
    class="release-hero"
    :data-tinted="tint ? '' : undefined"
    :data-preview="tracks.length > 1 ? '' : undefined"
    :style="tint ? { '--release-tint': tint } : undefined"
  >
    <!-- Pointer shortcut only; the detail button below is the keyboard path. -->
    <div class="release-hero-cover" @click="openDetail">
      <AlbumCover :src="album.image_url" :title="album.name" decorative class="release-cover" />
    </div>
    <CardHeader class="release-hero-header">
      <CardDescription>최신 발매</CardDescription>
      <CardTitle>
        <h3 class="release-title">{{ album.name }}</h3>
      </CardTitle>
      <CardDescription>{{ meta }}</CardDescription>
    </CardHeader>
    <CardContent v-if="tracks.length > 1" class="release-hero-tracks">
      <ReleaseTracks :tracks="tracks" :limit="HERO_PREVIEW_TRACKS" compact />
    </CardContent>
    <CardFooter class="release-hero-actions">
      <Button v-if="album.source_url" as-child size="sm">
        <a :href="album.source_url" target="_blank" rel="noopener noreferrer">
          {{ releaseLinkLabel(album.source_url) }}
          <ArrowUpRight data-icon="inline-end" />
        </a>
      </Button>
      <Button variant="outline" size="sm" @click="openDetail">
        {{ tracks.length > HERO_PREVIEW_TRACKS ? `전체 ${tracks.length}곡 보기` : '자세히' }}
      </Button>
    </CardFooter>
  </Card>
</template>
