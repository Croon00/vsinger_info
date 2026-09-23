<script setup lang="ts">
import { Cake, CalendarDays as CalendarIcon, ChevronRight } from '@lucide/vue'
import type { Artist, CalendarEvent } from '@/api/types'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import ArtistAvatar from '@/components/ArtistAvatar.vue'
import { formatDate } from '@/lib/dates'
import { cn } from '@/lib/utils'
const props = defineProps<{ events: CalendarEvent[]; artists: Artist[]; showDate?: boolean }>()
defineEmits<{ select: [event: CalendarEvent] }>()
const artist = (id: number) => props.artists.find((a) => a.id === id)
function subtitle(event: CalendarEvent) {
  const owner = artist(event.artist_id)
  if (event.kind === 'birthday' && owner?.display_name?.trim())
    return event.person
      ? `${owner.display_name} · ${event.person} 생일`
      : `${owner.display_name} 생일`
  return event.concert?.venue || owner?.name
}
</script>
<template>
  <div class="agenda-list">
    <template v-for="(event, index) in events" :key="event.id + event.date">
      <Separator v-if="index" />
      <Button
        variant="ghost"
        :class="cn('schedule-entry', showDate ? 'month-event' : 'agenda-item')"
        @click="$emit('select', event)"
      >
        <span v-if="showDate" class="entry-date">
          <strong>{{ Number(event.date.slice(-2)) }}</strong>
          <span>
            {{
              formatDate(event.date, {
                year: undefined,
                month: undefined,
                day: undefined,
                weekday: 'short',
              })
            }}
          </span>
        </span>
        <ArtistAvatar :artist="artist(event.artist_id)" class="size-9" />
        <span class="entry-copy">
          <span class="entry-kind">
            <component :is="event.kind === 'birthday' ? Cake : CalendarIcon" />
            {{ event.kind === 'birthday' ? '생일' : '공연' }}
          </span>
          <span class="entry-title">{{ event.title }}</span>
          <span class="entry-place">
            {{ subtitle(event) }}
          </span>
        </span>
        <ChevronRight data-icon="inline-end" />
      </Button>
    </template>
  </div>
</template>
