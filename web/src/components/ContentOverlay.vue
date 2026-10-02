<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useMediaQuery } from '@vueuse/core'
import { CalendarDays, MapPin, Ticket, ArrowUpRight, X } from '@lucide/vue'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import {
  Drawer,
  DrawerContent,
  DrawerHeader,
  DrawerTitle,
  DrawerDescription,
  DrawerClose,
} from '@/components/ui/drawer'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { safeUrl } from '@/api/backend'
import { api } from '@/api/client'
import type { Track } from '@/api/types'
import { useResource } from '@/composables/useResource'
import { formatDate } from '@/lib/dates'
import {
  isMixedRelease,
  lyricsKey,
  releaseDetailMeta,
  releaseLinkLabel,
  releaseTypeLabel,
} from '@/lib/discography'
import { openOverlay } from '@/lib/overlays'
import { cn } from '@/lib/utils'
import AlbumCover from './AlbumCover.vue'
import ArtistAvatar from './ArtistAvatar.vue'
import ReleaseTracks from './ReleaseTracks.vue'
import ResourceState from './ResourceState.vue'
const route = useRoute()
const router = useRouter()
const mobile = useMediaQuery('(max-width: 768px)')
const queryValue = (key: 'lyrics' | 'album' | 'event') => {
  const value = route.query[key]
  return typeof value === 'string' ? value : ''
}
const lyricsId = computed(() => queryValue('lyrics'))
const albumId = computed(() => queryValue('album'))
const eventId = computed(() => queryValue('event'))
// Lyrics open on top of an album, so the album stays loaded underneath.
const mode = computed(() => (lyricsId.value ? 'lyrics' : albumId.value ? 'album' : 'event'))
const open = computed(() => !!(lyricsId.value || albumId.value || eventId.value))
const visibleLyrics = ref<string[]>(['original', 'translation'])
let opener: HTMLElement | null = null
let lyricsOpener = ''
watch(
  open,
  (value) => {
    if (value) opener = document.activeElement as HTMLElement
  },
  { flush: 'sync' },
)
const lyricsResource = useResource(
  async (signal) => (lyricsId.value ? api.lyrics(lyricsId.value, signal) : null),
  [lyricsId],
)
const albumResource = useResource(
  async (signal) => {
    if (!albumId.value) return null
    const artistId = Number(route.params.artistId)
    const scoped = Number.isSafeInteger(artistId) && artistId > 0
    const [album, listing, artist] = await Promise.all([
      api.album(albumId.value, artistId, signal),
      // The listing carries is_primary; both reads are shared with the releases tab.
      scoped ? api.albums(artistId, signal).catch(() => []) : Promise.resolve([]),
      scoped ? api.artist(String(artistId), signal).catch(() => null) : Promise.resolve(null),
    ])
    const summary = listing.find((a) => a.id === album.id)
    return {
      album: { ...album, is_primary: summary?.is_primary ?? album.is_primary },
      artistIds: artist?.related_artist_ids ?? (scoped ? [artistId] : []),
    }
  },
  [albumId, () => route.params.artistId],
)
const eventResource = useResource(
  async (signal) => {
    if (!eventId.value) return null
    const [concert, artists] = await Promise.all([
      api.concert(eventId.value, signal),
      api.artists(signal),
    ])
    return { concert, artist: artists.find((a) => a.id === concert.artist_id) }
  },
  [eventId],
)
const resources = { lyrics: lyricsResource, album: albumResource, event: eventResource }
const loading = computed(() => resources[mode.value].loading.value)
const error = computed(() => resources[mode.value].error.value)
const lyrics = computed(() => (mode.value === 'lyrics' ? lyricsResource.data.value : null))
const release = computed(() => (mode.value === 'album' ? albumResource.data.value : null))
const concertDetail = computed(() => (mode.value === 'event' ? eventResource.data.value : null))
const title = computed(() => {
  if (mode.value === 'lyrics') return lyrics.value?.original_title || '가사'
  if (mode.value === 'album') return release.value?.album.name || '발매 정보'
  return concertDetail.value?.concert.title || '공연 정보'
})
const description = computed(() => {
  if (mode.value === 'lyrics') return lyrics.value?.artist_name || '가사를 불러오고 있어요.'
  if (mode.value === 'album')
    return release.value ? releaseDetailMeta(release.value.album) : '발매 정보를 불러오고 있어요.'
  return '공연 일시 · 장소 · 티켓 정보'
})
function openLyrics(track: Track) {
  lyricsOpener = lyricsKey(track)
  openOverlay(router, route, 'lyrics', lyricsOpener)
}
// Closing lyrics returns to the album; put focus back on the button that opened them.
watch(mode, async (next, previous) => {
  if (!open.value || previous !== 'lyrics' || next !== 'album' || !lyricsOpener) return
  await nextTick()
  document
    .querySelector<HTMLElement>(`[data-lyrics-id="${CSS.escape(lyricsOpener)}"]`)
    ?.focus()
})
function reload() {
  resources[mode.value].reload()
}
function close(value: boolean) {
  if (value) return
  if (window.history.state?.draftOverlay) router.back()
  else router.replace({ query: { ...route.query, [mode.value]: undefined } })
}
async function restoreFocus(event: Event) {
  event.preventDefault()
  await nextTick()
  ;(opener?.isConnected ? opener : document.querySelector<HTMLElement>('#main-content'))?.focus()
}
</script>
<template>
  <component
    :is="mobile ? Drawer : Dialog"
    :key="mobile ? 'drawer' : 'dialog'"
    :open="open"
    @update:open="close"
  >
    <component
      :is="mobile ? DrawerContent : DialogContent"
      class="content-overlay sm:max-w-2xl"
      @close-auto-focus="restoreFocus"
    >
      <component
        :is="mobile ? DrawerHeader : DialogHeader"
        :class="cn('pr-8', release && 'release-overlay-header')"
      >
        <template v-if="release">
          <AlbumCover
            :src="release.album.image_url"
            :title="release.album.name"
            decorative
            class="release-cover release-overlay-cover"
          />
          <div class="release-overlay-heading">
            <p class="release-overlay-kind">
              {{ releaseTypeLabel(release.album.album_type) }}
              <Badge v-if="release.album.is_primary === false" variant="secondary">참여</Badge>
            </p>
            <component :is="mobile ? DrawerTitle : DialogTitle" class="release-title">
              {{ title }}
            </component>
            <component :is="mobile ? DrawerDescription : DialogDescription">
              {{ description }}
            </component>
            <Button
              v-if="release.album.source_url"
              as-child
              variant="outline"
              size="sm"
              class="release-overlay-link"
            >
              <a :href="release.album.source_url" target="_blank" rel="noopener noreferrer">
                {{ releaseLinkLabel(release.album.source_url) }}
                <ArrowUpRight data-icon="inline-end" />
              </a>
            </Button>
          </div>
        </template>
        <template v-else>
          <component :is="mobile ? DrawerTitle : DialogTitle">{{ title }}</component>
          <component :is="mobile ? DrawerDescription : DialogDescription">
            {{ description }}
          </component>
        </template>
      </component>
      <DrawerClose v-if="mobile" as-child>
        <Button variant="ghost" size="icon" class="absolute top-6 right-5" aria-label="닫기">
          <X />
        </Button>
      </DrawerClose>
      <div class="overlay-scroll">
        <ResourceState :loading="loading" :error="error" @retry="reload">
          <div v-if="lyrics" class="lyrics-content">
            <p v-if="lyrics.needs_review" class="mb-4 text-sm text-muted-foreground">
              검토가 필요한 가사입니다.
            </p>
            <a
              v-if="safeUrl(lyrics.lyrics_source_url)"
              :href="safeUrl(lyrics.lyrics_source_url)"
              target="_blank"
              rel="noopener noreferrer"
              class="text-sm underline"
            >
              가사 출처
            </a>
            <div class="lyrics-toolbar">
              <ToggleGroup
                type="multiple"
                v-model="visibleLyrics"
                variant="outline"
                aria-label="가사 표시 언어"
              >
                <ToggleGroupItem value="original">원문</ToggleGroupItem>
                <ToggleGroupItem value="translation">번역</ToggleGroupItem>
                <ToggleGroupItem value="pronunciation">발음</ToggleGroupItem>
              </ToggleGroup>
            </div>
            <div class="lyric-stanzas">
              <div
                v-for="(line, i) in lyrics.original_lyrics.split('\n')"
                :key="i"
                class="lyric-line"
              >
                <p v-if="visibleLyrics.includes('original')" lang="ja">{{ line }}</p>
                <p v-if="visibleLyrics.includes('pronunciation')" class="lyric-pronunciation">
                  {{ lyrics.pronunciation_ko.split('\n')[i] }}
                </p>
                <p v-if="visibleLyrics.includes('translation')" class="lyric-translation">
                  {{ lyrics.translation_ko.split('\n')[i] }}
                </p>
              </div>
              <p v-if="!visibleLyrics.length" class="text-muted-foreground">
                표시할 언어를 선택해 주세요.
              </p>
            </div>
          </div>
          <ReleaseTracks
            v-if="release"
            :tracks="release.album.tracks"
            :artist-ids="release.artistIds"
            :highlight="isMixedRelease(release.album.tracks, release.artistIds)"
            @lyrics="openLyrics"
          />
          <div v-if="concertDetail" class="concert-detail">
            <div class="concert-detail-art">
              <ArtistAvatar v-if="concertDetail.artist" :artist="concertDetail.artist" />
              <div>
                <h3>{{ concertDetail.artist?.name }}</h3>
                <p>{{ concertDetail.concert.event_format === 'online' ? 'ONLINE LIVE' : 'LIVE EVENT' }}</p>
              </div>
            </div>
            <dl class="concert-facts">
              <div>
                <dt>
                  <CalendarDays />
                  일시
                </dt>
                <dd>
                  {{
                    formatDate(concertDetail.concert.starts_at, {
                      weekday: 'short',
                      hour: '2-digit',
                      minute: '2-digit',
                    })
                  }}
                  <small>
                    {{
                      concertDetail.concert.starts_at.length === 10 ? '시간 미정' : '한국·일본 시간 (UTC+9)'
                    }}
                  </small>
                </dd>
              </div>
              <div>
                <dt>
                  <MapPin />
                  장소
                </dt>
                <dd>
                  {{ concertDetail.concert.venue || '장소 미정' }}
                  <small>{{ concertDetail.concert.city }}</small>
                </dd>
              </div>
              <div>
                <dt>
                  <Ticket />
                  티켓
                </dt>
                <dd>
                  {{ concertDetail.concert.price_text || '가격 미정' }}
                </dd>
              </div>
            </dl>
            <Button
              v-if="concertDetail.concert.ticket_url || concertDetail.concert.source_url || concertDetail.artist?.official_url"
              as-child
              class="w-full"
            >
              <a
                :href="
                  concertDetail.concert.ticket_url || concertDetail.concert.source_url || concertDetail.artist?.official_url
                "
                target="_blank"
                rel="noopener noreferrer"
              >
                {{
                  concertDetail.concert.ticket_url
                    ? '티켓 페이지'
                    : concertDetail.concert.source_url
                      ? '공연 안내'
                      : '아티스트 공식 사이트'
                }}
                <ArrowUpRight data-icon="inline-end" />
              </a>
            </Button>
          </div>
        </ResourceState>
      </div>
    </component>
  </component>
</template>
