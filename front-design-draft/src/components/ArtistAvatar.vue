<script setup lang="ts">
import type { Artist } from '@/api/types'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'

defineProps<{
  artist?: Pick<Artist, 'name' | 'image' | 'roman' | 'image_position'>
}>()
</script>

<template>
  <Avatar class="artist-avatar">
    <AvatarImage
      :src="artist?.image || ''"
      :alt="artist?.name || ''"
      :style="{ objectPosition: artist?.image_position }"
    />
    <AvatarFallback>{{ artist?.roman.slice(0, 2) || '—' }}</AvatarFallback>
  </Avatar>
</template>
