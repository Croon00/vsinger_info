<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { pendingExploreScroll } from '@/app/router'
import { Search, X } from '@lucide/vue'
import { InputGroup, InputGroupInput, InputGroupAddon } from '@/components/ui/input-group'
import { Button } from '@/components/ui/button'
import { FieldGroup, Field, FieldLabel } from '@/components/ui/field'
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { api } from '@/api/client'
import { useResource } from '@/composables/useResource'
import { normalize } from '@/lib/search'
import { sortArtists, type ArtistSort } from '@/lib/artist-sort'
import ArtistTile from '@/components/ArtistTile.vue'
import ResourceState from '@/components/ResourceState.vue'
import SongExplore from '@/components/SongExplore.vue'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
const route = useRoute()
const router = useRouter()
const view = computed(() => (route.query.view === 'songs' ? 'songs' : 'artists'))
function changeView(value: string | number) {
  router.replace({ query: { ...route.query, view: value === 'songs' ? 'songs' : undefined } })
}
const query = ref(String(route.query.q ?? ''))
const agency = ref('all')
const sort = computed<ArtistSort>({
  get: () =>
    ['channel-created', 'channel-recent', 'subscribers', 'subscribers-low', 'name'].includes(
      String(route.query.sort),
    )
      ? (String(route.query.sort) as ArtistSort)
      : 'name',
  set: (value) => {
    router.replace({ query: { ...route.query, sort: value || undefined } })
  },
})
const { data, loading, error, reload } = useResource(api.artists)
watch(
  [loading, pendingExploreScroll],
  ([isLoading, top], _, onCleanup) => {
    if (isLoading || top === null) return
    let frame = 0
    let cancelled = false
    onCleanup(() => {
      cancelled = true
      cancelAnimationFrame(frame)
    })
    nextTick(() => {
      if (cancelled) return
      frame = requestAnimationFrame(() => {
        if (cancelled || pendingExploreScroll.value !== top) return
        window.scrollTo({ top, behavior: 'instant' })
        pendingExploreScroll.value = null
      })
    })
  },
  { flush: 'post', immediate: true },
)
watch(query, (q) => router.replace({ query: { ...route.query, q: q || undefined } }))
watch(
  () => route.query.q,
  (q) => {
    query.value = String(q ?? '')
  },
)
const agencies = computed(() => {
  const counts = new Map<string, number>()
  for (const artist of data.value ?? []) {
    if (artist.agency) {
      counts.set(artist.agency, (counts.get(artist.agency) ?? 0) + 1)
    }
  }
  return [...counts.keys()].sort().sort((a, b) => counts.get(b)! - counts.get(a)!)
})
const hasIndependentArtists = computed(() => (data.value ?? []).some((a) => !a.agency))
const filtered = computed(() => {
  return sortArtists(
    (data.value ?? []).filter(
      (a) =>
        (agency.value === 'all' ||
          (agency.value === 'independent' ? !a.agency : a.agency === agency.value)) &&
        [a.name, a.display_name, a.roman, ...(a.aliases ?? [])].some((s) =>
          normalize(s).includes(normalize(query.value)),
        ),
    ),
    sort.value,
  )
})
</script>
<template>
  <div class="page-container page-enter">
    <div class="page-heading">
      <h1>{{ view === 'songs' ? '곡 탐색' : '아티스트 탐색' }}</h1>
    </div>
    <Tabs :model-value="view" @update:model-value="changeView">
      <TabsList variant="line" class="mb-6">
        <TabsTrigger value="artists">아티스트 탐색</TabsTrigger>
        <TabsTrigger value="songs">곡 탐색</TabsTrigger>
      </TabsList>
      <TabsContent value="artists">
        <div class="explore-toolbar">
          <div class="explore-filters">
            <Select v-model="agency">
              <SelectTrigger aria-label="소속사 필터" class="explore-filter">
                <SelectValue placeholder="소속사 전체" />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  <SelectItem value="all">소속사 전체</SelectItem>
                  <SelectItem v-if="hasIndependentArtists" value="independent">개인세</SelectItem>
                  <SelectItem v-for="name in agencies" :key="name" :value="name">
                    {{ name }}
                  </SelectItem>
                </SelectGroup>
              </SelectContent>
            </Select>
            <Select v-model="sort">
              <SelectTrigger aria-label="정렬 기준" class="explore-filter">
                <SelectValue placeholder="정렬 기준" />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  <SelectItem value="subscribers">구독자 높은 순</SelectItem>
                  <SelectItem value="subscribers-low">구독자 낮은 순</SelectItem>
                  <SelectItem value="channel-created">채널 생성 오래 된 순</SelectItem>
                  <SelectItem value="channel-recent">채널 생성 최근 순</SelectItem>
                  <SelectItem value="name">가나다 순</SelectItem>
                </SelectGroup>
              </SelectContent>
            </Select>
          </div>
          <form role="search" aria-label="아티스트 검색" class="explore-search" @submit.prevent>
            <FieldGroup>
              <Field>
                <FieldLabel for="artist-search" class="sr-only">아티스트 이름</FieldLabel>
                <InputGroup class="h-11">
                  <InputGroupAddon><Search /></InputGroupAddon>
                  <InputGroupInput
                    id="artist-search"
                    v-model="query"
                    placeholder="아티스트 이름으로 찾기"
                  />
                  <InputGroupAddon v-if="query" align="inline-end">
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon-sm"
                      aria-label="검색어 지우기"
                      @click="query = ''"
                    >
                      <X />
                    </Button>
                  </InputGroupAddon>
                </InputGroup>
              </Field>
            </FieldGroup>
          </form>
          <p class="result-count" aria-live="polite">
            {{ filtered.length }}명의 아티스트
            <template v-if="sort === 'channel-created'">
              · 채널 생성일이 빠른 순 · 미확인은 마지막
            </template>
            <template v-else-if="sort === 'subscribers'">
              · 구독자가 많은 순 · 미확인은 마지막
            </template>
            <template v-else-if="sort === 'subscribers-low'">
              · 구독자가 적은 순 · 미확인은 마지막
            </template>
            <template v-else-if="sort === 'channel-recent'">
              · 채널 생성일이 최근 순 · 미확인은 마지막
            </template>
          </p>
        </div>
        <ResourceState
          loading-layout="artists"
          :loading="loading"
          :error="error"
          :empty="filtered.length === 0"
          title="아티스트를 찾지 못했어요"
          description="다른 이름으로 검색하거나 소속사 필터를 바꿔보세요."
          @retry="reload"
        >
          <div class="artist-grid">
            <ArtistTile v-for="artist in filtered" :key="artist.id" :artist="artist" />
          </div>
        </ResourceState>
      </TabsContent>
      <TabsContent value="songs"><SongExplore /></TabsContent>
    </Tabs>
  </div>
</template>
