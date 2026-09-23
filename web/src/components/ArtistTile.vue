<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import type { Artist } from '@/api/types'
import ArtistAvatar from './ArtistAvatar.vue'
import { cn } from '@/lib/utils'
import FavoriteButton from './FavoriteButton.vue'
const props = defineProps<{ artist: Artist; compact?: boolean }>()
const route = useRoute()
const artistTo = computed(() => {
  const returnTo = ['/', '/explore', '/search'].includes(route.path) ? route.fullPath : null
  return {
    path: `/artists/${props.artist.id}`,
    state: returnTo ? { artistReturnTo: returnTo, artistBackSteps: 1 } : undefined,
  }
})
</script>
<template>
  <article :class="cn('artist-tile', compact && 'compact')">
    <RouterLink
      :to="artistTo"
      class="artist-portrait-link"
      :aria-label="`${artist.name} 아티스트 상세`"
    >
      <ArtistAvatar :artist="artist" :class="cn(compact ? 'favorite-avatar' : 'explore-avatar')" />
    </RouterLink>
    <div class="artist-tile-caption">
      <RouterLink :to="artistTo" class="artist-name-link">
        <h3 class="truncate">{{ artist.name }}</h3>
        <p class="truncate">{{ artist.display_name }}</p>
      </RouterLink>
      <FavoriteButton v-if="!compact" :id="artist.id" :name="artist.name" />
    </div>
  </article>
</template>
