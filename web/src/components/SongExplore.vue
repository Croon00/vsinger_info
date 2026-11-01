<script setup lang="ts">
import { computed, nextTick, onScopeDispose, ref, shallowRef, watch } from 'vue'
import { useRoute, useRouter, RouterLink } from 'vue-router'
import { Search, ChevronDown, ArrowUpRight, Music2 } from '@lucide/vue'
import { api } from '@/api/client'
import type { ExploredSong, SongKind } from '@/api/types'
import { useResource } from '@/composables/useResource'
import { formatSubscribers } from '@/lib/subscribers'
import { formatDate } from '@/lib/dates'
import { displayName } from '@/lib/display-name'
import { Button } from '@/components/ui/button'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { InputGroup, InputGroupInput, InputGroupAddon } from '@/components/ui/input-group'
import ResourceState from '@/components/ResourceState.vue'
import SongVideoDialog from '@/components/SongVideoDialog.vue'
import BroadcastPeriodFilter from '@/components/BroadcastPeriodFilter.vue'
const route = useRoute()
const router = useRouter()
const kind = computed<SongKind>(() =>
  ['utawaku', 'cover', 'original'].includes(String(route.query.kind))
    ? (route.query.kind as SongKind)
    : 'utawaku',
)
const agency = computed(() => String(route.query.song_agency ?? 'all'))
const order = computed(() =>
  ['high', 'low', 'latest', 'name'].includes(String(route.query.song_order))
    ? String(route.query.song_order)
    : 'high',
)
const query = ref(String(route.query.song_q ?? ''))
const period = computed(() =>
  kind.value === 'utawaku'
    ? {}
    : {
        start: typeof route.query.song_start === 'string' ? route.query.song_start : undefined,
        end: typeof route.query.song_end === 'string' ? route.query.song_end : undefined,
      },
)
function applyPeriod(value: { start: string; end: string }) {
  const next = { ...route.query }
  if (value.start) next.song_start = value.start
  else delete next.song_start
  if (value.end) next.song_end = value.end
  else delete next.song_end
  router.replace({ query: next })
}
function update(key: string, value: string | number) {
  const next = { ...route.query, [key]: value }
  if (key === 'song_agency' || key === 'kind') delete next.song_artists
  router.replace({ query: next })
}
const selectedArtists = computed(() => [
  ...new Set(
    (Array.isArray(route.query.song_artists)
      ? route.query.song_artists
      : [route.query.song_artists]
    ).filter((id): id is string => typeof id === 'string' && /^[1-9]\d*$/.test(id)),
  ),
])
function selectArtists(value: unknown) {
  const ids = Array.isArray(value) ? value.map(String) : []
  const next = { ...route.query }
  if (!ids.length || ids.includes('all')) delete next.song_artists
  else next.song_artists = ids
  router.replace({ query: next })
}
const {
  data: artistCatalog,
  error: artistsError,
  reload: reloadArtists,
} = useResource((signal) => api.artists(signal))
const artistOptions = computed(() =>
  [...new Map((artistCatalog.value ?? []).map((artist) => {
    const group = kind.value === 'original' ? artist.original_song_group : null
    const option = group
      ? { ...artist, id: group.id, name: group.name, display_name: '', agency: group.agency ?? '' }
      : artist
    return [option.id, option] as const
  })).values()]
    .filter(
      (a) =>
        agency.value === 'all' ||
        (agency.value === 'independent' ? !a.agency : a.agency === agency.value),
    )
    .slice()
    .sort((a, b) =>
      displayName(a.name, a.display_name).localeCompare(displayName(b.name, b.display_name), 'ko'),
    ),
)
let timer: ReturnType<typeof setTimeout> | undefined
watch(query, (value) => {
  clearTimeout(timer)
  timer = setTimeout(() => update('song_q', value), 250)
})
watch(
  () => route.query.song_q,
  (value) => {
    query.value = String(value ?? '')
  },
)
const extra = ref<ExploredSong[]>([])
const moreLoading = ref(false)
const moreError = ref('')
let moreController: AbortController | undefined
const { data, loading, error, reload } = useResource(
  async (signal) => {
    const page = await api.songPage(
      kind.value,
      agency.value,
      String(route.query.song_q ?? ''),
      order.value,
      0,
      signal,
      selectedArtists.value.map(Number),
      period.value,
    )
    return { page }
  },
  [kind, agency, order, () => route.query.song_q, selectedArtists, period],
)
watch(data, () => {
  moreController?.abort()
  extra.value = []
  moreError.value = ''
  moreLoading.value = false
})
onScopeDispose(() => {
  clearTimeout(timer)
  moreController?.abort()
})
const agencies = computed(() =>
  [...new Set((artistCatalog.value ?? []).map((a) => a.agency).filter(Boolean))].sort(),
)
const songs = computed(() => [...(data.value?.page.items ?? []), ...extra.value])
const playingSong = shallowRef<ExploredSong | null>(null)
let playerTrigger: HTMLElement | null = null
function openPlayer(song: ExploredSong, event: MouseEvent) {
  if (!videoUrl(song)) return
  playerTrigger = event.currentTarget as HTMLElement
  playingSong.value = song
}
function closePlayer() {
  playingSong.value = null
  nextTick(() => {
    if (playerTrigger?.isConnected) playerTrigger.focus()
  })
}
watch([kind, agency, order, () => route.query.song_q, selectedArtists, period], () => {
  playingSong.value = null
})
async function loadMore() {
  if (moreLoading.value) return
  const current = data.value
  const controller = new AbortController()
  moreController = controller
  moreLoading.value = true
  moreError.value = ''
  try {
    const page = await api.songPage(
      kind.value,
      agency.value,
      String(route.query.song_q ?? ''),
      order.value,
      songs.value.length,
      controller.signal,
      selectedArtists.value.map(Number),
      period.value,
    )
    if (!controller.signal.aborted && data.value === current) extra.value.push(...page.items)
  } catch (e) {
    if (!controller.signal.aborted)
      moreError.value = e instanceof Error ? e.message : '곡을 불러오지 못했어요.'
  } finally {
    if (controller === moreController) moreLoading.value = false
  }
}
function videoUrl(song: ExploredSong) {
  return /^[A-Za-z0-9_-]{11}$/.test(song.youtube_video_id ?? '')
    ? `https://www.youtube.com/watch?v=${song.youtube_video_id}`
    : undefined
}
</script>
<template>
  <section aria-label="곡 탐색 목록">
    <Tabs :model-value="kind" @update:model-value="(value) => update('kind', value)">
      <TabsList variant="line" class="mb-6 max-w-full">
        <TabsTrigger value="utawaku">우타와꾸 곡</TabsTrigger>
        <TabsTrigger value="cover">커버 곡</TabsTrigger>
        <TabsTrigger value="original">오리지널 곡</TabsTrigger>
      </TabsList>
    </Tabs>
    <div class="explore-toolbar">
      <div class="explore-filters song-explore-filters">
        <Select :model-value="agency" @update:model-value="(v) => update('song_agency', String(v))">
          <SelectTrigger class="explore-filter" aria-label="곡 소속사 필터">
            <SelectValue placeholder="소속사 전체" />
          </SelectTrigger>
          <SelectContent>
            <SelectGroup>
              <SelectItem value="all">소속사 전체</SelectItem>
              <SelectItem value="independent">개인세</SelectItem>
              <SelectItem v-for="name in agencies" :key="name" :value="name">{{ name }}</SelectItem>
            </SelectGroup>
          </SelectContent>
        </Select>
        <Select :model-value="selectedArtists" multiple @update:model-value="selectArtists">
          <SelectTrigger class="explore-filter" aria-label="곡 아티스트 필터">
            <SelectValue>
              {{
                selectedArtists.length
                  ? `아티스트 ${selectedArtists.length}명 선택`
                  : '아티스트 전체'
              }}
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            <SelectGroup>
              <SelectItem value="all">아티스트 전체</SelectItem>
              <SelectItem
                v-for="artist in artistOptions"
                :key="artist.id"
                :value="String(artist.id)"
              >
                {{ displayName(artist.name, artist.display_name) }}
              </SelectItem>
            </SelectGroup>
          </SelectContent>
        </Select>
        <Select
          :key="kind"
          :model-value="order"
          @update:model-value="(v) => update('song_order', String(v))"
        >
          <SelectTrigger class="explore-filter" aria-label="곡 정렬 기준">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectGroup>
              <SelectItem value="high">
                {{ kind === 'utawaku' ? '부른 횟수 높은 순' : '조회수 높은 순' }}
              </SelectItem>
              <SelectItem value="low">
                {{ kind === 'utawaku' ? '부른 횟수 낮은 순' : '조회수 낮은 순' }}
              </SelectItem>
              <SelectItem value="latest">
                {{ kind === 'utawaku' ? '최근 부른 순' : '최신 영상 순' }}
              </SelectItem>
              <SelectItem value="name">곡 이름 순</SelectItem>
            </SelectGroup>
          </SelectContent>
        </Select>
        <BroadcastPeriodFilter
          v-if="kind !== 'utawaku'"
          title="영상 등록 기간"
          :start="period.start"
          :end="period.end"
          @apply="applyPeriod"
        />
      </div>
      <form
        class="explore-search"
        role="search"
        aria-label="곡 검색"
        @submit.prevent="update('song_q', query)"
      >
        <InputGroup class="h-11">
          <InputGroupAddon><Search /></InputGroupAddon>
          <InputGroupInput
            v-model="query"
            aria-label="곡 또는 아티스트 이름"
            placeholder="곡 또는 아티스트 이름으로 찾기"
          />
        </InputGroup>
      </form>
      <p class="result-count" aria-live="polite">
        {{ data?.page.total.toLocaleString('ko-KR') ?? '…'
        }}{{ kind === 'cover' ? '개의 커버 영상' : '개의 곡' }} ·
        {{ kind === 'utawaku' ? '수집된 세트리스트 기준' : 'YouTube 조회수 · 미확인은 마지막' }}
      </p>
    </div>
    <p v-if="artistsError" role="alert" class="mb-4 text-sm text-destructive">
      아티스트 목록을 불러오지 못했어요.
      <Button variant="ghost" size="sm" @click="reloadArtists">다시 시도</Button>
    </p>
    <p v-if="kind === 'cover'" class="mb-5 text-xs text-muted-foreground">
      Shorts 제외 · 짧은 영상은 일반 영상으로 확인된 뒤 표시됩니다.
    </p>
    <p v-if="kind === 'original'" class="mb-5 text-xs text-muted-foreground">
      등록된 발매곡 기준이며, 커버 여부가 확인되지 않은 곡이 포함될 수 있어요.
    </p>
    <ResourceState
      :loading="loading"
      :error="error"
      :empty="!songs.length"
      title="조건에 맞는 곡이 없습니다"
      @retry="reload"
    >
      <div class="song-explore-list">
        <article v-for="(song, index) in songs" :key="song.key" class="song-explore-row">
          <span class="song-rank">{{ index + 1 }}</span>
          <a
            v-if="videoUrl(song)"
            :href="videoUrl(song)"
            target="_blank"
            rel="noopener noreferrer"
            class="song-explore-thumb"
            :aria-label="`${song.title} YouTube에서 보기`"
          >
            <img
              :src="`https://i.ytimg.com/vi/${song.youtube_video_id}/mqdefault.jpg`"
              alt=""
              loading="lazy"
              width="320"
              height="180"
            />
          </a>
          <div v-else class="song-explore-thumb song-explore-placeholder">
            <Music2 aria-hidden="true" />
          </div>
          <div class="song-explore-copy">
            <h3>
              <button
                v-if="kind !== 'utawaku' && videoUrl(song)"
                type="button"
                class="song-title-button"
                aria-haspopup="dialog"
                @click="openPlayer(song, $event)"
              >
                {{ song.title_ko || song.title }}
              </button>
              <template v-else>{{ song.title_ko || song.title }}</template>
            </h3>
            <p v-if="song.title_ko">{{ song.title }}</p>
            <p>{{ song.artist_name || '아티스트 미확인' }}</p>
          </div>
          <div class="song-explore-metric">
            <strong>
              {{
                kind === 'utawaku'
                  ? `${song.performance_count?.toLocaleString('ko-KR')}회`
                  : song.view_count == null
                    ? '—'
                    : `${formatSubscribers(song.view_count)}회`
              }}
            </strong>
            <span>
              {{ kind === 'utawaku' ? `${song.artist_count}명의 아티스트` : 'YouTube 조회수' }}
            </span>
            <span v-if="kind !== 'utawaku' && song.published_at" :title="song.published_at">
              {{ formatDate(song.published_at) }} 등록
            </span>
          </div>
          <Button v-if="kind === 'utawaku'" as-child variant="outline" size="sm">
            <RouterLink
              :to="{
                path: '/search',
                query: {
                  q: song.title,
                  song_key: song.key,
                  agency,
                  artist_ids: selectedArtists.length ? selectedArtists : undefined,
                },
              }"
            >
              리스트 열기
            </RouterLink>
          </Button>
          <Button v-else-if="videoUrl(song)" as-child variant="ghost" size="icon-sm">
            <a
              :href="videoUrl(song)"
              target="_blank"
              rel="noopener noreferrer"
              :aria-label="`${song.title} YouTube에서 보기`"
            >
              <ArrowUpRight />
            </a>
          </Button>
        </article>
      </div>
      <Button
        v-if="(data?.page.total ?? 0) > songs.length"
        class="mx-auto mt-8 flex"
        variant="outline"
        :disabled="moreLoading"
        @click="loadMore"
      >
        더보기
        <ChevronDown data-icon="inline-end" />
      </Button>
      <p v-if="moreError" role="alert" class="mt-3 text-sm text-destructive">{{ moreError }}</p>
    </ResourceState>
    <SongVideoDialog :song="playingSong" @close="closePlayer" />
  </section>
</template>
