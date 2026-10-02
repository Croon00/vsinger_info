<script setup lang="ts">
import { computed } from 'vue'
import { FileText } from '@lucide/vue'
import type { Track } from '@/api/types'
import { Button } from '@/components/ui/button'
import {
  Item,
  ItemActions,
  ItemContent,
  ItemDescription,
  ItemGroup,
  ItemTitle,
} from '@/components/ui/item'
import { displayName } from '@/lib/display-name'
import { discGroups, isCurrentArtist, lyricsKey, performsOn, showsCredits } from '@/lib/discography'
import { cn } from '@/lib/utils'

// compact: the hero preview shows only number, title and length.
const props = withDefaults(
  defineProps<{
    tracks: Track[]
    artistIds?: number[]
    highlight?: boolean
    limit?: number
    compact?: boolean
  }>(),
  { artistIds: () => [] },
)
const emit = defineEmits<{ lyrics: [track: Track] }>()
const groups = computed(() =>
  discGroups(props.limit ? props.tracks.slice(0, props.limit) : props.tracks),
)
const multiDisc = computed(() => !props.compact && discGroups(props.tracks).length > 1)
</script>
<template>
  <div class="release-tracks">
    <section
      v-for="group in groups"
      :key="group.disc"
      :aria-label="multiDisc ? `Disc ${group.disc}` : undefined"
    >
      <h3 v-if="multiDisc" class="release-disc-title">Disc {{ group.disc }}</h3>
      <ItemGroup class="has-data-[size=xs]:gap-0.5">
        <Item
          v-for="(track, index) in group.tracks"
          :key="track.id"
          role="listitem"
          size="xs"
          :variant="highlight && performsOn(track, artistIds) ? 'muted' : 'default'"
          class="release-track"
        >
          <span class="release-track-number">{{ track.track_number ?? index + 1 }}</span>
          <ItemContent class="min-w-0">
            <ItemTitle
              :id="compact ? undefined : `release-track-${track.id}`"
              class="release-track-title line-clamp-2 w-full"
            >
              {{ displayName(track.title, track.title_ko) }}
            </ItemTitle>
            <ItemDescription v-if="!compact && showsCredits(track, artistIds)" class="line-clamp-1">
              <template v-for="(artist, i) in track.artists" :key="`${i}-${artist.name}`">
                <template v-if="i">&nbsp;·&nbsp;</template>
                <span
                  :class="cn(isCurrentArtist(artist, artistIds) && 'text-foreground font-medium')"
                >
                  {{ displayName(artist.name, artist.name_ko) }}
                </span>
              </template>
            </ItemDescription>
          </ItemContent>
          <ItemContent v-if="track.duration" class="flex-none">
            <ItemDescription class="tabular-nums">{{ track.duration }}</ItemDescription>
          </ItemContent>
          <ItemActions v-if="!compact && track.has_lyrics">
            <Button
              variant="ghost"
              size="sm"
              :data-lyrics-id="lyricsKey(track)"
              :aria-describedby="`release-track-${track.id}`"
              @click="emit('lyrics', track)"
            >
              <FileText data-icon="inline-start" />
              가사
            </Button>
          </ItemActions>
        </Item>
      </ItemGroup>
    </section>
  </div>
</template>
