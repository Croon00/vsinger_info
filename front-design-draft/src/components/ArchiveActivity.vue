<script setup lang="ts">
import { computed, ref } from 'vue'
import { VisArea, VisAxis, VisXYContainer } from '@unovis/vue'
import type { Live } from '@/api/types'
import { archiveActivity, type ActivityPeriod } from '@/lib/archive-activity'
import {
  ChartContainer,
  ChartTooltip,
  ChartCrosshair,
  ChartTooltipContent,
  componentToString,
  type ChartConfig,
} from '@/components/ui/chart'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
const props = defineProps<{ lives: Live[] }>()
const period = ref<ActivityPeriod>('6M')
const data = computed(() => archiveActivity(props.lives, period.value))
type Month = ReturnType<typeof archiveActivity>[number]
const config = { count: { label: '아카이브', color: 'var(--chart-2)' } } satisfies ChartConfig
// Reserve at least 20% above the peak and keep four evenly spaced integer ticks.
const yStep = computed(() =>
  Math.max(1, Math.ceil((Math.max(...data.value.map((d) => d.count)) * 1.2) / 4)),
)
const maximum = computed(() => yStep.value * 4)
const total = computed(() => data.value.reduce((sum, d) => sum + d.count, 0))
const ticks = computed(() => (data.value.length > 1 ? [0, data.value.length - 1] : [0]))
const tickLabel = (index: number) => data.value[Math.round(index)]?.month.replace('-', '.') ?? ''
const tooltip = componentToString(config, ChartTooltipContent, {
  labelFormatter: (index: number | Date) => tickLabel(Number(index)),
})
</script>
<template>
  <section class="archive-activity" aria-labelledby="activity-heading">
    <div class="section-heading">
      <h2 id="activity-heading">활동량</h2>
      <ToggleGroup
        type="single"
        :model-value="period"
        variant="outline"
        aria-label="활동량 기간"
        @update:model-value="
          (value) => {
            if (value) period = value as ActivityPeriod
          }
        "
      >
        <ToggleGroupItem
          v-for="option in ['6M', '12M', 'All']"
          :key="option"
          :value="option"
          size="sm"
        >
          {{ option === '12M' ? '1Y' : option }}
        </ToggleGroupItem>
      </ToggleGroup>
    </div>
    <ChartContainer :config="config" class="activity-chart" aria-hidden="true">
      <VisXYContainer :data="data" :height="220" :y-domain="[0, maximum]" :duration="0">
        <VisArea
          :x="(d: Month) => d.index"
          :y="(d: Month) => d.count"
          :color="config.count.color"
          curve-type="monotoneX"
          :opacity="0.18"
          :line="true"
          :line-width="2"
          :line-color="config.count.color"
          :duration="0"
        />
        <VisAxis
          type="x"
          :tick-values="ticks"
          :tick-format="tickLabel"
          :grid-line="false"
          :duration="0"
        />
        <VisAxis
          type="y"
          :tick-values="Array.from({ length: 5 }, (_, i) => i * yStep)"
          :duration="0"
        />
        <ChartTooltip />
        <ChartCrosshair :template="tooltip" :color="config.count.color" :duration="0" />
      </VisXYContainer>
    </ChartContainer>
    <p v-if="!total" class="statistics-note">이 기간에 등록된 아카이브가 없습니다.</p>
    <table class="sr-only" aria-label="월별 아카이브 개수">
      <thead>
        <tr>
          <th>월</th>
          <th>아카이브 개수</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="month in data" :key="month.month">
          <th>{{ month.month }}</th>
          <td>{{ month.count }}</td>
        </tr>
      </tbody>
    </table>
  </section>
</template>
