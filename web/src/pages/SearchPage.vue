<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ChevronRight } from '@lucide/vue'
import { api } from '@/api/client'
import type { SearchPerformance } from '@/api/types'
import { Button } from '@/components/ui/button'
import { useResource } from '@/composables/useResource'
import { formatDate } from '@/lib/dates'
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
const performer = ref('all')
const original = ref('all')
const extra = ref<SearchPerformance[]>([])
const moreLoading = ref(false)
const moreError = ref('')
const { data, loading, error, reload } = useResource(
  (signal) => api.search(query.value, signal),
  [query],
)
watch(data, () => {
  extra.value = []
  moreError.value = ''
})
const results = computed(() => [...(data.value?.performances ?? []), ...extra.value])
async function loadMore() {
  if (moreLoading.value) return
  const initial = data.value
  moreLoading.value = true
  moreError.value = ''
  try {
    const result = await api.search(query.value, undefined, results.value.length)
    if (data.value === initial) {
      const known = new Set(results.value.map((p) => p.id))
      extra.value.push(...result.performances.filter((p) => !known.has(p.id)))
    }
  } catch (e) {
    if (data.value === initial)
      moreError.value = e instanceof Error ? e.message : '불러오지 못했어요.'
  } finally {
    moreLoading.value = false
  }
}
watch(query, () => {
  performer.value = 'all'
  original.value = 'all'
})
const singers = computed(() => [
  ...new Map(results.value.map((p) => [p.artist.id ?? p.artist.name, p.artist])).values(),
])
const originals = computed(() => [...new Set(results.value.map((p) => p.original_artist))])
const performances = computed(() =>
  results.value.filter(
    (p) =>
      (performer.value === 'all' || String(p.artist.id ?? p.artist.name) === performer.value) &&
      (original.value === 'all' || p.original_artist === original.value),
  ),
)
function search(q: string) {
  router.push({ path: '/search', query: { q } })
}
function koreanName(original: string, korean?: string) {
  return korean?.trim() && korean !== original ? korean : ''
}
</script>
<template>
  <div class="page-container search-page page-enter">
    <div class="page-heading">
      <h1>검색 결과</h1>
      <p>아티스트 이름, 원곡명, 원곡 아티스트로 라이브 속 노래를 찾아보세요.</p>
    </div>
    <SearchForm :initial="query" @search="search" />
    <ResourceState
      :loading="loading"
      :error="error"
      :empty="!data || (!data.artists.length && !data.performances.length)"
      :title="query ? '검색 결과가 없어요' : '어떤 노래를 찾고 있나요?'"
      :description="
        query
          ? '다른 이름이나 원곡 아티스트로 검색해 보세요.'
          : '예를 들어 HACHI, 晴る, 요루시카를 검색해 보세요.'
      "
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
            <span>{{ performances.length }}</span>
          </h2>
          <div class="search-filters">
            <Select v-model="performer">
              <SelectTrigger aria-label="부른 아티스트" class="min-w-36">
                <SelectValue placeholder="부른 아티스트" />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  <SelectItem value="all">부른 아티스트 전체</SelectItem>
                  <SelectItem
                    v-for="a in singers"
                    :key="a.id ?? a.name"
                    :value="String(a.id ?? a.name)"
                  >
                    {{ a.name }}
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
                  <SelectItem v-for="name in originals" :key="name" :value="name">
                    {{ name }}
                  </SelectItem>
                </SelectGroup>
              </SelectContent>
            </Select>
          </div>
        </div>
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
              :to="`/lives/${p.live.id}?t=${p.start_seconds}`"
              class="performance-result"
            >
              <ArchiveThumbnail :video-id="p.live.video_id" />
              <div class="performance-song">
                <h3 class="performance-title truncate">
                  {{ p.song_title }} － {{ p.original_artist }}
                </h3>
                <p class="performance-translation truncate">
                  {{ p.song_title_ko || p.song_title }} -
                  {{ p.original_artist_ko || p.original_artist }}
                </p>
                <p class="performance-singer">
                  <span>
                    {{ p.artist.name }}
                    <span
                      v-if="koreanName(p.artist.name, p.artist.display_name)"
                      class="performance-korean performance-singer-reading"
                    >
                      ({{ p.artist.display_name }})
                    </span>
                  </span>
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
