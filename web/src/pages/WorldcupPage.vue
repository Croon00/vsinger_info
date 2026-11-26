<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ArrowUpRight,
  ChartNoAxesColumnIncreasing,
  Play,
  RotateCcw,
  Trophy,
  Undo2,
  X,
} from '@lucide/vue'
import { api } from '@/api/client'
import type { Artist, ExploredSong, SongKind as ApiSongKind } from '@/api/types'
import {
  percent,
  submitWorldcup,
  worldcupStats,
  WorldcupApiError,
  worldcupPoolSummary,
  type WorldcupSongStat,
} from '@/api/worldcup'
import { useResource } from '@/composables/useResource'
import { displayName } from '@/lib/display-name'
import { formatSubscribers } from '@/lib/subscribers'
import {
  availableSizes,
  choose,
  clientId,
  currentPair,
  drawSongs,
  isFinished,
  load,
  progress,
  ranking,
  save,
  start,
  submission,
  shuffle,
  toCandidates,
  undo,
  WORLDCUP_SIZES,
  type WorldcupDraw,
  type WorldcupMode,
  type WorldcupSize,
  type WorldcupSong,
  type WorldcupState,
} from '@/lib/worldcup'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Field, FieldGroup, FieldLabel } from '@/components/ui/field'
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import ResourceState from '@/components/ResourceState.vue'
import WorldcupRanking from '@/components/WorldcupRanking.vue'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'

type SongKind = Extract<ApiSongKind, 'original' | 'cover'>
const MODES: { value: WorldcupMode; label: string }[] = [
  { value: 'agency', label: '소속사' },
  { value: 'artists', label: '아티스트 선택' },
  { value: 'random', label: '무작위 섞기' },
]
const KINDS: { value: SongKind; label: string }[] = [
  { value: 'original', label: '오리지널' },
  { value: 'cover', label: '커버' },
]
const songKind = ref<SongKind>('original')
const mode = ref<WorldcupMode>('agency')
const agency = ref('')
const artistIds = ref<string[]>([])
const size = ref<WorldcupSize>(32)
const draw = ref<WorldcupDraw>('random')
const run = ref<WorldcupState | null>(load())
const playing = ref<string | null>(null)
const lowRes = ref(new Set<string>())
// A missing HD thumbnail is answered with a 120px grey placeholder, not an error.
function checkThumb(event: Event, videoId: string) {
  if ((event.target as HTMLImageElement).naturalWidth <= 120) lowRes.value.add(videoId)
}
const route = useRoute()
const router = useRouter()
const view = computed(() => (route.query.view === 'ranking' ? 'ranking' : 'play'))
function changeView(value: string | number) {
  router.replace({ query: { ...route.query, view: value === 'ranking' ? 'ranking' : undefined } })
}

const {
  data: artists,
  loading: artistsLoading,
  error: artistsError,
  reload: reloadArtists,
} = useResource((signal) => api.artists(signal))
const agencies = computed(() => {
  const counts = new Map<string, number>()
  for (const artist of artists.value ?? [])
    if (artist.agency) counts.set(artist.agency, (counts.get(artist.agency) ?? 0) + 1)
  return [...counts.keys()].sort().sort((a, b) => counts.get(b)! - counts.get(a)!)
})
// Agencies and artists are offered with their playable song counts (one cached API call).
const MIN_POOL = WORLDCUP_SIZES[0]
const {
  data: summary,
  loading: summaryLoading,
  error: summaryError,
  reload: reloadSummary,
} = useResource((signal) => worldcupPoolSummary(songKind.value, signal), [songKind])
const eligibleAgencies = computed(() =>
  (summary.value?.agencies ?? [])
    .filter((option) => option.count >= MIN_POOL)
    .sort((a, b) => b.count - a.count),
)
watch(eligibleAgencies, (options) => {
  if (!options.some((option) => option.name === agency.value)) agency.value = options[0]?.name ?? ''
})
// Originals credit approved groups (VESPERBELL, KMNZ, ...) as one artist, like the song tab;
// covers are credited to each member.
const artistOptions = computed(() =>
  [
    ...new Map(
      (artists.value ?? []).map((artist: Artist) => {
        const group = songKind.value === 'original' ? artist.original_song_group : null
        const option = group
          ? { id: group.id, name: group.name, display_name: '' }
          : { id: artist.id, name: artist.name, display_name: artist.display_name }
        return [option.id, option] as const
      }),
    ).values(),
  ].sort((a, b) =>
    (a.display_name || a.name).localeCompare(b.display_name || b.name, 'ko', { numeric: true }),
  ),
)
const pickableArtists = computed(() => {
  const counts = new Map((summary.value?.artists ?? []).map((item) => [item.id, item.count]))
  return artistOptions.value
    .map((option) => ({ ...option, count: counts.get(option.id) ?? 0 }))
    .filter((option) => option.count > 0)
})
watch(songKind, () => {
  artistIds.value = []
})

