<script setup lang="ts">
import { computed, nextTick, onMounted, onScopeDispose, ref, shallowRef, watch } from 'vue'
import { ChevronLeft, ChevronRight, Music2, Play } from '@lucide/vue'
import { api } from '@/api/client'
import type { ExploredSong } from '@/api/types'
import { useResource } from '@/composables/useResource'
import { formatDate } from '@/lib/dates'
import { Button } from '@/components/ui/button'
import ResourceState from '@/components/ResourceState.vue'
import SongVideoDialog from '@/components/SongVideoDialog.vue'

const props = defineProps<{ kind: 'original' | 'cover'; title: string }>()
const { data, loading, error, reload } = useResource(
  (signal) =>
    api.songPage(
      props.kind,
      'all',
      '',
      'latest',
      0,
      signal,
      [],
      {},
      {},
      {
        limit: 10,
        publishedOnly: true,
      },
    ),
  [() => props.kind],
)
const songs = computed(() => data.value?.items ?? [])
const track = ref<HTMLElement | null>(null)
const canPrevious = ref(false)
const canNext = ref(false)
const failedImages = ref(new Set<string>())
const playing = shallowRef<ExploredSong | null>(null)
let trigger: HTMLElement | null = null
let observer: ResizeObserver | undefined
function updateControls() {
  const el = track.value
  canPrevious.value = !!el && el.scrollLeft > 2
  canNext.value = !!el && el.scrollLeft + el.clientWidth < el.scrollWidth - 2
}
function move(direction: number) {
  const el = track.value
  el?.scrollBy({
    left: direction * el.clientWidth * 0.85,
    behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth',
  })
}
function open(song: ExploredSong, event: MouseEvent) {
  trigger = event.currentTarget as HTMLElement
  playing.value = song
}
function close() {
  playing.value = null
  nextTick(() => trigger?.isConnected && trigger.focus())
}
watch(track, (el, previous) => {
  if (previous) observer?.unobserve(previous)
  if (el) observer?.observe(el)
  nextTick(updateControls)
})
onMounted(() => {
  observer = new ResizeObserver(updateControls)
  if (track.value) observer.observe(track.value)
})
onScopeDispose(() => observer?.disconnect())
</script>

<template>
  <section class="recent-songs" :aria-labelledby="`recent-${kind}-heading`">
    <div class="section-heading">
      <div>
        <h2 :id="`recent-${kind}-heading`">{{ title }}</h2>
        <p>YouTube 게시일 최신순</p>
      </div>
      <div class="recent-song-actions">
        <Button variant="ghost" as-child>
          <RouterLink
            :to="{ path: '/explore', query: { view: 'songs', kind, song_order: 'latest' } }"
          >
            전체 보기
          </RouterLink>
        </Button>
        <Button
          variant="outline"
          size="icon"
          :aria-label="`${title} 이전`"
          :aria-controls="`recent-${kind}-track`"
          :disabled="!canPrevious"
          @click="move(-1)"
        >
          <ChevronLeft />
        </Button>
        <Button
          variant="outline"
          size="icon"
          :aria-label="`${title} 다음`"
          :aria-controls="`recent-${kind}-track`"
          :disabled="!canNext"
          @click="move(1)"
        >
          <ChevronRight />
        </Button>
      </div>
    </div>
    <ResourceState
      :loading="loading"
      :error="error"
      :empty="songs.length === 0"
      title="아직 등록된 영상이 없어요"
      description="새로운 곡이 등록되면 여기에 보여드릴게요."
      @retry="reload"
    >
      <div
        :id="`recent-${kind}-track`"
        ref="track"
        class="recent-song-track"
        role="list"
        :aria-label="title"
        @scroll.passive="updateControls"
      >
        <article v-for="song in songs" :key="song.key" class="recent-song-card" role="listitem">
          <button
            type="button"
            class="recent-song-button"
            :aria-label="`${song.title} · ${song.artist_name} 재생`"
            @click="open(song, $event)"
          >
            <div class="recent-song-thumb">
              <img
                v-if="!failedImages.has(song.key)"
                :src="`https://i.ytimg.com/vi/${song.youtube_video_id}/hqdefault.jpg`"
                alt=""
                width="480"
                height="360"
                loading="lazy"
                @error="failedImages.add(song.key)"
              />
              <Music2 v-else class="size-10" aria-hidden="true" />
              <span class="live-play" aria-hidden="true">
                <Play fill="currentColor" class="size-5" />
              </span>
            </div>
            <h3>{{ song.title_ko || song.title }}</h3>
            <p class="recent-song-artist">{{ song.artist_name }}</p>
            <time :datetime="song.published_at ?? undefined">
              {{
                formatDate(song.published_at ?? '', {
                  year: 'numeric',
                  month: '2-digit',
                  day: '2-digit',
                })
              }}
            </time>
          </button>
        </article>
      </div>
    </ResourceState>
    <SongVideoDialog :song="playing" @close="close" />
  </section>
</template>

<style scoped>
.recent-songs {
  min-width: 0;
}
.recent-song-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}
.recent-song-track {
  display: flex;
  gap: 20px;
  overflow-x: auto;
  scroll-snap-type: x mandatory;
  scroll-padding: 4px;
  padding: 4px 4px 16px;
  scrollbar-width: thin;
  scrollbar-color: var(--border) transparent;
}
.recent-song-card {
  flex: 0 0 calc((100% - 80px) / 3.5);
  min-width: 0;
  scroll-snap-align: start;
}
.recent-song-button {
  display: block;
  width: 100%;
  text-align: left;
  cursor: pointer;
  border-radius: var(--radius-xl);
}
.recent-song-button:focus-visible {
  outline: 2px solid var(--ring);
  outline-offset: 3px;
}
.recent-song-thumb {
  position: relative;
  display: grid;
  place-items: center;
  aspect-ratio: 16 / 9;
  overflow: hidden;
  border-radius: var(--radius-xl);
  background: var(--muted);
  color: var(--muted-foreground);
}
.recent-song-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.recent-song-button h3 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  font-size: 16px;
  font-weight: 600;
  line-height: 1.5;
  height: 3em;
  margin-top: 12px;
  overflow-wrap: anywhere;
}
.recent-song-artist {
  margin-top: 6px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 14px;
  color: var(--muted-foreground);
}
.recent-song-button time {
  display: block;
  margin-top: 4px;
  font-size: 13px;
  color: var(--muted-foreground);
}
@media (max-width: 1024px) {
  .recent-song-card {
    flex-basis: calc((100% - 48px) / 2.5);
  }
}
@media (max-width: 600px) {
  .recent-song-track {
    gap: 14px;
  }
  .recent-song-card {
    flex-basis: 82%;
  }
  .recent-song-actions {
    gap: 4px;
  }
}
</style>
