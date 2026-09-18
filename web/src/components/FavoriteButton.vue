<script setup lang="ts">
import { Heart } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { favoriteIds, toggleFavorite } from '@/composables/preferences'
defineProps<{ id: number; name: string }>()
</script>
<template>
  <Button
    variant="secondary"
    size="icon"
    class="favorite-button"
    :aria-label="`${name} 즐겨찾기`"
    :aria-pressed="favoriteIds.includes(id)"
    @click="toggleFavorite(id, name)"
  >
    <span class="t-icon-swap" :data-state="favoriteIds.includes(id) ? 'b' : 'a'" aria-hidden="true">
      <Heart class="t-icon" data-icon="a" />
      <Heart class="t-icon" data-icon="b" fill="currentColor" />
    </span>
  </Button>
</template>
