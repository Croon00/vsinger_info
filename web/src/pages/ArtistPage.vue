<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useMediaQuery } from '@vueuse/core'
import { useRoute, useRouter } from 'vue-router'
import {
  ArrowLeft,
  ArrowUpRight,
  Play,
  Disc3,
  CalendarDays,
  ListMusic,
  ChevronDown,
  FileText,
  ChartNoAxesColumnIncreasing,
} from '@lucide/vue'
import { api } from '@/api/client'
import type { Live } from '@/api/types'
import { useResource } from '@/composables/useResource'
import ArtistAvatar from '@/components/ArtistAvatar.vue'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { formatDate, todayKey } from '@/lib/dates'
import { openOverlay } from '@/lib/overlays'
import AlbumCover from '@/components/AlbumCover.vue'
import FavoriteButton from '@/components/FavoriteButton.vue'
import LiveCard from '@/components/LiveCard.vue'
import ResourceState from '@/components/ResourceState.vue'
import ConcertRow from '@/components/ConcertRow.vue'
import ArtistStatistics from '@/components/ArtistStatistics.vue'
const route = useRoute()
const router = useRouter()
const mobile = useMediaQuery('(max-width: 768px)')
const id = computed(() => String(route.params.artistId))
const tab = computed(() =>
  ['lives', 'statistics', 'originals', 'concerts'].includes(String(route.query.tab))
    ? String(route.query.tab)
    : 'lives',
)
const selectedAlbum = ref('')
const extraLives = ref<Live[]>([])
const moreLoading = ref(false)
const moreError = ref('')
watch(id, () => {
  selectedAlbum.value = ''
  extraLives.value = []
  moreLoading.value = false
  moreError.value = ''
})
const {
  data: profile,
  loading,
  error,
  reload,
} = useResource((signal) => api.artist(id.value, signal), [id])
const {
  data: liveData,
  loading: livesLoading,
  error: livesError,
  reload: reloadLives,
} = useResource(
  (signal) =>
    tab.value === 'lives' ? api.livePage(Number(id.value), 0, 6, signal) : Promise.resolve(null),
  [id, () => tab.value === 'lives'],
)
watch(liveData, () => {
  extraLives.value = []
  moreError.value = ''
})
const {
  data: stats,
  loading: statsLoading,
  error: statsError,
  reload: reloadStats,
} = useResource(
  (signal) =>
    tab.value === 'statistics' ? api.statistics(Number(id.value), signal) : Promise.resolve(null),
  [id, () => tab.value === 'statistics'],
)
async function loadMore() {
  if (moreLoading.value) return
  const artistId = id.value
  const initial = liveData.value
  moreLoading.value = true
  moreError.value = ''
  try {
    const result = await api.livePage(
      Number(artistId),
      (initial?.items.length ?? 0) + extraLives.value.length,
      6,
    )
    if (id.value === artistId && liveData.value === initial) extraLives.value.push(...result.items)
  } catch (e) {
    if (id.value === artistId)
      moreError.value = e instanceof Error ? e.message : '불러오지 못했어요.'
  } finally {
    if (id.value === artistId) moreLoading.value = false
  }
}
const {
  data: albumData,
  loading: albumsLoading,
  error: albumsError,
  reload: reloadAlbums,
} = useResource(
  (signal) =>
    tab.value === 'originals' ? api.albums(Number(id.value), signal) : Promise.resolve(null),
  [id, () => tab.value === 'originals'],
)
const {
  data: concertData,
  loading: concertsLoading,
  error: concertsError,
  reload: reloadConcerts,
} = useResource(
  (signal) =>
    tab.value === 'concerts'
      ? api.concerts(signal, { artistId: Number(id.value) })
      : Promise.resolve(null),
  [id, () => tab.value === 'concerts'],
)
const data = computed(() =>
  profile.value
    ? {
        artist: profile.value,
        lives: [...(liveData.value?.items ?? []), ...extraLives.value],
        albums: albumData.value ?? [],
        concerts: (concertData.value ?? []).filter((c) =>
          (profile.value?.related_artist_ids ?? [Number(id.value)]).includes(c.artist_id),
        ),
      }
    : null,
)
const albumSummary = computed(
  () => data.value?.albums.find((a) => a.id === selectedAlbum.value) ?? data.value?.albums[0],
)
const {
  data: album,
  loading: tracksLoading,
  error: tracksError,
  reload: reloadTracks,
} = useResource(
  (signal) =>
    !albumSummary.value
      ? Promise.resolve(null)
      : albumSummary.value.tracks_loaded === false
        ? api.album(albumSummary.value.id, Number(id.value), signal)
        : Promise.resolve(albumSummary.value),
  [id, () => albumSummary.value?.id],
)
const upcoming = computed(() =>
  (data.value?.concerts ?? [])
    .filter((c) => !c.starts_at || c.starts_at.slice(0, 10) >= todayKey())
    .sort((a, b) => a.starts_at.localeCompare(b.starts_at)),
)
const past = computed(() =>
  (data.value?.concerts ?? [])
    .filter((c) => !!c.starts_at && c.starts_at.slice(0, 10) < todayKey())
    .sort((a, b) => b.starts_at.localeCompare(a.starts_at)),
)
function changeTab(value: string | number) {
  router.push({
    query: { ...route.query, tab: String(value), event: undefined, lyrics: undefined },
  })
}
</script>
<template>
  <div class="page-container artist-page page-enter">
    <Button as-child variant="ghost" class="back-link">
      <RouterLink to="/explore">
        <ArrowLeft data-icon="inline-start" />
        모든 아티스트
      </RouterLink>
    </Button>
    <ResourceState :loading="loading" :error="error" @retry="reload">
      <template v-if="data">
        <section class="artist-profile">
          <ArtistAvatar :artist="data.artist" class="profile-avatar" />
          <div class="profile-copy">
            <p class="eyebrow">{{ data.artist.agency }}</p>
            <div class="profile-name">
              <h1>{{ data.artist.name }}</h1>
              <FavoriteButton :id="data.artist.id" :name="data.artist.name" />
            </div>
            <p v-if="data.artist.display_name" class="profile-reading">
              {{ data.artist.display_name }}
            </p>
            <div class="profile-links">
              <Button
                v-for="link in data.artist.links"
                :key="link.url"
                as-child
                variant="outline"
                size="sm"
              >
                <a :href="link.url" target="_blank" rel="noopener noreferrer">
                  {{ link.label }}
                  <ArrowUpRight data-icon="inline-end" />
                </a>
              </Button>
            </div>
          </div>
        </section>
        <Tabs :model-value="tab" @update:model-value="changeTab" class="artist-tabs">
          <TabsList variant="line" class="h-13">
            <TabsTrigger value="lives">
              <Play />
              라이브
              <span v-if="liveData || stats" class="tab-count">
                {{ liveData?.total ?? stats?.archives }}
              </span>
            </TabsTrigger>
            <TabsTrigger value="statistics">
              <ChartNoAxesColumnIncreasing />
              통계
            </TabsTrigger>
            <TabsTrigger value="originals">
              <Disc3 />
              오리곡
            </TabsTrigger>
            <TabsTrigger value="concerts">
              <CalendarDays />
              공연 정보
            </TabsTrigger>
          </TabsList>
          <TabsContent value="lives" class="pt-4 min-[769px]:pt-6">
            <div class="section-heading">
              <div>
                <h2>라이브 아카이브</h2>
              </div>
              <span class="text-xs text-muted-foreground">최신순</span>
            </div>
            <ResourceState
              :loading="livesLoading"
              :error="livesError"
              @retry="reloadLives"
              :empty="!data.lives.length"
              title="등록된 라이브가 없습니다"
              description="공식 채널에서 영상을 확인할 수 있습니다."
            >
              <template #action>
                <Button
                  v-if="
                    data.artist.links.find((l) => l.label === 'YouTube')?.url ||
                    data.artist.official_url
                  "
                  as-child
                  variant="outline"
                >
                  <a
                    :href="
                      data.artist.links.find((l) => l.label === 'YouTube')?.url ||
                      data.artist.official_url
                    "
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    공식 채널에서 보기
                    <ArrowUpRight data-icon="inline-end" />
                  </a>
                </Button>
              </template>
              <div class="live-grid">
                <LiveCard v-for="live in data.lives" :key="live.id" :live="live" />
              </div>
              <Button
                v-if="(liveData?.total ?? 0) > data.lives.length"
                variant="outline"
                class="mx-auto mt-8 flex"
                :disabled="moreLoading"
                @click="loadMore"
              >
                라이브 더 보기
                <ChevronDown data-icon="inline-end" />
              </Button>
              <p v-if="moreError" role="alert" class="text-sm text-destructive mt-3">
                {{ moreError }}
              </p>
            </ResourceState>
          </TabsContent>
          <TabsContent value="statistics" class="pt-4 min-[769px]:pt-6">
            <ResourceState :loading="statsLoading" :error="statsError" @retry="reloadStats">
              <ArtistStatistics v-if="stats" :key="id" :lives="[]" :summary="stats" />
            </ResourceState>
          </TabsContent>
          <TabsContent value="originals" class="pt-4 min-[769px]:pt-6">
            <div class="section-heading">
              <div>
                <h2>디스코그래피</h2>
              </div>
            </div>
            <ResourceState
              :loading="albumsLoading"
              :error="albumsError"
              @retry="reloadAlbums"
              :empty="!data.albums.length"
              title="등록된 앨범이 없습니다"
            >
              <div class="discography-layout">
                <ToggleGroup
                  :key="mobile ? 'horizontal' : 'vertical'"
                  type="single"
                  :orientation="mobile ? 'horizontal' : 'vertical'"
                  :model-value="albumSummary?.id"
                  @update:model-value="
                    (v) => {
                      if (v) selectedAlbum = String(v)
                    }
                  "
                  :spacing="2"
                  variant="outline"
                  class="album-grid"
                  aria-label="앨범 선택"
                >
                  <ToggleGroupItem
                    v-for="a in data.albums"
                    :key="a.id"
                    class="album-card"
                    :value="a.id"
                  >
                    <AlbumCover :src="a.image_url" :title="a.name" />
                    <div class="album-copy">
                      <h3>{{ a.name }}</h3>
                      <p>
                        {{ a.release_date.slice(0, 4) }}
                        <span>·</span>
                        {{ ({ album: 'Album', single: 'Single', ep: 'EP', compilation: 'Compilation', other: 'Release' })[a.album_type] }}
                      </p>
                    </div>
                  </ToggleGroupItem>
                </ToggleGroup>
                <ResourceState :loading="tracksLoading" :error="tracksError" @retry="reloadTracks">
                  <section v-if="album" class="track-section">
                    <div class="section-heading">
                      <div>
                        <h2>{{ album.name }}</h2>
                        <p>{{ formatDate(album.release_date) }} · {{ album.tracks.length }}곡</p>
                      </div>
                      <Button v-if="album.source_url" as-child variant="outline" size="sm">
                        <a :href="album.source_url" target="_blank" rel="noopener noreferrer">
                          공식 릴리스
                          <ArrowUpRight data-icon="inline-end" />
                        </a>
                      </Button>
                    </div>
                    <div v-for="(track, index) in album.tracks" :key="track.id" class="track-row">
                      <span class="track-number">{{ String(index + 1).padStart(2, '0') }}</span>
                      <div>
                        <h3>{{ track.title }}</h3>
                        <p>{{ track.title_ko || data.artist.name }}</p>
                      </div>
                      <span class="track-duration">{{ track.duration }}</span>
                      <Button
                        variant="ghost"
                        size="sm"
                        :disabled="!track.has_lyrics"
                        @click="
                          openOverlay(router, route, 'lyrics', track.lyrics_id ?? track.song_id ?? Number(track.id))
                        "
                      >
                        <FileText data-icon="inline-start" />
                        {{ track.has_lyrics ? '가사' : '가사 없음' }}
                      </Button>
                    </div>
                  </section>
                </ResourceState>
              </div>
            </ResourceState>
          </TabsContent>
          <TabsContent value="concerts" class="pt-4 min-[769px]:pt-6">
            <ResourceState
              :loading="concertsLoading"
              :error="concertsError"
              @retry="reloadConcerts"
            >
              <section>
                <div class="section-heading">
                  <div>
                    <h2>예정된 공연</h2>
                  </div>
                </div>
                <ResourceState :empty="!upcoming.length" title="예정된 공연이 없어요">
                  <div class="concert-list">
                    <ConcertRow v-for="c in upcoming" :key="c.id" :concert="c" />
                  </div>
                </ResourceState>
              </section>
              <section class="past-concerts">
                <div class="section-heading">
                  <div>
                    <h2>지난 공연</h2>
                  </div>
                </div>
                <ResourceState :empty="!past.length" title="지난 공연 기록이 없어요">
                  <div class="concert-timeline">
                    <div v-for="(c, index) in past" :key="c.id" class="timeline-item">
                      <h3
                        v-if="
                          index === 0 ||
                          c.starts_at.slice(0, 4) !== past[index - 1]?.starts_at.slice(0, 4)
                        "
                        class="timeline-year"
                      >
                        {{ c.starts_at.slice(0, 4) }}
                      </h3>
                      <ConcertRow :concert="c" past />
                    </div>
                  </div>
                </ResourceState>
              </section>
            </ResourceState>
          </TabsContent>
        </Tabs>
      </template>
    </ResourceState>
  </div>
</template>
