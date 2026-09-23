<script setup lang="ts">
import { computed, ref, useTemplateRef } from 'vue'
import { useElementSize, useIntersectionObserver, useWindowSize } from '@vueuse/core'
import type { Artist } from '@/api/types'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { avatarImageSource } from '@/lib/avatar-image'

const props = defineProps<{
  artist?: Pick<Artist, 'name' | 'image' | 'roman' | 'image_position' | 'image_variants'>
}>()
const avatar = useTemplateRef('avatar')
const { width, height } = useElementSize(avatar)
const windowSize = useWindowSize()
const visible = ref(false)
const { stop, isSupported } = useIntersectionObserver(
  avatar,
  ([entry]) => {
    if (entry?.isIntersecting) {
      visible.value = true
      stop()
    }
  },
  { rootMargin: '200px' },
)
// Reka preloads src with Image(), so native loading="lazy" alone does not defer it.
const src = computed(() => {
  if (isSupported.value && !visible.value) return ''
  if (width.value <= 0) return ''
  void windowSize.width.value
  return avatarImageSource(
    props.artist?.image || '',
    props.artist?.image_variants,
    Math.max(width.value, height.value),
    window.devicePixelRatio || 1,
  )
})
</script>

<template>
  <Avatar ref="avatar" class="artist-avatar">
    <AvatarImage
      :src="src"
      :alt="artist?.name || ''"
      decoding="async"
      :style="{ objectPosition: artist?.image_position }"
    />
    <AvatarFallback>{{ (artist?.roman || artist?.name || '').slice(0, 2) || '—' }}</AvatarFallback>
  </Avatar>
</template>
