<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'
import { ChevronRight, MapPin } from '@lucide/vue'
import type { Concert } from '@/api/types'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { formatDate, dateKey } from '@/lib/dates'
import { openOverlay } from '@/lib/overlays'
defineProps<{ concert: Concert; past?: boolean }>()
const router = useRouter()
const route = useRoute()
</script>
<template>
  <Button
    variant="outline"
    type="button"
    class="concert-row"
    @click="openOverlay(router, route, 'event', concert.id)"
  >
    <span class="concert-date">
      <small>
        {{ formatDate(concert.starts_at, { year: undefined, month: 'short', day: undefined }) }}
      </small>
      <strong>{{ Number(dateKey(new Date(concert.starts_at)).slice(-2)) }}</strong>
    </span>
    <div class="concert-summary">
      <div class="flex flex-wrap items-center gap-2">
        <Badge :variant="past ? 'outline' : 'secondary'">
          {{ past ? '지난 공연' : '공연 예정' }}
        </Badge>
        <Badge variant="outline">샘플 일정</Badge>
      </div>
      <h3>{{ concert.title }}</h3>
      <p>
        <MapPin />
        {{ concert.venue }} · {{ concert.city }}
      </p>
    </div>
    <ChevronRight data-icon="inline-end" />
  </Button>
</template>
