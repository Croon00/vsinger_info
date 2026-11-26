<script setup lang="ts">
import { computed, nextTick, onScopeDispose, ref, shallowRef, watch } from 'vue'
import { ChevronDown, FileText, Music2, Play, Search } from '@lucide/vue'
import { api } from '@/api/client'
import type { ExploredSong } from '@/api/types'
import { useResource } from '@/composables/useResource'
import { formatDate } from '@/lib/dates'
import { formatSubscribers } from '@/lib/subscribers'
import { Button } from '@/components/ui/button'
import {
  Item,
  ItemGroup,
  ItemContent,
  ItemTitle,
  ItemDescription,
  ItemActions,
} from '@/components/ui/item'
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Field, FieldGroup, FieldLabel } from '@/components/ui/field'
import { InputGroup, InputGroupAddon, InputGroupInput } from '@/components/ui/input-group'
import ResourceState from '@/components/ResourceState.vue'
import SongVideoDialog from '@/components/SongVideoDialog.vue'
import OriginalLyricsDialog from '@/components/OriginalLyricsDialog.vue'
import OriginalLyricsPanel from '@/components/OriginalLyricsPanel.vue'

const props = defineProps<{ artistId: number }>()
const order = ref('latest')
const query = ref('')
const searchTerm = ref('')
let timer: ReturnType<typeof setTimeout> | undefined
watch(query, (value) => {
  clearTimeout(timer)
  timer = setTimeout(() => {
    searchTerm.value = value.trim()
  }, 250)
})
const { data, loading, error, reload } = useResource(
  (signal) =>
    api.songPage('original', 'all', searchTerm.value, order.value, 0, signal, [props.artistId]),
  [() => props.artistId, order, searchTerm],
)
const extra = ref<ExploredSong[]>([])
const nextOffset = ref(0)
const moreLoading = ref(false)
const moreError = ref('')
const failedImages = ref(new Set<string>())
let moreController: AbortController | undefined
const playing = shallowRef<ExploredSong | null>(null)
const lyricsSong = shallowRef<ExploredSong | null>(null)
// Song playing in the docked panel beside the list (player + lyrics).
const docked = shallowRef<ExploredSong | null>(null)
let trigger: HTMLElement | null = null
watch(data, (value) => {
  moreController?.abort()
  moreController = undefined
  extra.value = []
  nextOffset.value = value ? value.offset + value.items.length : 0
  moreLoading.value = false
  moreError.value = ''
  playing.value = null
  lyricsSong.value = null
})
const songs = computed(() => [
  ...new Map(
    [...(data.value?.items ?? []), ...extra.value].map((song) => [song.key, song]),
  ).values(),
])
async function loadMore() {
  if (moreLoading.value || !data.value) return
  const initial = data.value
  const controller = new AbortController()
  moreController = controller
  moreLoading.value = true
  moreError.value = ''
  try {
    const page = await api.songPage(
      'original',
      'all',
      searchTerm.value,
      order.value,
      nextOffset.value,
      controller.signal,
      [props.artistId],
    )
    if (!controller.signal.aborted && data.value === initial) {
      extra.value.push(...page.items)
      nextOffset.value = page.offset + page.items.length
      if (!page.items.length) nextOffset.value = page.total
    }
  } catch (e) {
    if (!controller.signal.aborted)
      moreError.value = e instanceof Error ? e.message : '곡을 불러오지 못했어요.'
  } finally {
    if (moreController === controller) moreLoading.value = false
  }
}
function playable(song: ExploredSong) {
  return /^[A-Za-z0-9_-]{11}$/.test(song.youtube_video_id ?? '')
}
function open(song: ExploredSong, event: MouseEvent) {
  // While the panel is docked, other songs play there instead of in a dialog.
  if (docked.value) {
    docked.value = song
    return
  }
  trigger = event.currentTarget as HTMLElement
  playing.value = song
}
function openLyrics(song: ExploredSong, event: MouseEvent) {
  trigger = event.currentTarget as HTMLElement
  lyricsSong.value = song
}
function closeLyrics() {
  lyricsSong.value = null
  nextTick(() => {
    if (trigger?.isConnected) trigger.focus()
  })
}
function listen(song: ExploredSong) {
  lyricsSong.value = null
  docked.value = song
}
function close() {
  playing.value = null
  nextTick(() => {
    if (trigger?.isConnected) trigger.focus()
  })
}
onScopeDispose(() => {
  clearTimeout(timer)
  moreController?.abort()
})
</script>

