<script setup lang="ts">
import { ref } from 'vue'
import { Play, ListMusic } from '@lucide/vue'
import type { Live } from '@/api/types'
import { formatDate, formatTime } from '@/lib/dates'
import { Badge } from '@/components/ui/badge'
defineProps<{ live: Live }>()
const imageFailed = ref(false)
</script>
<template>
  <RouterLink :to="`/lives/${live.id}`" class="live-card">
    <div class="live-thumb">
      <img
        v-if="!imageFailed"
        :src="`https://i.ytimg.com/vi/${live.video_id}/hqdefault.jpg`"
        :alt="live.title"
        loading="lazy"
        @error="imageFailed = true"
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
