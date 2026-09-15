<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, ArrowUpRight, Play, AudioLines, ListMusic, RotateCcw } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardFooter,
} from '@/components/ui/card'
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import { api } from '@/api/client'
import { useResource } from '@/composables/useResource'
import { loadYouTube, clampTime, type YouTubePlayer } from '@/lib/youtube'
import { formatDate, formatTime } from '@/lib/dates'
import { cn } from '@/lib/utils'
import ResourceState from '@/components/ResourceState.vue'
const route = useRoute()
const router = useRouter()
const id = computed(() => String(route.params.archiveId))
const { data, loading, error, reload } = useResource((signal) => api.live(id.value, signal), [id])
const playerHost = ref<HTMLElement>()
const ready = ref(false)
const playerError = ref('')
const autoplayMuted = ref(false)
const currentTime = ref(0)
let player: YouTubePlayer | undefined
let interval: ReturnType<typeof setInterval> | undefined
let readyTimeout: ReturnType<typeof setTimeout> | undefined
let version = 0
const activeSong = computed(
  () =>
    data.value?.performances
      .slice()
      .reverse()
      .find((p) => p.start_seconds <= currentTime.value)?.id,
)
function teardown() {
  version++
  clearInterval(interval)
  clearTimeout(readyTimeout)
  try {
    player?.destroy()
  } catch {
    /* Already detached. */
  }
  player = undefined
  ready.value = false
}
async function setup() {
  teardown()
  playerError.value = ''
  autoplayMuted.value = false
  currentTime.value = clampTime(route.query.t, data.value?.duration_seconds ?? 0)
  const current = version
  if (!data.value) return
  await nextTick()
  try {
    const YT = await loadYouTube()
    if (current !== version || !playerHost.value || !data.value) return
    const startSeconds = currentTime.value
    const target = document.createElement('div')
    playerHost.value.replaceChildren(target)
    readyTimeout = setTimeout(() => {
      if (current === version && !ready.value)
        playerError.value =
          '플레이어 연결이 지연되고 있어요. 다시 시도하거나 YouTube에서 열어 주세요.'
    }, 15000)
    player = new YT.Player(target, {
      videoId: data.value.video_id,
      width: '100%',
      height: '100%',
      playerVars: {
        autoplay: 1,
        playsinline: 1,
        rel: 0,
        origin: window.location.origin,
        start: startSeconds,
      },
      events: {
        onReady() {
          if (current !== version) return
          clearTimeout(readyTimeout)
          ready.value = true
          playerError.value = ''
          // The embed's start parameter already sets the initial position.
          // Only seek again if the requested timestamp changed while loading.
          const requestedTime = clampTime(route.query.t, data.value!.duration_seconds)
          if (requestedTime !== startSeconds) player?.seekTo(requestedTime, true)
          interval = setInterval(() => {
            if (
              player &&
              ready.value &&
              !playerError.value &&
              [1, 2].includes(player.getPlayerState())
            )
              currentTime.value = player.getCurrentTime()
          }, 500)
        },
        onAutoplayBlocked() {
          if (current !== version || autoplayMuted.value) return
          autoplayMuted.value = true
          player?.mute()
          player?.playVideo()
        },
        onError(event) {
          if (current !== version) return
          clearTimeout(readyTimeout)
          const messages: Record<number, string> = {
            100: '삭제되었거나 비공개로 전환된 영상이에요. YouTube에서 확인해 주세요.',
            101: '이 영상의 외부 재생이 제한되어 있어요. YouTube에서 확인해 주세요.',
            150: '이 영상의 외부 재생이 제한되어 있어요. YouTube에서 확인해 주세요.',
            153: 'YouTube에서 이 브라우저의 재생 요청을 확인하지 못했어요. 원본 영상으로 이동해 주세요.',
          }
          playerError.value =
            messages[event.data] ||
            '이 환경에서는 영상을 재생할 수 없어요. YouTube에서 확인해 주세요.'
        },
      },
    })
  } catch (e) {
    if (current === version)
      playerError.value = e instanceof Error ? e.message : '영상을 불러오지 못했어요.'
  }
}
watch(data, setup)
watch(
  () => route.query.t,
  (t) => {
    currentTime.value = clampTime(t, data.value?.duration_seconds ?? 0)
    if (ready.value) player?.seekTo(currentTime.value, true)
  },
)
watch(id, teardown)
onBeforeUnmount(teardown)
function seek(seconds: number) {
  router.replace({ query: { ...route.query, t: seconds.toString() } })
  if (ready.value) player?.seekTo(seconds, true)
  currentTime.value = seconds
}
</script>
<template>
  <div class="page-container viewer-page page-enter">
    <Button v-if="data" as-child variant="ghost" class="back-link">
      <RouterLink :to="`/artists/${data.artist_id}?tab=lives`">
        <ArrowLeft data-icon="inline-start" />
        아티스트의 라이브
      </RouterLink>
    </Button>
    <ResourceState :loading="loading" :error="error" @retry="reload">
      <template v-if="data">
        <div class="viewer-layout">
          <section>
            <div class="video-frame">
              <div ref="playerHost" class="player-host" />
              <div v-if="!ready && !playerError" class="player-loading">
                <AudioLines class="size-9" />
                <span>플레이어를 준비하고 있어요</span>
              </div>
            </div>
            <p
              v-if="autoplayMuted && !playerError"
              class="mt-3 text-sm text-muted-foreground"
              role="status"
            >
              음소거로 자동재생 중입니다. 영상에서 소리를 켜 주세요.
            </p>
            <Alert v-if="playerError" class="mt-4">
              <AlertTitle>영상을 재생하지 못했어요</AlertTitle>
              <AlertDescription>{{ playerError }}</AlertDescription>
              <div class="flex gap-2 mt-4">
                <Button variant="outline" size="sm" @click="setup">
                  <RotateCcw data-icon="inline-start" />
                  다시 시도
                </Button>
                <Button as-child size="sm">
                  <a
                    :href="`https://www.youtube.com/watch?v=${data.video_id}&t=${Math.floor(currentTime)}s`"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    YouTube에서 열기
                    <ArrowUpRight data-icon="inline-end" />
                  </a>
                </Button>
              </div>
            </Alert>
            <div class="viewer-heading">
              <p class="eyebrow">
                {{ formatDate(data.broadcast_at) }}
                <span>·</span>
                LIVE ARCHIVE
              </p>
              <h1>{{ data.title_ko }}</h1>
              <p class="viewer-original-title">{{ data.title }}</p>
              <div class="viewer-meta">
                <Badge variant="secondary">
                  <ListMusic />
                  {{ data.performances.length }}곡
                </Badge>
                <span>{{ formatTime(data.duration_seconds) }}</span>
                <Button as-child variant="ghost" size="sm">
                  <a
                    :href="`https://www.youtube.com/watch?v=${data.video_id}`"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    YouTube
                    <ArrowUpRight data-icon="inline-end" />
                  </a>
                </Button>
              </div>
            </div>
          </section>
          <aside class="setlist-panel">
            <Card size="sm">
              <CardHeader>
                <CardTitle>세트리스트</CardTitle>
                <CardDescription>곡을 누르면 해당 순간으로 이동해요.</CardDescription>
              </CardHeader>
              <CardContent>
                <ResourceState
                  :empty="!data.performances.length"
                  title="세트리스트 준비 중"
                  description="등록된 곡 정보가 없습니다. 영상은 재생할 수 있습니다."
                >
                  <ol class="setlist">
                    <li v-for="(song, index) in data.performances" :key="song.id">
                      <button
                        :class="cn('setlist-song', activeSong === song.id && 'is-playing')"
                        :aria-current="activeSong === song.id ? 'true' : undefined"
                        @click="seek(song.start_seconds)"
                      >
                        <span class="setlist-number">
                          <AudioLines v-if="activeSong === song.id" class="size-4" />
                          <template v-else>{{ String(index + 1).padStart(2, '0') }}</template>
                        </span>
                        <span class="setlist-name">
                          <strong>{{ song.song_title }}</strong>
                          <small>{{ song.original_artist }}</small>
                        </span>
                        <span class="setlist-time">{{ formatTime(song.start_seconds) }}</span>
                      </button>
                    </li>
                  </ol>
                </ResourceState>
              </CardContent>
              <CardFooter v-if="data.metadata_note">
                <a
                  :href="data.source_url"
                  target="_blank"
                  rel="noopener noreferrer"
                  class="setlist-source"
                >
                  {{ data.metadata_note }} ↗
                </a>
              </CardFooter>
            </Card>
          </aside>
        </div>
      </template>
    </ResourceState>
  </div>
</template>
