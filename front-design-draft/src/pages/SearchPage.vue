<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowUpRight, Play, ListMusic } from '@lucide/vue'
import { api } from '@/api/client'
import { useResource } from '@/composables/useResource'
import { formatDate, formatTime } from '@/lib/dates'
import { Button } from '@/components/ui/button'
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
import ResourceState from '@/components/ResourceState.vue'
const route = useRoute()
const router = useRouter()
const query = computed(() => String(route.query.q ?? ''))
const performer = ref('all')
const original = ref('all')
const { data, loading, error, reload } = useResource(
  (signal) => api.search(query.value, signal),
  [query],
)
watch(query, () => {
  performer.value = 'all'
  original.value = 'all'
})
const singers = computed(() => [
  ...new Map((data.value?.performances ?? []).map((p) => [p.artist.id, p.artist])).values(),
])
const originals = computed(() => [
  ...new Set((data.value?.performances ?? []).map((p) => p.original_artist)),
])
const performances = computed(() =>
  (data.value?.performances ?? []).filter(
    (p) =>
      (performer.value === 'all' || String(p.artist.id) === performer.value) &&
      (original.value === 'all' || p.original_artist === original.value),
  ),
)
function search(q: string) {
  router.push({ path: '/search', query: { q } })
}
</script>
<template>
  <div class="page-container page-enter">
    <div class="page-heading">
      <p class="eyebrow">FIND THAT VOICE, FIND THAT SONG</p>
      <h1>마음에 남은 그 노래.</h1>
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
                  <SelectItem v-for="a in singers" :key="a.id" :value="String(a.id)">
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
          <div class="performance-results">
            <RouterLink
              v-for="p in performances"
              :key="p.id"
              :to="`/lives/${p.live.id}?t=${p.start_seconds}`"
              class="performance-result"
            >
              <div class="performance-art">
                <img :src="p.artist.image" :alt="p.artist.name" />
                <span><Play class="size-4" /></span>
              </div>
              <div class="performance-song">
                <h3>{{ p.song_title }}</h3>
                <p>
                  {{ p.original_artist }}
                  <span v-if="p.original_artist_ko">· {{ p.original_artist_ko }}</span>
                </p>
              </div>
              <div class="performance-context">
                <span>{{ p.artist.name }}</span>
                <p>{{ p.live.title_ko }}</p>
                <small>{{ formatDate(p.live.broadcast_at) }}</small>
              </div>
              <span class="timestamp">
                <Play class="size-3" />
                {{ formatTime(p.start_seconds) }}
              </span>
              <ArrowUpRight class="size-4 result-arrow" />
            </RouterLink>
          </div>
        </ResourceState>
      </section>
    </ResourceState>
  </div>
</template>
