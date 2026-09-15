<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Play, ListMusic } from '@lucide/vue'
import type { Live } from '@/api/types'
import { formatDate, formatTime } from '@/lib/dates'
import { Badge } from '@/components/ui/badge'
const props = defineProps<{ live: Live }>()
const qualities = ['maxresdefault', 'mqdefault', 'hqdefault']
const imageIndex = ref(0)
const imageFailed = computed(() => imageIndex.value >= qualities.length)
const thumbnail = computed(
  () => `https://i.ytimg.com/vi/${props.live.video_id}/${qualities[imageIndex.value]}.jpg`,
)
watch(
  () => props.live.video_id,
  () => {
    imageIndex.value = 0
  },
)
function nextThumbnail() {
  imageIndex.value++
}
function checkThumbnail(event: Event) {
  // YouTube sometimes returns a 120px placeholder with HTTP 200 for a missing size.
  if ((event.target as HTMLImageElement).naturalWidth <= 120) nextThumbnail()
}
</script>
<template>
  <RouterLink :to="`/lives/${live.id}`" class="live-card">
    <div class="live-thumb">
      <img
        v-if="!imageFailed"
        :src="thumbnail"
        :alt="live.title"
        loading="lazy"
        width="1280"
        height="720"
        referrerpolicy="strict-origin-when-cross-origin"
        @load="checkThumbnail"
        @error="nextThumbnail"
      />
      <ListMusic v-else class="size-12" />
      <span class="live-play"><Play fill="currentColor" class="size-5" /></span>
      <Badge variant="secondary" class="absolute bottom-3 right-3">
        {{ formatTime(live.duration_seconds) }}
      </Badge>
    </div>
    <p class="eyebrow">{{ formatDate(live.broadcast_at, { month: '2-digit', day: '2-digit' }) }}</p>
    <h3>{{ live.title_ko || live.title }}</h3>
    <p class="text-sm text-muted-foreground">
      {{
        live.performances.length
          ? `${live.performances.length}곡의 세트리스트`
          : '세트리스트 준비 중'
      }}
      <span aria-hidden="true">↗</span>
    </p>
  </RouterLink>
</template>
