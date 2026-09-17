<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ChevronRight } from '@lucide/vue'
import { api } from '@/api/client'
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
function koreanName(original: string, korean?: string) {
  // Latin-only original names are already the display name; aliases remain searchable.
  if (
    !korean?.trim() ||
    korean === original ||
    /^[\p{Script=Latin}\p{N}\p{P}\p{Z}\p{S}]+$/u.test(original)
  )
    return ''
  return korean
}
</script>
<template>
  <div class="page-container page-enter">
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
              <ArchiveThumbnail :video-id="p.live.video_id" />
              <div class="performance-song">
                <h3 class="performance-title">
                  <span>
                    {{ p.song_title }}
                    <span
                      v-if="koreanName(p.song_title, p.song_title_ko)"
                      class="performance-korean"
                    >
                      ({{ p.song_title_ko }})
                    </span>
                  </span>
                  <span class="performance-divider">{{ ' – ' }}</span>
                  <span class="performance-original">
                    {{ p.original_artist }}
                    <span
                      v-if="koreanName(p.original_artist, p.original_artist_ko)"
                      class="performance-korean"
                    >
                      ({{ p.original_artist_ko }})
                    </span>
                  </span>
                </h3>
                <p class="performance-singer">
                  <span>
                    {{ p.artist.name }}
                    <span
                      v-if="koreanName(p.artist.name, p.artist.display_name)"
                      class="performance-korean"
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
      </section>
    </ResourceState>
  </div>
</template>
