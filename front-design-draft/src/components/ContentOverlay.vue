<script setup lang="ts">
import { computed, nextTick, watch } from 'vue'
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
import { ref } from 'vue'
import { api } from '@/api/client'
import { useResource } from '@/composables/useResource'
import { formatDate } from '@/lib/dates'
import ResourceState from './ResourceState.vue'
import ArtistAvatar from './ArtistAvatar.vue'
const route = useRoute()
const router = useRouter()
const mobile = useMediaQuery('(max-width: 768px)')
const mode = computed(() => (route.query.lyrics ? 'lyrics' : 'event'))
const itemId = computed(() => String(route.query.lyrics || route.query.event || ''))
const open = computed(() => !!itemId.value)
const visibleLyrics = ref<string[]>(['original', 'translation'])
let opener: HTMLElement | null = null
watch(
  open,
  (value) => {
    if (value) opener = document.activeElement as HTMLElement
  },
  { flush: 'sync' },
)
const { data, loading, error, reload } = useResource(
  async (signal) => {
    if (!itemId.value) return null
    if (mode.value === 'lyrics')
      return { lyrics: await api.lyrics(itemId.value, signal), concert: null, artist: null }
    const [concerts, artists] = await Promise.all([api.concerts(signal), api.artists(signal)])
    const concert = concerts.find((c) => String(c.id) === itemId.value)
    if (!concert) throw new Error('찾으시는 공연이 없어요.')
    return { lyrics: null, concert, artist: artists.find((a) => a.id === concert.artist_id) }
  },
  [itemId, mode],
)
const title = computed(
  () =>
    data.value?.lyrics?.original_title ||
    data.value?.concert?.title ||
    (mode.value === 'lyrics' ? '가사' : '공연 정보'),
)
function close(value: boolean) {
  if (value) return
  if (window.history.state?.draftOverlay) router.back()
  else router.replace({ query: { ...route.query, event: undefined, lyrics: undefined } })
}
async function restoreFocus(event: Event) {
  event.preventDefault()
  await nextTick()
  ;(opener?.isConnected ? opener : document.querySelector<HTMLElement>('#main-content'))?.focus()
}
</script>
<template>
  <component :is="mobile ? Drawer : Dialog" :open="open" @update:open="close">
    <component
      :is="mobile ? DrawerContent : DialogContent"
      class="content-overlay sm:max-w-2xl"
      @close-auto-focus="restoreFocus"
    >
      <component :is="mobile ? DrawerHeader : DialogHeader" class="pr-8">
        <component :is="mobile ? DrawerTitle : DialogTitle">{{ title }}</component>
        <component :is="mobile ? DrawerDescription : DialogDescription">
          {{
            mode === 'lyrics'
              ? '노래 속에 담긴 문장을 함께 읽어보세요.'
              : '무대에서 만나는 다음 순간.'
          }}
        </component>
      </component>
      <DrawerClose v-if="mobile" as-child>
        <Button variant="ghost" size="icon" class="absolute top-6 right-5" aria-label="닫기">
          <X />
        </Button>
      </DrawerClose>
      <div class="overlay-scroll">
        <ResourceState :loading="loading" :error="error" @retry="reload">
          <div v-if="data?.lyrics" class="lyrics-content">
            <div class="lyrics-toolbar">
              <Badge variant="secondary">샘플 가사</Badge>
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
            <p class="sample-explanation">
              화면 확인용으로 작성한 문장입니다. 실제 곡의 가사가 아닙니다.
            </p>
            <div class="lyric-stanzas">
              <div
                v-for="(line, i) in data.lyrics.original_lyrics.split('\n')"
                :key="i"
                class="lyric-line"
              >
                <p v-if="visibleLyrics.includes('original')" lang="ja">{{ line }}</p>
                <p v-if="visibleLyrics.includes('pronunciation')" class="lyric-pronunciation">
                  {{ data.lyrics.pronunciation_ko.split('\n')[i] }}
                </p>
                <p v-if="visibleLyrics.includes('translation')" class="lyric-translation">
                  {{ data.lyrics.translation_ko.split('\n')[i] }}
                </p>
              </div>
              <p v-if="!visibleLyrics.length" class="text-muted-foreground">
                표시할 언어를 선택해 주세요.
              </p>
            </div>
          </div>
          <div v-if="data?.concert" class="concert-detail">
            <div class="concert-detail-art">
              <ArtistAvatar v-if="data.artist" :artist="data.artist" />
              <div>
                <Badge variant="secondary">샘플 일정</Badge>
                <h3>{{ data.artist?.name }}</h3>
                <p>OFFLINE LIVE</p>
              </div>
            </div>
            <p class="sample-explanation">
              디자인 테스트용 가상 공연입니다. 실제 공연 일정이 아닙니다.
            </p>
            <dl class="concert-facts">
              <div>
                <dt>
                  <CalendarDays />
                  일시
                </dt>
                <dd>
                  {{
                    formatDate(data.concert.starts_at, {
                      weekday: 'short',
                      hour: '2-digit',
                      minute: '2-digit',
                    })
                  }}
                  <small>한국·일본 시간 (UTC+9)</small>
                </dd>
              </div>
              <div>
                <dt>
                  <MapPin />
                  장소
                </dt>
                <dd>
                  {{ data.concert.venue }}
                  <small>{{ data.concert.city }}</small>
                </dd>
              </div>
              <div>
                <dt>
                  <Ticket />
                  티켓
                </dt>
                <dd>
                  {{ data.concert.price_text }}
                  <small>샘플 가격 · 실제 판매하지 않습니다</small>
                </dd>
              </div>
            </dl>
            <Button v-if="data.artist" as-child class="w-full">
              <a :href="data.artist.official_url" target="_blank" rel="noopener noreferrer">
                아티스트 공식 사이트
                <ArrowUpRight data-icon="inline-end" />
              </a>
            </Button>
          </div>
        </ResourceState>
      </div>
    </component>
  </component>
</template>