const headingKind = computed(() => {
  const kind = run.value ? (run.value.songKind ?? 'original') : songKind.value
  return kind === 'cover' ? '커버' : '오리지널'
})
const poolNoun = computed(() =>
  songKind.value === 'cover' ? '커버 영상' : 'MV가 있는 오리지널 곡',
)
const PAGE = 100
const MAX_PAGES = 20
// Large pools (thousands of covers) are sampled from random pages instead of read in full.
async function fetchPool(scope: string, ids: number[], signal: AbortSignal) {
  const read = (offset: number) =>
    api.songPage(
      songKind.value,
      scope,
      '',
      'high',
      offset,
      signal,
      ids,
      {},
      {},
      {
        limit: PAGE,
        publishedOnly: true,
      },
    )
  const first = await read(0)
  const pages = Math.ceil(first.total / PAGE)
  const offsets =
    pages <= MAX_PAGES
      ? Array.from({ length: pages - 1 }, (_, i) => (i + 1) * PAGE)
      : shuffle(Array.from({ length: pages - 1 }, (_, i) => (i + 1) * PAGE)).slice(0, MAX_PAGES - 1)
  const rest = await Promise.all(offsets.map(read))
  return toCandidates([first, ...rest].flatMap((page) => page.items as ExploredSong[]))
}
const {
  data: pool,
  loading: poolLoading,
  error: poolError,
  reload: reloadPool,
} = useResource(
  async (signal): Promise<WorldcupSong[]> => {
    if (mode.value === 'agency') return agency.value ? fetchPool(agency.value, [], signal) : []
    if (mode.value === 'artists')
      return artistIds.value.length ? fetchPool('all', artistIds.value.map(Number), signal) : []
    return fetchPool('all', [], signal)
  },
  [songKind, mode, agency, artistIds],
)
const sampled = computed(() => {
  const total =
    mode.value === 'agency'
      ? eligibleAgencies.value.find((option) => option.name === agency.value)?.count
      : mode.value === 'random'
        ? summary.value?.total
        : undefined
  return total != null && total > PAGE * MAX_PAGES ? total : null
})
const sizes = computed(() => availableSizes(pool.value?.length ?? 0))
watch(sizes, (options) => {
  if (options.length && !options.includes(size.value))
    size.value = options.includes(32) ? 32 : options[options.length - 1]
})
const poolArtists = computed(() => new Set((pool.value ?? []).map((song) => song.artist)).size)
const canStart = computed(() => !poolLoading.value && sizes.value.includes(size.value))
const label = computed(() => {
  if (mode.value === 'agency') return agency.value
  if (mode.value === 'random') return '무작위 아티스트'
  const names = artistOptions.value
    .filter((option) => artistIds.value.includes(String(option.id)))
    .map((option) => option.display_name || option.name)
  return names.length > 2
    ? `${names.slice(0, 2).join(', ')} 외 ${names.length - 2}명`
    : names.join(', ')
})