<template>
  <section class="artist-original-songs" aria-label="아티스트 오리지널 곡">
    <div class="section-heading">
      <h2>
        오리지널 곡
        <span v-if="data">{{ data.total.toLocaleString('ko-KR') }}곡</span>
      </h2>
      <Select v-model="order">
        <SelectTrigger class="w-40" aria-label="오리지널 곡 정렬"><SelectValue /></SelectTrigger>
        <SelectContent>
          <SelectGroup>
            <SelectItem value="latest">최신 영상순</SelectItem>
            <SelectItem value="name">곡 이름순</SelectItem>
            <SelectItem value="high">조회수 높은순</SelectItem>
          </SelectGroup>
        </SelectContent>
      </Select>
    </div>
    <form
      class="mb-5"
      role="search"
      aria-label="오리지널 곡 검색"
      @submit.prevent="searchTerm = query.trim()"
    >
      <FieldGroup>
        <Field>
          <FieldLabel :for="`original-song-search-${artistId}`" class="sr-only">
            오리지널 곡 제목
          </FieldLabel>
          <InputGroup>
            <InputGroupAddon><Search /></InputGroupAddon>
            <InputGroupInput
              :id="`original-song-search-${artistId}`"
              v-model="query"
              placeholder="오리지널 곡 제목으로 찾기"
            />
          </InputGroup>
        </Field>
      </FieldGroup>
    </form>
    <div class="original-songs-layout" :class="{ docked: !!docked }">
      <div class="original-songs-list">
        <ResourceState
          :loading="loading"
          :error="error"
          :empty="!songs.length"
          :title="searchTerm ? '검색한 오리지널 곡이 없습니다' : '등록된 오리지널 곡이 없습니다'"
          description="등록된 곡이 추가되면 여기에 표시됩니다."
          @retry="reload"
        >
          <ItemGroup aria-label="오리지널 곡 목록">
            <Item
              v-for="song in songs"
              :key="song.key"
              as="article"
              role="listitem"
              variant="outline"
              class="original-song-item"
            >
              <button
                v-if="playable(song)"
                type="button"
                class="original-song-thumb"
                :aria-label="`${song.title_ko || song.title} 재생`"
                aria-haspopup="dialog"
                @click="open(song, $event)"
              >
                <img
                  v-if="!failedImages.has(song.key)"
                  :src="`https://i.ytimg.com/vi/${song.youtube_video_id}/mqdefault.jpg`"
                  alt=""
                  width="320"
                  height="180"
                  loading="lazy"
                  @error="failedImages.add(song.key)"
                />
                <Music2 v-else aria-hidden="true" />
                <span class="live-play" aria-hidden="true"><Play fill="currentColor" /></span>
              </button>
              <div v-else class="original-song-thumb" aria-hidden="true"><Music2 /></div>
              <ItemContent>
                <ItemTitle>
                  <button
                    v-if="playable(song)"
                    type="button"
                    class="song-title-button"
                    aria-haspopup="dialog"
                    @click="open(song, $event)"
                  >
                    {{ song.title_ko || song.title }}
                  </button>
                  <span v-else>{{ song.title_ko || song.title }}</span>
                </ItemTitle>
                <ItemDescription v-if="song.title_ko">{{ song.title }}</ItemDescription>
                <ItemDescription>{{ song.artist_name }}</ItemDescription>
                <ItemDescription>
                  <time v-if="song.published_at" :datetime="song.published_at">
                    {{ formatDate(song.published_at) }}
                  </time>
                  <span v-else>{{ playable(song) ? '게시일 미등록' : '등록된 영상 없음' }}</span>
                </ItemDescription>
              </ItemContent>
              <ItemActions
                v-if="song.view_count != null || song.lyrics_recording_id"
                class="original-song-views"
              >
                <Button
                  v-if="song.lyrics_recording_id"
                  variant="outline"
                  size="sm"
                  class="original-song-lyrics"
                  :class="{ active: docked?.key === song.key }"
                  aria-haspopup="dialog"
                  :aria-label="`${song.title_ko || song.title} 가사 보기`"
                  @click="openLyrics(song, $event)"
                >
                  <FileText data-icon="inline-start" />
                  가사
                </Button>
                <span v-if="song.view_count != null" class="text-sm text-muted-foreground">
                  {{ formatSubscribers(song.view_count) }}회
                </span>
              </ItemActions>
            </Item>
          </ItemGroup>
          <Button
            v-if="data && nextOffset < data.total"
            variant="outline"
            class="mx-auto mt-6 flex"
            :disabled="moreLoading"
            @click="loadMore"
          >
            {{ moreLoading ? '불러오는 중' : '더보기' }}
            <ChevronDown data-icon="inline-end" />
          </Button>
          <p v-if="moreError" role="alert" class="mt-3 text-sm text-destructive">{{ moreError }}</p>
        </ResourceState>
      </div>
      <OriginalLyricsPanel v-if="docked" :song="docked" @close="docked = null" />
    </div>
    <SongVideoDialog :song="playing" @close="close" />
    <OriginalLyricsDialog
      :song="lyricsSong"
      :can-listen="!!lyricsSong && playable(lyricsSong)"
      @close="closeLyrics"
      @listen="listen"
    />
  </section>
</template>
