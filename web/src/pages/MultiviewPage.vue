<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useMediaQuery } from '@vueuse/core'
import { ArrowLeft, Maximize, MessageSquare, RotateCcw, Volume2, VolumeX, X } from '@lucide/vue'
import { request } from '@/api/http'
import { isMock } from '@/api/config'
import type { LiveStream, Page, StreamGroup } from '@/api/types'
import { favoriteIds } from '@/composables/preferences'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { avatarImageSource } from '@/lib/avatar-image'
import { isStreamWithinUpcomingWindow, streamTime } from '@/lib/stream-time'
import { Field, FieldGroup, FieldLabel } from '@/components/ui/field'
import {
  NativeSelect,
  NativeSelectOption,
  NativeSelectOptGroup,
} from '@/components/ui/native-select'
import ResourceState from '@/components/ResourceState.vue'
import StreamPlayer from '@/components/StreamPlayer.vue'
import { cn } from '@/lib/utils'

const root = ref<HTMLElement>()
const streams = ref<LiveStream[]>([])
const selected = ref<LiveStream[]>([])
const chatId = ref('')
const audioId = ref('')
const chatVisible = ref(true)
const scope = ref('all')
const groupFilter = ref('all')
const groups = ref<StreamGroup[]>([])
const layout = ref('grid')
const loading = ref(true)
const refreshing = ref(false)
const error = ref('')
const notice = ref('')
const lastRead = ref('')
const now = ref(Date.now())
const pixelRatio = window.devicePixelRatio || 1
const mobile = useMediaQuery('(max-width: 768px)')
const prefersDark = useMediaQuery('(prefers-color-scheme: dark)')
function isFreeChat(stream: LiveStream) {
  return /free\s*chat/i.test(stream.title.normalize('NFKC'))
}
const visibleStreams = computed(() => {
  const group = groups.value.find((g) => g.key === groupFilter.value)
  return streams.value.filter(
    (s) =>
      !isFreeChat(s) &&
      isStreamWithinUpcomingWindow(s, now.value) &&
      (scope.value !== 'favorites' || favoriteIds.value.includes(s.artist_id)) &&
      (groupFilter.value === 'all' || !!group?.account_ids.includes(s.account_id)),
  )
})
const chatStream = computed(() => selected.value.find((s) => s.video_id === chatId.value))
const chatUrl = computed(() => {
  if (!chatStream.value) return ''
  const url = new URL('https://www.youtube.com/live_chat')
  url.searchParams.set('v', chatStream.value.video_id)
  url.searchParams.set('embed_domain', window.location.hostname)
  // YouTube owns the frame; chat appearance follows its supported parameter.
  if (prefersDark.value) url.searchParams.set('dark_theme', '1')
  return url.toString()
})
let controller: AbortController | undefined
let timer: ReturnType<typeof setInterval> | undefined
let closed = false
async function refresh() {
  if (controller || closed) return
  const current = new AbortController()
  controller = current
  refreshing.value = true
  try {
    // Read all pages so channels are not silently lost beyond the first 100.
    const items: LiveStream[] = []
    let offset = 0
    let total = 0
    do {
      const result = await request<Page<LiveStream>>(
        `${isMock ? '/api/draft/streams' : '/api/streams'}?offset=${offset}&limit=100&include_upcoming=true`,
        current.signal,
      )
      items.push(...result.items)
      total = result.total
      offset += result.items.length
      if (!result.items.length) break
    } while (offset < total && offset < 100000)
    const groupItems = await request<StreamGroup[]>(
      isMock ? '/api/draft/stream-groups' : '/api/stream-groups',
      current.signal,
    )
    if (closed) return
    groups.value = groupItems
    streams.value = items
    // Refresh metadata without recreating players. Ended/stale entries remain
    // watchable until explicitly closed; never interrupt a stream on API failure.
    selected.value = selected.value.map((s) => items.find((v) => v.video_id === s.video_id) ?? s)
    for (const stream of selected.value.filter(isFreeChat)) remove(stream.video_id)
    lastRead.value = new Date().toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' })
    error.value = ''
  } catch (e) {
    if (!closed && !current.signal.aborted)
      error.value = e instanceof Error ? e.message : '방송 목록을 불러오지 못했어요.'
  } finally {
    loading.value = false
    refreshing.value = false
    controller = undefined
  }
}
function toggle(stream: LiveStream) {
  notice.value = ''
  if (selected.value.some((s) => s.video_id === stream.video_id)) {
    remove(stream.video_id)
    return
  }
  if (selected.value.length >= 4) {
    notice.value = '최대 4개 방송까지 함께 볼 수 있어요. 먼저 방송 하나를 닫아 주세요.'
    return
  }
  selected.value.push(stream)
  if (!chatId.value) chatId.value = stream.video_id
}
function remove(id: string) {
  selected.value = selected.value.filter((s) => s.video_id !== id)
  if (chatId.value === id) chatId.value = selected.value[0]?.video_id ?? ''
  if (audioId.value === id) audioId.value = ''
  notice.value = ''
}
function addVisible() {
  const additions = visibleStreams.value.filter(
    (s) => !selected.value.some((v) => v.video_id === s.video_id),
  )
  const room = 4 - selected.value.length
  selected.value.push(...additions.slice(0, room))
  if (!chatId.value) chatId.value = selected.value[0]?.video_id ?? ''
  notice.value =
    additions.length > room
      ? '최대 4개까지 담았어요. 나머지 방송은 기존 방송을 닫은 뒤 선택해 주세요.'
      : ''
}
function selectChat(id: string) {
  chatId.value = id
  chatVisible.value = true
}
async function fullscreen() {
  try {
    if (document.fullscreenElement) await document.exitFullscreen()
    else await root.value?.requestFullscreen()
  } catch {
    notice.value = '이 브라우저에서는 전체 화면을 사용할 수 없어요.'
  }
}
onMounted(() => {
  refresh()
  timer = setInterval(() => {
    now.value = Date.now()
    if (!document.hidden) refresh()
  }, 60000)
})
onBeforeUnmount(() => {
  closed = true
  clearInterval(timer)
  controller?.abort()
})
</script>
<template>
  <div ref="root" class="multiview-page">
    <header class="multiview-toolbar">
      <Button as-child variant="ghost" size="icon" aria-label="홈으로">
        <RouterLink to="/"><ArrowLeft /></RouterLink>
      </Button>
      <h1 class="text-base font-semibold">멀티뷰</h1>
      <Badge variant="secondary">{{ selected.length }} / 4</Badge>
      <div class="flex-1" />
      <Button
        variant="ghost"
        size="icon"
        aria-label="방송 목록 새로고침"
        :disabled="refreshing"
        @click="refresh"
      >
        <RotateCcw />
      </Button>
      <Button
        variant="ghost"
        size="icon"
        aria-label="채팅 표시"
        :aria-pressed="chatVisible"
        @click="chatVisible = !chatVisible"
      >
        <MessageSquare />
      </Button>
      <Button variant="ghost" size="icon" aria-label="전체 화면 전환" @click="fullscreen">
        <Maximize />
      </Button>
    </header>

    <FieldGroup class="multiview-filters">
      <Field orientation="horizontal">
        <FieldLabel for="stream-scope">채널</FieldLabel>
        <NativeSelect id="stream-scope" v-model="scope" aria-label="채널 필터">
          <NativeSelectOption value="all">전체</NativeSelectOption>
          <NativeSelectOption value="favorites">즐겨찾기</NativeSelectOption>
        </NativeSelect>
      </Field>
      <Field orientation="horizontal">
        <FieldLabel for="stream-group">그룹</FieldLabel>
        <NativeSelect id="stream-group" v-model="groupFilter" aria-label="그룹 필터">
          <NativeSelectOption value="all">전체 그룹</NativeSelectOption>
          <NativeSelectOptGroup label="소속사">
            <NativeSelectOption
              v-for="group in groups.filter((g) => g.kind === 'agency')"
              :key="group.key"
              :value="group.key"
            >
              {{ group.name }}
            </NativeSelectOption>
          </NativeSelectOptGroup>
          <NativeSelectOptGroup label="유닛·그룹">
            <NativeSelectOption
              v-for="group in groups.filter((g) => g.kind === 'group')"
              :key="group.key"
              :value="group.key"
            >
              {{ group.name }}
            </NativeSelectOption>
          </NativeSelectOptGroup>
        </NativeSelect>
      </Field>
      <Button variant="outline" size="sm" :disabled="!visibleStreams.length" @click="addVisible">
        표시된 방송 담기
      </Button>
      <Field orientation="horizontal">
        <FieldLabel for="stream-layout">배치</FieldLabel>
        <NativeSelect id="stream-layout" v-model="layout" aria-label="영상 배치">
          <NativeSelectOption value="grid">균등 분할</NativeSelectOption>
          <NativeSelectOption value="focus">첫 방송 크게</NativeSelectOption>
        </NativeSelect>
      </Field>
      <span v-if="lastRead" class="text-xs text-muted-foreground">목록 갱신 {{ lastRead }}</span>
    </FieldGroup>

    <TooltipProvider :delay-duration="150">
      <section aria-label="방송 중인 채널" class="multiview-channels">
        <ResourceState
          :loading="loading"
          :error="error"
          :empty="!visibleStreams.length"
          title="확인된 생방송·예정 방송이 없어요"
          description="최근 15분 내 수집기가 확인한 방송을 표시합니다. 잠시 후 새로고침해 주세요."
          @retry="refresh"
        >
          <Tooltip v-for="stream in visibleStreams" :key="stream.video_id">
            <TooltipTrigger as-child>
              <Button
                variant="ghost"
                size="icon"
                class="stream-channel"
                :aria-label="`${stream.artist_name} ${stream.status === 'upcoming' ? '예정' : 'LIVE'}`"
                :aria-pressed="selected.some((s) => s.video_id === stream.video_id)"
                :title="`${stream.artist_name} · ${stream.title}`"
                @click="toggle(stream)"
              >
                <Avatar class="size-12">
                  <AvatarImage
                    :src="
                      avatarImageSource(
                        stream.avatar_url || '',
                        stream.avatar_variants,
                        48,
                        pixelRatio,
                      )
                    "
                    alt=""
                  />
                  <AvatarFallback>{{ stream.artist_name.slice(0, 2) }}</AvatarFallback>
                </Avatar>
                <Badge
                  :variant="stream.status === 'upcoming' ? 'upcoming' : 'live'"
                  class="stream-channel-time"
                  :data-status="stream.status || 'live'"
                >
                  {{ streamTime(stream, now) }}
                </Badge>
              </Button>
            </TooltipTrigger>
            <TooltipContent>
              <p>{{ stream.artist_name }}</p>
              <p>{{ stream.title }}</p>
              <p>
                {{ stream.status === 'upcoming' ? '시작까지' : '방송 시작 후' }}
                {{ streamTime(stream, now) }}
              </p>
            </TooltipContent>
          </Tooltip>
        </ResourceState>
      </section>
    </TooltipProvider>
    <p v-if="notice" class="px-4 py-2 text-sm" role="status">{{ notice }}</p>

    <div :class="cn('multiview-workspace', chatVisible && selected.length > 0 && 'has-chat')">
      <section
        :class="cn('multiview-videos', layout === 'focus' && 'focus-first')"
        :data-count="selected.length"
        aria-label="선택한 방송"
      >
        <ResourceState
          :empty="!selected.length"
          title="함께 볼 방송을 선택해 주세요"
          description="상단에서 최대 4개 방송을 선택할 수 있어요. 소리는 방송별 버튼으로 켜 주세요."
        />
        <article v-for="stream in selected" :key="stream.video_id" class="multiview-tile">
          <div class="multiview-tile-heading">
            <span class="min-w-0 flex-1 truncate" :title="stream.title">
              {{ stream.artist_name }} · {{ stream.title }}
            </span>
            <Button
              variant="ghost"
              size="icon-sm"
              :aria-label="`${stream.artist_name} 소리`"
              :aria-pressed="audioId === stream.video_id"
              @click="audioId = audioId === stream.video_id ? '' : stream.video_id"
            >
              <Volume2 v-if="audioId === stream.video_id" />
              <VolumeX v-else />
            </Button>
            <Button
              variant="ghost"
              size="icon-sm"
              :aria-label="`${stream.artist_name} 채팅 선택`"
              :aria-pressed="chatId === stream.video_id"
              @click="selectChat(stream.video_id)"
            >
              <MessageSquare />
            </Button>
            <Button
              variant="ghost"
              size="icon-sm"
              :aria-label="`${stream.artist_name} 닫기`"
              @click="remove(stream.video_id)"
            >
              <X />
            </Button>
          </div>
          <StreamPlayer :video-id="stream.video_id" :audible="audioId === stream.video_id" />
          <a
            :href="`https://www.youtube.com/watch?v=${stream.video_id}`"
            target="_blank"
            rel="noopener noreferrer"
            class="px-3 py-1 text-xs text-muted-foreground"
          >
            YouTube에서 열기 ↗
          </a>
        </article>
      </section>
      <aside v-if="chatVisible && chatStream" class="multiview-chat" aria-label="실시간 채팅">
        <FieldGroup class="p-3">
          <Field>
            <FieldLabel for="chat-stream">실시간 채팅</FieldLabel>
            <NativeSelect
              id="chat-stream"
              v-model="chatId"
              class="w-full"
              aria-label="채팅 방송 선택"
            >
              <NativeSelectOption
                v-for="stream in selected"
                :key="stream.video_id"
                :value="stream.video_id"
              >
                {{ stream.artist_name }} · {{ stream.title }}
              </NativeSelectOption>
            </NativeSelect>
          </Field>
        </FieldGroup>
        <p v-if="mobile" class="p-4 text-sm text-muted-foreground">
          모바일 웹에서는 YouTube 채팅을 삽입할 수 없어요. 아래 링크에서 채팅을 확인해 주세요.
        </p>
        <iframe
          v-else
          :key="chatUrl"
          :src="chatUrl"
          :title="`${chatStream.artist_name} 실시간 채팅`"
          referrerpolicy="strict-origin-when-cross-origin"
        />
        <Button as-child variant="outline" size="sm" class="m-3">
          <a
            :href="`https://www.youtube.com/watch?v=${chatStream.video_id}`"
            target="_blank"
            rel="noopener noreferrer"
          >
            YouTube에서 채팅 열기 ↗
          </a>
        </Button>
      </aside>
    </div>
    <p class="px-4 py-2 text-xs text-muted-foreground">
      브라우저가 자동재생을 막으면 영상의 재생 버튼을 눌러 주세요. 채팅 비활성화·로그인·외부 재생
      제한은 YouTube 설정을 따릅니다.
    </p>
  </div>
</template>