function begin() {
  if (!canStart.value || !pool.value) return
  // Random mixes cap each artist so one prolific singer cannot fill the bracket.
  const cap = mode.value === 'random' ? Math.max(2, Math.ceil(size.value / 8)) : undefined
  const songs = drawSongs(pool.value, size.value, draw.value, Math.random, cap)
  const kindLabel = songKind.value === 'cover' ? '커버' : '오리지널'
  run.value = start(
    `${label.value} ${kindLabel} · ${size.value}강`,
    songs,
    Math.random,
    mode.value,
    Date.now(),
    songKind.value,
  )
}
const pair = computed(() => (run.value ? currentPair(run.value) : null))
const step = computed(() => (run.value ? progress(run.value) : null))
const result = computed(() => (run.value && isFinished(run.value) ? ranking(run.value) : null))
watch(run, (value) => save(value), { deep: false })
watch(pair, () => {
  playing.value = null
})

function pick(side: 0 | 1) {
  if (run.value) run.value = choose(run.value, side)
}
function back() {
  if (run.value) run.value = undo(run.value)
}
function quit() {
  run.value = null
  playing.value = null
  winnerStat.value = null
  submitError.value = ''
}

// Finished runs are sent once (the server de-duplicates retries by submission ID).
const winnerStat = ref<WorldcupSongStat | null>(null)
const submitting = ref(false)
const submitError = ref('')
async function send() {
  const state = run.value
  if (!state || !isFinished(state) || submitting.value) return
  submitting.value = true
  submitError.value = ''
  try {
    if (!state.submitted) {
      const saved = await submitWorldcup(submission(state, clientId()))
      if (run.value?.submissionId === state.submissionId) run.value = { ...state, submitted: true }
      winnerStat.value = saved.winner
    } else {
      const winner = ranking(state)!.winner.videoId
      winnerStat.value =
        (await worldcupStats({ songKind: state.songKind, videoIds: [winner], limit: 1 }))
          .items[0] ?? null
    }
  } catch (e) {
    submitError.value = e instanceof Error ? e.message : '결과를 저장하지 못했어요.'
    // An invalid bracket will never be accepted; stop retrying it.
    if (e instanceof WorldcupApiError && e.status === 422 && run.value)
      run.value = { ...run.value, submitted: true }
  } finally {
    submitting.value = false
  }
}
watch(
  () => run.value && isFinished(run.value) && run.value.submissionId,
  (finished) => {
    if (finished) send()
  },
  { immediate: true },
)
function embedUrl(song: WorldcupSong) {
  const params = new URLSearchParams({
    autoplay: '1',
    playsinline: '1',
    rel: '0',
    origin: window.location.origin,
  })
  return `https://www.youtube.com/embed/${song.videoId}?${params}`
}
function views(song: WorldcupSong) {
  return song.viewCount == null ? '' : `조회수 ${formatSubscribers(song.viewCount)}회`
}
</script>

