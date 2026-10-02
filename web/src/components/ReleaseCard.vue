<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { Album } from '@/api/types'
import { Item, ItemContent, ItemDescription, ItemHeader, ItemTitle } from '@/components/ui/item'
import { releaseCardMeta } from '@/lib/discography'
import { openOverlay } from '@/lib/overlays'
import AlbumCover from './AlbumCover.vue'

const props = defineProps<{ album: Album }>()
const route = useRoute()
const router = useRouter()
// A real URL keeps open-in-new-tab and direct access working; a plain click opens
// the query-backed detail overlay with the same history state as other overlays.
const href = computed(
  () =>
    router.resolve({
      path: route.path,
      query: { ...route.query, event: undefined, lyrics: undefined, album: props.album.id },
    }).href,
)
function open(event: MouseEvent) {
  if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey)
    return
  event.preventDefault()
  openOverlay(router, route, 'album', props.album.id)
}
</script>
<template>
  <Item as-child size="xs" class="release-card">
    <a :href="href" @click="open">
      <ItemHeader>
        <AlbumCover :src="album.image_url" :title="album.name" decorative class="release-cover" />
      </ItemHeader>
      <ItemContent class="min-w-0">
        <ItemTitle class="release-title line-clamp-2 w-full">{{ album.name }}</ItemTitle>
        <ItemDescription class="line-clamp-1">{{ releaseCardMeta(album) }}</ItemDescription>
      </ItemContent>
    </a>
  </Item>
</template>
