<script setup lang="ts">
import { computed, ref } from 'vue'
import { Play, Music2 } from '@lucide/vue'
import type { Cover } from '@/api/types'
import { formatDate, formatTime } from '@/lib/dates'
import { Badge } from '@/components/ui/badge'
const props = defineProps<{ cover: Cover }>()
const failed = ref(false)
const validId = computed(() => /^[A-Za-z0-9_-]{11}$/.test(props.cover.youtube_video_id))
const url = computed(() =>
  validId.value ? `https://www.youtube.com/watch?v=${props.cover.youtube_video_id}` : undefined,
)
</script>
<template>
  <component
    :is="url ? 'a' : 'article'"
    :href="url"
    :target="url ? '_blank' : undefined"
    rel="noopener noreferrer"
    class="live-card"
  >
    <div class="live-thumb">
      <img
        v-if="validId && !failed"
        :src="`https://i.ytimg.com/vi/${cover.youtube_video_id}/hqdefault.jpg`"
        :alt="cover.title"
        loading="lazy"
        width="480"
        height="360"
        @error="failed = true"
      />
      <Music2 v-else class="size-12" />
      <span v-if="url" class="live-play" aria-hidden="true">
        <Play fill="currentColor" class="size-5" />
      </span>
      <Badge
        v-if="cover.duration_seconds && cover.duration_seconds > 0"
        variant="secondary"
        class="absolute bottom-3 right-3"
      >
        {{ formatTime(cover.duration_seconds) }}
      </Badge>
    </div>
    <h3>{{ cover.title }}</h3>
    <div class="live-meta">
      <p>{{ formatDate(cover.published_at ?? '', { month: '2-digit', day: '2-digit' }) }}</p>
      <span aria-hidden="true">・</span>
      <span>YouTube ↗</span>
    </div>
  </component>
</template>
