<script setup lang="ts">
import type { Artist } from '@/api/types'
import ArtistAvatar from './ArtistAvatar.vue'
import { cn } from '@/lib/utils'
import FavoriteButton from './FavoriteButton.vue'
defineProps<{ artist: Artist; compact?: boolean }>()
</script>
<template>
  <article :class="cn('artist-tile', compact && 'compact')">
    <RouterLink
      :to="`/artists/${artist.id}`"
      class="artist-portrait-link"
      :aria-label="`${artist.name} 아티스트 상세`"
    >
      <ArtistAvatar :artist="artist" :class="cn(compact ? 'favorite-avatar' : 'explore-avatar')" />
    </RouterLink>
    <div class="artist-tile-caption">
      <RouterLink :to="`/artists/${artist.id}`">
        <h3>{{ artist.name }}</h3>
        <p>{{ compact ? artist.roman : artist.display_name }}</p>
      </RouterLink>
      <FavoriteButton v-if="!compact" :id="artist.id" :name="artist.name" />
    </div>
    <FavoriteButton v-if="compact" :id="artist.id" :name="artist.name" />
  </article>
</template>
