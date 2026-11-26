<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ChevronDown, Music2 } from '@lucide/vue'
import { useResource } from '@/composables/useResource'
import {
  percent,
  worldcupStats,
  type WorldcupSongKind,
  type WorldcupSongStat,
  type WorldcupStatOrder,
} from '@/api/worldcup'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import ResourceState from '@/components/ResourceState.vue'

const props = defineProps<{ agencies: string[] }>()
const PAGE = 50
// Rates from one or two runs swing wildly, so rate rankings need a few appearances.
const RATE_MINIMUM = 3
const songKind = ref<WorldcupSongKind>('original')
const scope = ref('all')
const order = ref<WorldcupStatOrder>('championships')
const minimum = computed(() => (order.value === 'championships' ? 1 : RATE_MINIMUM))
const extra = ref<WorldcupSongStat[]>([])
const moreLoading = ref(false)
const moreError = ref('')
const failed = ref(new Set<string>())

const { data, loading, error, reload } = useResource(
  (signal) =>
    worldcupStats(
      {
        songKind: songKind.value,
        agency: scope.value === 'all' ? undefined : scope.value,
        order: order.value,
        minAppearances: minimum.value,
        limit: PAGE,
      },
      signal,
    ),
  [songKind, scope, order],
)
watch(data, () => {
  extra.value = []
  moreError.value = ''
})
const rows = computed(() => [...(data.value?.items ?? []), ...extra.value])

async function loadMore() {
  if (moreLoading.value || !data.value) return
  const initial = data.value
  moreLoading.value = true
  moreError.value = ''
  try {
    const page = await worldcupStats({
      songKind: songKind.value,
      agency: scope.value === 'all' ? undefined : scope.value,
      order: order.value,
      minAppearances: minimum.value,
      offset: rows.value.length,
      limit: PAGE,
    })
    if (data.value === initial) extra.value.push(...page.items)
  } catch (e) {
    moreError.value = e instanceof Error ? e.message : '랭킹을 더 불러오지 못했어요.'
  } finally {
    moreLoading.value = false
  }
}
</script>

<template>
  <section class="worldcup-ranking" aria-label="월드컵 랭킹">
    <div class="worldcup-ranking-filters">
      <Select v-model="songKind">
        <SelectTrigger class="worldcup-select" aria-label="랭킹 곡 종류">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectGroup>
            <SelectItem value="original">오리지널</SelectItem>
            <SelectItem value="cover">커버</SelectItem>
          </SelectGroup>
        </SelectContent>
      </Select>
      <Select v-model="scope">
        <SelectTrigger class="worldcup-select" aria-label="랭킹 범위">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectGroup>
            <SelectItem value="all">전체</SelectItem>
            <SelectItem v-for="name in props.agencies" :key="name" :value="name">
              {{ name }}
            </SelectItem>
          </SelectGroup>
        </SelectContent>
      </Select>
      <Select v-model="order">
        <SelectTrigger class="worldcup-select" aria-label="랭킹 정렬">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectGroup>
            <SelectItem value="championships">우승 횟수</SelectItem>
            <SelectItem value="championship_rate">우승 비율</SelectItem>
            <SelectItem value="match_win_rate">1:1 승률</SelectItem>
          </SelectGroup>
        </SelectContent>
      </Select>
    </div>
    <p class="worldcup-hint">
      <template v-if="data">전체 {{ data.total_runs.toLocaleString('ko-KR') }}판 집계 ·</template>
      우승 비율은 우승 횟수 ÷ 출전한 판, 1:1 승률은 이긴 대결 ÷ 전체 대결이에요.
      <template v-if="minimum > 1">출전 {{ minimum }}판 이상인 곡만 보여요.</template>
    </p>
    <ResourceState
      :loading="loading"
      :error="error"
      :empty="!rows.length"
      title="아직 집계된 기록이 없어요"
      description="월드컵을 끝까지 마치면 결과가 랭킹에 더해져요."
      @retry="reload"
    >
      <ol class="worldcup-rank-list">
        <li v-for="(song, index) in rows" :key="song.video_id" class="worldcup-rank-row">
          <span class="worldcup-rank-number">{{ index + 1 }}</span>
          <a
            class="worldcup-rank-thumb"
            :href="`https://www.youtube.com/watch?v=${song.video_id}`"
            target="_blank"
            rel="noopener noreferrer"
            :aria-label="`${song.title_ko || song.title} YouTube에서 보기`"
          >
            <img
              v-if="!failed.has(song.video_id)"
              :src="`https://i.ytimg.com/vi/${song.video_id}/mqdefault.jpg`"
              alt=""
              width="320"
              height="180"
              loading="lazy"
              @error="failed.add(song.video_id)"
            />
            <Music2 v-else aria-hidden="true" />
          </a>
          <div class="worldcup-rank-song">
            <p class="worldcup-rank-title">{{ song.title_ko || song.title }}</p>
            <p class="worldcup-rank-artist">{{ song.artist_name }}</p>
          </div>
          <dl class="worldcup-rank-stats">
            <div>
              <dt>우승</dt>
              <dd>{{ song.championships.toLocaleString('ko-KR') }}회</dd>
            </div>
            <div>
              <dt>우승 비율</dt>
              <dd>{{ percent(song.championship_rate) }}</dd>
            </div>
            <div>
              <dt>1:1 승률</dt>
              <dd :title="`${song.match_wins}승 ${song.match_losses}패`">
                {{ percent(song.match_win_rate) }}
              </dd>
            </div>
            <div>
              <dt>출전</dt>
              <dd>{{ song.appearances.toLocaleString('ko-KR') }}판</dd>
            </div>
          </dl>
        </li>
      </ol>
      <Button
        v-if="(data?.total ?? 0) > rows.length"
        variant="outline"
        class="mx-auto mt-6 flex"
        :disabled="moreLoading"
        @click="loadMore"
      >
        더보기
        <ChevronDown data-icon="inline-end" />
      </Button>
      <p v-if="moreError" role="alert" class="mt-3 text-sm text-destructive">{{ moreError }}</p>
    </ResourceState>
  </section>
</template>
