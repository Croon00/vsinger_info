<script setup lang="ts">
import { computed, ref, watch } from 'vue'
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
} from '@lucide/vue'
import { api } from '@/api/client'
import { useResource } from '@/composables/useResource'
import { Avatar, AvatarImage, AvatarFallback } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { formatDate, todayKey } from '@/lib/dates'
import { openOverlay } from '@/lib/overlays'
import AlbumCover from '@/components/AlbumCover.vue'
import FavoriteButton from '@/components/FavoriteButton.vue'
import LiveCard from '@/components/LiveCard.vue'
import ResourceState from '@/components/ResourceState.vue'
import ConcertRow from '@/components/ConcertRow.vue'
const route = useRoute()
const router = useRouter()
const id = computed(() => String(route.params.artistId))
const tab = computed(() =>
  ['lives', 'originals', 'concerts'].includes(String(route.query.tab))
    ? String(route.query.tab)
    : 'lives',
)
const selectedAlbum = ref('')
const liveLimit = ref(6)
watch(id, () => {
  selectedAlbum.value = ''
  liveLimit.value = 6
})
const { data, loading, error, reload } = useResource(
  async (signal) => {
    const [artist, lives, albums, concerts] = await Promise.all([
      api.artist(id.value, signal),
      api.lives(Number(id.value), signal),
      api.albums(Number(id.value), signal),
      api.concerts(signal),
    ])
    return {
      artist,
      lives,
      albums,
      concerts: concerts.filter((c) => c.artist_id === Number(id.value)),
    }
  },
  [id],
)
const album = computed(
  () => data.value?.albums.find((a) => a.id === selectedAlbum.value) ?? data.value?.albums[0],
)
const upcoming = computed(() =>
  (data.value?.concerts ?? [])
    .filter((c) => c.starts_at.slice(0, 10) >= todayKey())
    .sort((a, b) => a.starts_at.localeCompare(b.starts_at)),
)
const past = computed(() =>
  (data.value?.concerts ?? [])
    .filter((c) => c.starts_at.slice(0, 10) < todayKey())
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
          <Avatar class="profile-avatar">
            <AvatarImage
              :src="data.artist.image"
              :style="{ objectPosition: data.artist.image_position }"
              :alt="data.artist.name"
              class="object-cover"
            />
            <AvatarFallback>{{ data.artist.roman.slice(0, 2) }}</AvatarFallback>
          </Avatar>
          <div class="profile-copy">
            <p class="eyebrow">{{ data.artist.agency }}</p>
            <div class="profile-name">
              <h1>{{ data.artist.name }}</h1>
              <FavoriteButton :id="data.artist.id" :name="data.artist.name" />
            </div>
            <p class="profile-reading">
              {{ data.artist.display_name }}
              <span>·</span>
              {{ data.artist.roman }}
            </p>
            <p class="profile-intro">{{ data.artist.intro }}</p>
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
              <span class="tab-count">{{ data.lives.length }}</span>
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
          <TabsContent value="lives" class="pt-8">
            <div class="section-heading">
              <div>
                <h2>다시 만나는 라이브</h2>
                <p>좋아하는 순간은, 몇 번을 들어도 좋으니까.</p>
              </div>
              <span class="text-xs text-muted-foreground">최신순</span>
            </div>
            <ResourceState :empty="!data.lives.length" title="라이브 아카이브를 준비하고 있어요">
              <template #action>
                <Button as-child variant="outline">
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
                <LiveCard
                  v-for="live in data.lives.slice(0, liveLimit)"
                  :key="live.id"
                  :live="live"
                />
              </div>
              <Button
                v-if="data.lives.length > liveLimit"
                variant="outline"
                class="mx-auto mt-8 flex"
                @click="liveLimit += 6"
              >
                라이브 더 보기
                <ChevronDown data-icon="inline-end" />
              </Button>
            </ResourceState>
          </TabsContent>
          <TabsContent value="originals" class="pt-8">
            <div class="section-heading">
              <div>
                <h2>자신만의 이야기를 담은 음악</h2>
                <p>앨범과 싱글, 그리고 노래 속의 한 문장.</p>
              </div>
            </div>
            <ResourceState :empty="!data.albums.length" title="디스코그래피를 준비하고 있어요">
              <div class="album-grid">
                <button
                  v-for="a in data.albums"
                  :key="a.id"
                  class="album-card"
                  :aria-pressed="album?.id === a.id"
                  @click="selectedAlbum = a.id"
                >
                  <AlbumCover :src="a.image_url" :title="a.name" />
                  <h3>{{ a.name }}</h3>
                  <p>
                    {{ a.release_date.slice(0, 4) }}
                    <span>·</span>
                    {{ a.album_type === 'album' ? 'Album' : 'Single' }}
                  </p>
                </button>
              </div>
              <section v-if="album" class="track-section">
                <div class="section-heading">
                  <div>
                    <p class="eyebrow">{{ formatDate(album.release_date) }}</p>
                    <h2>{{ album.name }}</h2>
                  </div>
                  <Button as-child variant="outline" size="sm">
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
                    @click="openOverlay(router, route, 'lyrics', track.id)"
                  >
                    <FileText data-icon="inline-start" />
                    {{ track.has_lyrics ? '가사' : '가사 없음' }}
                  </Button>
                </div>
              </section>
            </ResourceState>
          </TabsContent>
          <TabsContent value="concerts" class="pt-8">
            <section>
              <div class="section-heading">
                <div>
                  <p class="eyebrow">SEE YOU THERE</p>
                  <h2>곧 만나요</h2>
                </div>
                <Badge variant="outline">가상 일정으로 구성한 프리뷰</Badge>
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
                  <p class="eyebrow">MOMENTS WE SHARED</p>
                  <h2>함께한 순간들</h2>
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
          </TabsContent>
        </Tabs>
      </template>
    </ResourceState>
  </div>
</template>
