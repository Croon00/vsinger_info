<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowUpRight, ChevronDown } from '@lucide/vue'
import { api } from '@/api/client'
import type { Artist } from '@/api/types'
import { Button } from '@/components/ui/button'
import { ItemGroup } from '@/components/ui/item'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { useResource } from '@/composables/useResource'
import {
  RELEASE_FILTERS,
  RELEASES_PAGE_SIZE,
  filterReleases,
  latestPrimaryRelease,
  releaseCounts,
  releaseFilter,
  type ReleaseFilter,
} from '@/lib/discography'
import ReleaseCard from './ReleaseCard.vue'
import ReleaseHero from './ReleaseHero.vue'
import ResourceState from './ResourceState.vue'

const props = defineProps<{ artist: Artist; artistId: number }>()
const route = useRoute()
const router = useRouter()
const { data, loading, error, reload } = useResource(
  (signal) => api.albums(props.artistId, signal),
  [() => props.artistId],
)
const albums = computed(() => data.value ?? [])
const counts = computed(() => releaseCounts(albums.value))
const filters = computed(() =>
  RELEASE_FILTERS.filter((f) => f.value === 'all' || counts.value[f.value] > 0),
)
// Chips only help when at least two kinds of release exist.
const showFilters = computed(() => filters.value.length > 2)
const filter = computed<ReleaseFilter>(() => {
  const requested = releaseFilter(route.query.group)
  return showFilters.value && counts.value[requested] > 0 ? requested : 'all'
})
const items = computed(() => filterReleases(albums.value, filter.value))
const limit = ref(RELEASES_PAGE_SIZE)
watch([() => props.artistId, filter], () => {
  limit.value = RELEASES_PAGE_SIZE
})
const visible = computed(() => items.value.slice(0, limit.value))
const hero = computed(() =>
  filter.value === 'all' ? latestPrimaryRelease(albums.value) : undefined,
)
const spotifyUrl = computed(() => props.artist.links.find((l) => l.label === 'Spotify')?.url)
function setFilter(value: unknown) {
  const next = releaseFilter(value)
  if (!value || next === filter.value) return
  // Replace keeps the artist page's back-button state and avoids one entry per chip.
  router.replace({ query: { ...route.query, group: next === 'all' ? undefined : next } })
}
</script>
<template>
  <section class="artist-discography" aria-labelledby="discography-heading">
    <div class="section-heading">
      <h2 id="discography-heading" class="flex items-center">
        디스코그래피
        <span v-if="data">{{ albums.length }}개</span>
      </h2>
      <span class="text-xs text-muted-foreground">최신순</span>
    </div>
    <ResourceState
      :loading="loading"
      :error="error"
      :empty="!albums.length"
      title="등록된 발매곡이 없어요"
      loading-layout="releases"
      @retry="reload"
    >
      <template #action>
        <Button v-if="spotifyUrl" as-child variant="outline">
          <a :href="spotifyUrl" target="_blank" rel="noopener noreferrer">
            Spotify에서 보기
            <ArrowUpRight data-icon="inline-end" />
          </a>
        </Button>
      </template>
      <div v-if="showFilters" class="release-filters">
        <ToggleGroup
          type="single"
          variant="outline"
          :model-value="filter"
          aria-label="발매 종류"
          @update:model-value="setFilter"
        >
          <ToggleGroupItem
            v-for="option in filters"
            :key="option.value"
            :value="option.value"
            :aria-label="`${option.label} ${counts[option.value]}개`"
            size="sm"
          >
            {{ option.label }}
            <span class="text-muted-foreground tabular-nums">{{ counts[option.value] }}</span>
          </ToggleGroupItem>
        </ToggleGroup>
      </div>
      <ReleaseHero
        v-if="hero"
        :key="hero.id"
        :album="hero"
        :artist-id="artistId"
        :theme-color="artist.theme_color"
      />
      <ItemGroup class="release-grid" aria-label="발매 목록">
        <div v-for="album in visible" :key="album.id" role="listitem" class="min-w-0">
          <ReleaseCard :album="album" />
        </div>
      </ItemGroup>
      <Button
        v-if="items.length > visible.length"
        variant="outline"
        class="mx-auto mt-8 flex"
        @click="limit += RELEASES_PAGE_SIZE"
      >
        더보기
        <ChevronDown data-icon="inline-end" />
      </Button>
    </ResourceState>
  </section>
</template>
