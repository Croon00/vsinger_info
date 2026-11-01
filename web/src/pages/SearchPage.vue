<script setup lang="ts">
import { computed, onScopeDispose, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ChevronRight } from '@lucide/vue'
import { api } from '@/api/client'
import type { SearchPerformance, SearchResults } from '@/api/types'
import { Button } from '@/components/ui/button'
import BroadcastPeriodFilter from '@/components/BroadcastPeriodFilter.vue'
import { useResource } from '@/composables/useResource'
import { formatDate } from '@/lib/dates'
import { displayName } from '@/lib/display-name'
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import SearchForm from '@/components/SearchForm.vue'
import ArtistTile from '@/components/ArtistTile.vue'
import ArchiveThumbnail from '@/components/ArchiveThumbnail.vue'
import ResourceState from '@/components/ResourceState.vue'
const route = useRoute()
const router = useRouter()
const query = computed(() => String(route.query.q ?? ''))
const baseScope = computed(() => {
  const id = Number(route.query.artist_id)
  return {
    artistId: Number.isInteger(id) && id > 0 ? id : undefined,
    songKey: typeof route.query.song_key === 'string' ? route.query.song_key : undefined,
    agency: typeof route.query.agency === 'string' ? route.query.agency : undefined,
  }
})
function updateFilter(key: string, value: string | string[]) {
  const next = { ...route.query }
  if (!value.length) delete next[key]
  else next[key] = value
  router.replace({ query: next })
}
const selectedPerformers = computed<string[]>({
  get: () => [
    ...new Set(
      (Array.isArray(route.query.artist_ids)
        ? route.query.artist_ids
        : [route.query.artist_ids]
      ).filter((id): id is string => typeof id === 'string' && /^[1-9]\d*$/.test(id)),
    ),
  ],
  set: (ids) => updateFilter('artist_ids', ids),
})
function selectPerformers(value: unknown) {
  const ids = Array.isArray(value) ? value.map(String) : []
  selectedPerformers.value = ids.includes('all') ? [] : ids
}
const start = computed({
  get: () => String(route.query.start ?? ''),
  set: (value: string) => updateFilter('start', value),
})
const end = computed({
  get: () => String(route.query.end ?? ''),
  set: (value: string) => updateFilter('end', value),
})
const invalidRange = computed(() => !!start.value && !!end.value && start.value > end.value)
function applyPeriod(period: { start: string; end: string }) {
  const next = { ...route.query }
  if (period.start) next.start = period.start
  else delete next.start
  if (period.end) next.end = period.end
  else delete next.end
  router.replace({ query: next })
}
const scope = computed(() => ({
  ...baseScope.value,
  artistIds: selectedPerformers.value.map(Number),
  start: start.value || undefined,
  end: end.value || undefined,
}))
function clearFilters() {
  const next = { ...route.query }
  delete next.artist_ids
  delete next.start
  delete next.end
  router.replace({ query: next })
}
const {
  data: songSingers,
  error: singersError,
  reload: reloadSingers,
} = useResource(
  (signal) =>
    baseScope.value.songKey
      ? api.songPerformers(baseScope.value.songKey, baseScope.value.agency, signal)
      : query.value.trim()
        ? api.searchPerformers(
            query.value,
            baseScope.value.agency,
            baseScope.value.artistId,
            signal,
          )
        : Promise.resolve([]),
  [
    query,
    () => baseScope.value.songKey,
    () => baseScope.value.agency,
    () => baseScope.value.artistId,
  ],
)
const original = ref('all')
const extra = ref<SearchPerformance[]>([])
const moreLoading = ref(false)
const moreError = ref('')
let moreController: AbortController | undefined
onScopeDispose(() => moreController?.abort())
const { data, loading, error, reload } = useResource(
  (signal) =>
    invalidRange.value
      ? Promise.resolve<SearchResults>({ artists: [], performances: [], total: 0 })
      : api.search(query.value, signal, 0, scope.value),
  [query, scope],
)
watch(data, () => {
  moreController?.abort()
  moreLoading.value = false
  extra.value = []
  moreError.value = ''
})
const results = computed(() => [...(data.value?.performances ?? []), ...extra.value])
async function loadMore() {
  if (moreLoading.value) return
  const initial = data.value
  const controller = new AbortController()
  moreController = controller
  moreLoading.value = true
  moreError.value = ''
  try {
    const result = await api.search(
      query.value,
      controller.signal,
      results.value.length,
      scope.value,
    )
    if (data.value === initial) {
      const known = new Set(results.value.map((p) => p.id))
      extra.value.push(...result.performances.filter((p) => !known.has(p.id)))
    }
  } catch (e) {
    if (!controller.signal.aborted && data.value === initial)
      moreError.value = e instanceof Error ? e.message : '불러오지 못했어요.'
  } finally {
    if (moreController === controller) moreLoading.value = false
  }
}
watch(
  [
    query,
    () => baseScope.value.songKey,
    () => baseScope.value.agency,
    () => baseScope.value.artistId,
  ],
  () => {
    original.value = 'all'
  },
)
const singers = computed(() => songSingers.value ?? [])
const originals = computed(() => [
  ...results.value
    .filter((p) => p.original_artist.trim())
    .reduce((map, p) => {
      if (!map.get(p.original_artist))
        map.set(p.original_artist, p.original_artist_ko?.trim() ?? '')
      return map
    }, new Map<string, string>()),
])
const performances = computed(() =>
  results.value.filter((p) => original.value === 'all' || p.original_artist === original.value),
)
function search(q: string) {
  router.push({ path: '/search', query: { q } })
}
</script>
<template>
  <div class="page-container search-page page-enter">
    <div class="page-heading">
      <h1>{{ baseScope.artistId ? '부른 날짜' : '검색 결과' }}</h1>
      <p v-if="baseScope.artistId">방송 날짜를 선택하면 해당 곡을 부른 시점부터 볼 수 있어요.</p>
    </div>
    <SearchForm :initial="query" @search="search" />
    <div v-if="query.trim() || scope.artistId">
      <div class="mb-6 mt-8 flex flex-wrap items-end justify-end gap-3">
        <Select :model-value="selectedPerformers" multiple @update:model-value="selectPerformers">
          <SelectTrigger aria-label="부른 아티스트" class="min-w-36">
            <SelectValue>
              {{
                selectedPerformers.length
                  ? `부른 아티스트 ${selectedPerformers.length}명`
                  : '부른 아티스트 전체'
              }}
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            <SelectGroup>
              <SelectItem value="all">부른 아티스트 전체</SelectItem>
              <SelectItem
                v-for="a in singers"
                :key="a.id ?? a.name"
                :value="String(a.id ?? a.name)"
              >
                {{ displayName(a.name, a.display_name) }}
              </SelectItem>
            </SelectGroup>
          </SelectContent>
        </Select>
        <Select v-model="original">
          <SelectTrigger aria-label="원곡 아티스트" class="min-w-36">
            <SelectValue placeholder="원곡 아티스트" />
          </SelectTrigger>
          <SelectContent>
            <SelectGroup>
              <SelectItem value="all">원곡 아티스트 전체</SelectItem>
              <SelectItem v-for="[name, ko] in originals" :key="name" :value="name">
                {{ displayName(name, ko) }}
              </SelectItem>
            </SelectGroup>
          </SelectContent>
        </Select>
        <BroadcastPeriodFilter :start="start" :end="end" @apply="applyPeriod" />
        <Button
          v-if="selectedPerformers.length || start || end"
          variant="ghost"
          @click="clearFilters"
        >
          필터 초기화
        </Button>
      </div>
      <p v-if="invalidRange" role="alert" class="mb-4 text-sm text-destructive">
        시작일은 종료일보다 늦을 수 없어요.
      </p>
    </div>
    <ResourceState
      v-if="query.trim() || scope.artistId"
      :loading="loading"
      :error="error"
      :empty="!data || (!data.artists.length && !data.performances.length)"
      title="검색 결과가 없어요"
      :description="query ? '다른 이름이나 원곡 아티스트로 검색해 보세요.' : undefined"
      @retry="reload"
    >
      <section v-if="data?.artists.length" class="search-section">
        <div class="section-heading">
          <h2>
            아티스트
            <span>{{ data.artists.length }}</span>
          </h2>
        </div>
        <div class="search-artist-grid">
          <ArtistTile v-for="a in data.artists" :key="a.id" :artist="a" compact />
        </div>
      </section>
      <section v-if="data?.performances.length" class="search-section">
        <div class="section-heading">
          <h2>
            세트리스트
            <span>
              {{ original === 'all' ? (data?.total ?? performances.length) : performances.length }}
            </span>
          </h2>
        </div>
        <p v-if="singersError" role="alert" class="mb-4 text-sm text-destructive">
          부른 아티스트 목록을 불러오지 못했어요.
          <Button variant="ghost" size="sm" @click="reloadSingers">다시 시도</Button>
        </p>
        <ResourceState
          :empty="!performances.length"
          title="선택한 조건의 노래가 없어요"
          description="아티스트 필터를 바꿔보세요."
        >
          <p v-if="data?.limited" class="text-sm text-muted-foreground mb-4">
            검색 결과가 많아 일부만 표시합니다. 더 구체적인 곡명이나 아티스트명으로 검색해 주세요.
          </p>
          <div class="performance-results">
            <RouterLink
              v-for="p in performances"
              :key="p.id"
              :to="{
                path: `/lives/${p.live.id}`,
                query: { t: String(p.start_seconds) },
                state: { liveReturnTo: route.fullPath },
              }"
              class="performance-result"
            >
              <ArchiveThumbnail :video-id="p.live.video_id" />
              <div class="performance-song">
                <h3 class="performance-title truncate">
                  {{ displayName(p.song_title, p.song_title_ko) }}
                </h3>
                <p v-if="p.original_artist.trim()" class="performance-original truncate">
                  {{ displayName(p.original_artist, p.original_artist_ko) }}
                </p>
                <p class="performance-singer">
                  <span>{{ displayName(p.artist.name, p.artist.display_name) }}</span>
                  <span class="performance-mobile-date">
                    · {{ formatDate(p.live.broadcast_at) }}
                  </span>
                </p>
              </div>
              <div class="performance-context">
                <p>{{ p.live.title_ko || p.live.title }}</p>
                <time :datetime="p.live.broadcast_at">{{ formatDate(p.live.broadcast_at) }}</time>
              </div>
              <ChevronRight class="size-4 result-arrow" aria-hidden="true" />
            </RouterLink>
          </div>
        </ResourceState>
        <Button
          v-if="(data?.total ?? 0) > results.length"
          variant="outline"
          class="mx-auto mt-6 flex"
          :disabled="moreLoading"
          @click="loadMore"
        >
          검색 결과 더 보기
        </Button>
        <p v-if="moreError" role="alert" class="mt-3 text-sm text-destructive">{{ moreError }}</p>
      </section>
    </ResourceState>
  </div>
</template>