<template>
  <div class="page-container page-enter worldcup-page">
    <div class="page-heading">
      <h1>{{ headingKind }} 곡 월드컵</h1>
    </div>
    <Tabs :model-value="view" @update:model-value="changeView">
      <TabsList variant="line" class="mb-6">
        <TabsTrigger value="play">
          <Trophy />
          월드컵
        </TabsTrigger>
        <TabsTrigger value="ranking">
          <ChartNoAxesColumnIncreasing />
          랭킹
        </TabsTrigger>
      </TabsList>
      <TabsContent value="ranking">
        <WorldcupRanking :agencies="agencies" />
      </TabsContent>
      <TabsContent value="play">
        <section v-if="!run" class="worldcup-setup" aria-label="월드컵 설정">
          <p class="worldcup-intro">
            {{ poolNoun }} 중에서 두 곡씩 듣고 더 좋은 곡을 골라 보세요. 진행 상황은 이 브라우저에
            저장돼요.
          </p>
          <FieldGroup class="worldcup-fields">
            <Field>
              <FieldLabel>곡 종류</FieldLabel>
              <ToggleGroup
                type="single"
                variant="outline"
                :model-value="songKind"
                aria-label="곡 종류"
                @update:model-value="(value) => value && (songKind = value as SongKind)"
              >
                <ToggleGroupItem v-for="option in KINDS" :key="option.value" :value="option.value">
                  {{ option.label }}
                </ToggleGroupItem>
              </ToggleGroup>
            </Field>
            <Field>
              <FieldLabel>후보 범위</FieldLabel>
              <ToggleGroup
                type="single"
                variant="outline"
                :model-value="mode"
                aria-label="후보 범위"
                @update:model-value="(value) => value && (mode = value as WorldcupMode)"
              >
                <ToggleGroupItem v-for="option in MODES" :key="option.value" :value="option.value">
                  {{ option.label }}
                </ToggleGroupItem>
              </ToggleGroup>
            </Field>

            <ResourceState
              v-if="mode !== 'random'"
              :loading="artistsLoading || summaryLoading"
              :error="artistsError || summaryError"
              :empty="mode === 'agency' ? !eligibleAgencies.length : !pickableArtists.length"
              :title="
                mode === 'agency'
                  ? '월드컵을 열 수 있는 소속사가 없어요'
                  : `${poolNoun}을 가진 아티스트가 없어요`
              "
              :description="
                mode === 'agency' ? `${poolNoun}이 ${MIN_POOL}곡 이상인 소속사만 보여요.` : ''
              "
              @retry="artistsError ? reloadArtists() : reloadSummary()"
            >
              <Field v-if="mode === 'agency'">
                <FieldLabel for="worldcup-agency">소속사</FieldLabel>
                <Select v-model="agency">
                  <SelectTrigger id="worldcup-agency" class="worldcup-select" aria-label="소속사">
                    <SelectValue placeholder="소속사 선택" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectGroup>
                      <SelectItem
                        v-for="option in eligibleAgencies"
                        :key="option.name"
                        :value="option.name"
                      >
                        {{ option.name }} · {{ option.count.toLocaleString('ko-KR') }}곡
                      </SelectItem>
                    </SelectGroup>
                  </SelectContent>
                </Select>
                <p class="worldcup-hint">
                  {{ poolNoun }}이 {{ MIN_POOL }}곡 이상인 소속사만 보여요.
                </p>
              </Field>
              <Field v-else>
                <FieldLabel for="worldcup-artists">아티스트</FieldLabel>
                <Select v-model="artistIds" multiple>
                  <SelectTrigger
                    id="worldcup-artists"
                    class="worldcup-select"
                    aria-label="아티스트"
                  >
                    <SelectValue>
                      {{
                        artistIds.length ? `아티스트 ${artistIds.length}명 선택` : '아티스트 선택'
                      }}
                    </SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    <SelectGroup>
                      <SelectItem
                        v-for="artist in pickableArtists"
                        :key="artist.id"
                        :value="String(artist.id)"
                      >
                        {{ displayName(artist.name, artist.display_name) }} · {{ artist.count }}곡
                      </SelectItem>
                    </SelectGroup>
                  </SelectContent>
                </Select>
                <p class="worldcup-hint">
                  {{ poolNoun }}이 있는 아티스트만 보여요. 합쳐서 {{ MIN_POOL }}곡 이상이면 시작할
                  수 있어요.
                </p>
              </Field>
            </ResourceState>

            <Field>
              <FieldLabel>규모</FieldLabel>
              <ToggleGroup
                type="single"
                variant="outline"
                :model-value="String(size)"
                aria-label="월드컵 규모"
                @update:model-value="(value) => value && (size = Number(value) as WorldcupSize)"
              >
                <ToggleGroupItem
                  v-for="option in WORLDCUP_SIZES"
                  :key="option"
                  :value="String(option)"
                  :disabled="!sizes.includes(option)"
                >
                  {{ option }}강
                </ToggleGroupItem>
              </ToggleGroup>
            </Field>
            <Field>
              <FieldLabel>후보 뽑기</FieldLabel>
              <ToggleGroup
                type="single"
                variant="outline"
                :model-value="draw"
                aria-label="후보 뽑기"
                @update:model-value="(value) => value && (draw = value as WorldcupDraw)"
              >
                <ToggleGroupItem value="random">무작위</ToggleGroupItem>
                <ToggleGroupItem value="popular">조회수 상위</ToggleGroupItem>
              </ToggleGroup>
            </Field>
          </FieldGroup>

          <div class="worldcup-start">
            <p class="worldcup-pool" role="status" aria-live="polite">
              <template v-if="poolLoading">후보 곡을 불러오는 중…</template>
              <template v-else-if="poolError">
                후보 곡을 불러오지 못했어요.
                <Button variant="link" size="sm" @click="reloadPool">다시 시도</Button>
              </template>
              <template v-else-if="mode === 'artists' && !artistIds.length">
                아티스트를 한 명 이상 골라 주세요.
              </template>
              <template v-else>
                {{ poolNoun }} {{ (pool?.length ?? 0).toLocaleString('ko-KR') }}곡 · 아티스트
                {{ poolArtists }}명
                <template v-if="sampled">
                  (전체 {{ sampled.toLocaleString('ko-KR') }}곡 중 무작위 표본)
                </template>
                <span v-if="(pool?.length ?? 0) < 16">
                  —
                  {{
                    mode === 'artists'
                      ? '16곡 이상이 되도록 아티스트를 더 골라 주세요.'
                      : '16곡 이상이어야 시작할 수 있어요.'
                  }}
                </span>
              </template>
            </p>
            <Button size="lg" :disabled="!canStart" @click="begin">
              <Trophy data-icon="inline-start" />
              {{ size }}강 시작하기
            </Button>
          </div>
        </section>

        <section v-else-if="pair && step" class="worldcup-play" aria-label="월드컵 대결">
          <div class="worldcup-status">
            <div>
              <p class="worldcup-label">{{ run.label }}</p>
              <h2 class="worldcup-round">
                {{ step.round }}
                <span>{{ step.match }} / {{ step.matches }}</span>
              </h2>
            </div>
            <div class="worldcup-actions">
              <Button variant="outline" size="sm" :disabled="!run.history.length" @click="back">
                <Undo2 data-icon="inline-start" />
                되돌리기
              </Button>
              <Button variant="ghost" size="sm" @click="quit">
                <X data-icon="inline-start" />
                그만두기
              </Button>
            </div>
          </div>
          <div
            class="worldcup-progress"
            role="progressbar"
            :aria-valuenow="step.done"
            :aria-valuemin="0"
            :aria-valuemax="step.total"
            :aria-label="`전체 ${step.total}경기 중 ${step.done}경기 완료`"
          >
            <span :style="{ width: `${(step.done / step.total) * 100}%` }" />
          </div>
          <div class="worldcup-match">
            <template v-for="(song, side) in pair" :key="song.key">
              <div v-if="side === 1" class="worldcup-vs" aria-hidden="true">VS</div>
              <article :class="['worldcup-card', side === 0 ? 'worldcup-left' : 'worldcup-right']">
                <div class="worldcup-media">
                  <iframe
                    v-if="playing === song.key"
                    :src="embedUrl(song)"
                    :title="`${song.title} YouTube 재생`"
                    allow="autoplay; encrypted-media; picture-in-picture; fullscreen"
                    allowfullscreen
                    referrerpolicy="strict-origin-when-cross-origin"
                  />
                  <button
                    v-else
                    type="button"
                    class="worldcup-thumb"
                    :aria-label="`${song.title} 듣기`"
                    @click="playing = song.key"
                  >
                    <!-- Large cards want the HD thumbnail; older videos only have hqdefault. -->
                    <img
                      :src="`https://i.ytimg.com/vi/${song.videoId}/${lowRes.has(song.videoId) ? 'hqdefault' : 'maxresdefault'}.jpg`"
                      alt=""
                      width="1280"
                      height="720"
                      @load="checkThumb($event, song.videoId)"
                      @error="lowRes.add(song.videoId)"
                    />
                    <span class="live-play" aria-hidden="true"><Play fill="currentColor" /></span>
                  </button>
                </div>
                <div class="worldcup-card-body">
                  <h3 class="worldcup-title">{{ song.title }}</h3>
                  <p class="worldcup-artist">{{ song.artist }}</p>
                  <p v-if="views(song)" class="worldcup-views">{{ views(song) }}</p>
                </div>
                <Button
                  size="lg"
                  class="worldcup-pick"
                  :aria-label="`${song.title} 선택`"
                  @click="pick(side as 0 | 1)"
                >
                  선택
                </Button>
              </article>
            </template>
          </div>
        </section>

        <section v-else-if="result" class="worldcup-result" aria-label="월드컵 결과">
          <p class="worldcup-label">{{ run.label }}</p>
          <article class="worldcup-winner">
            <div class="worldcup-media">
              <iframe
                v-if="playing === result.winner.key"
                :src="embedUrl(result.winner)"
                :title="`${result.winner.title} YouTube 재생`"
                allow="autoplay; encrypted-media; picture-in-picture; fullscreen"
                allowfullscreen
                referrerpolicy="strict-origin-when-cross-origin"
              />
              <button
                v-else
                type="button"
                class="worldcup-thumb"
                :aria-label="`${result.winner.title} 듣기`"
                @click="playing = result.winner.key"
              >
                <img
                  :src="`https://i.ytimg.com/vi/${result.winner.videoId}/hqdefault.jpg`"
                  alt=""
                  width="480"
                  height="360"
                />
                <span class="live-play" aria-hidden="true"><Play fill="currentColor" /></span>
              </button>
            </div>
            <div class="worldcup-card-body">
              <Badge class="worldcup-badge">
                <Trophy data-icon="inline-start" />
                우승
              </Badge>
              <h2 class="worldcup-title">{{ result.winner.title }}</h2>
              <p class="worldcup-artist">{{ result.winner.artist }}</p>
              <p v-if="views(result.winner)" class="worldcup-views">{{ views(result.winner) }}</p>
              <p v-if="winnerStat" class="worldcup-winner-stats">
                전체 {{ winnerStat.appearances.toLocaleString('ko-KR') }}판 출전 · 우승
                {{ winnerStat.championships.toLocaleString('ko-KR') }}회 ({{
                  percent(winnerStat.championship_rate)
                }}) · 1:1 승률 {{ percent(winnerStat.match_win_rate) }} ({{
                  winnerStat.match_wins
                }}승 {{ winnerStat.match_losses }}패)
              </p>
              <p v-else-if="submitting" class="worldcup-winner-stats" role="status">
                결과를 집계하는 중…
              </p>
              <p v-else-if="submitError" class="worldcup-winner-stats" role="alert">
                {{ submitError }}
                <Button variant="link" size="sm" @click="send">다시 시도</Button>
              </p>
              <Button as-child variant="outline" size="sm">
                <a
                  :href="`https://www.youtube.com/watch?v=${result.winner.videoId}`"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  YouTube에서 보기
                  <ArrowUpRight data-icon="inline-end" />
                </a>
              </Button>
            </div>
          </article>
          <div class="worldcup-ranks">
            <div v-if="result.runnerUp">
              <h3>준우승</h3>
              <p>
                {{ result.runnerUp.title }}
                <span>{{ result.runnerUp.artist }}</span>
              </p>
            </div>
            <div v-if="result.semifinal.length">
              <h3>4강</h3>
              <p v-for="song in result.semifinal" :key="song.key">
                {{ song.title }}
                <span>{{ song.artist }}</span>
              </p>
            </div>
            <div v-if="result.quarterfinal.length">
              <h3>8강</h3>
              <p v-for="song in result.quarterfinal" :key="song.key">
                {{ song.title }}
                <span>{{ song.artist }}</span>
              </p>
            </div>
          </div>
          <div class="worldcup-result-actions">
            <Button size="lg" @click="quit">
              <RotateCcw data-icon="inline-start" />
              새 월드컵
            </Button>
            <Button size="lg" variant="outline" @click="changeView('ranking')">
              <ChartNoAxesColumnIncreasing data-icon="inline-start" />
              랭킹 보기
            </Button>
          </div>
        </section>
      </TabsContent>
    </Tabs>
  </div>
</template>
