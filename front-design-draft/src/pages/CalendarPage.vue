<script setup lang="ts">
import { computed, shallowRef, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { CalendarRoot, type DateValue } from 'reka-ui'
import { parseDate } from '@internationalized/date'
import { CalendarDays as CalendarIcon, Cake, ArrowUpRight } from '@lucide/vue'
import {
  CalendarCell,
  CalendarCellTrigger,
  CalendarGrid,
  CalendarGridBody,
  CalendarGridHead,
  CalendarGridRow,
  CalendarHeadCell,
  CalendarHeader,
  CalendarHeading,
  CalendarNextButton,
  CalendarPrevButton,
} from '@/components/ui/calendar'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Avatar, AvatarImage, AvatarFallback } from '@/components/ui/avatar'
import { ref } from 'vue'
import { api } from '@/api/client'
import type { CalendarEvent } from '@/api/types'
import { useResource } from '@/composables/useResource'
import { favoriteIds, calendarScope } from '@/composables/preferences'
import { calendarEvents, formatDate, monthKey, todayKey } from '@/lib/dates'
import { openOverlay } from '@/lib/overlays'
import ResourceState from '@/components/ResourceState.vue'
const route = useRoute()
const router = useRouter()
const month = computed(() => monthKey(route.query.month))
const placeholder = computed(() => parseDate(month.value))
const selected = shallowRef<DateValue>(
  parseDate(month.value.slice(0, 7) === todayKey().slice(0, 7) ? todayKey() : month.value),
)
watch(month, (value) => {
  if (!selected.value.toString().startsWith(value.slice(0, 7))) selected.value = parseDate(value)
})
const kinds = ref<string[]>(['concert', 'birthday'])
const { data, loading, error, reload } = useResource(async (signal) => {
  const [artists, concerts] = await Promise.all([api.artists(signal), api.concerts(signal)])
  return { artists, concerts }
})
const allEvents = computed(() => {
  if (!data.value) return []
  const year = Number(month.value.slice(0, 4))
  const events = [year - 1, year, year + 1].flatMap((y) =>
    calendarEvents(data.value!.artists, data.value!.concerts, y),
  )
  return [...new Map(events.map((e) => [`${e.id}-${e.date}`, e])).values()]
    .filter(
      (e) =>
        kinds.value.includes(e.kind) &&
        (calendarScope.value === 'all' || favoriteIds.value.includes(e.artist_id)),
    )
    .sort((a, b) => a.date.localeCompare(b.date))
})
const inMonth = computed(() =>
  allEvents.value.filter((e) => e.date.startsWith(month.value.slice(0, 7))),
)
const selectedEvents = computed(() => eventsOn(selected.value.toString()))
function eventsOn(date: string) {
  return allEvents.value.filter((e) => e.date === date)
}
function artist(id: number) {
  return data.value?.artists.find((a) => a.id === id)
}
function setMonth(value: DateValue) {
  const key = `${value.toString().slice(0, 7)}-01`
  if (!selected.value.toString().startsWith(key.slice(0, 7))) selected.value = parseDate(key)
  if (key !== month.value) router.push({ query: { ...route.query, month: key } })
}
function goToday() {
  selected.value = parseDate(todayKey())
  setMonth(selected.value)
}
function openEvent(event: CalendarEvent) {
  if (event.concert) openOverlay(router, route, 'event', event.concert.id)
  else router.push(`/artists/${event.artist_id}`)
}
</script>
<template>
  <div class="page-container calendar-page page-enter">
    <div class="page-heading">
      <p class="eyebrow">GOOD DAYS, GREAT MEMORIES</p>
      <h1>기다려지는 날들.</h1>
      <p>다음 공연과 특별한 생일, 놓치지 않도록.</p>
    </div>
    <div class="calendar-toolbar">
      <ToggleGroup
        type="single"
        :model-value="calendarScope"
        @update:model-value="
          (v) => {
            if (v) calendarScope = v as 'all' | 'favorites'
          }
        "
        variant="outline"
        aria-label="캘린더 아티스트 범위"
      >
        <ToggleGroupItem value="favorites">즐겨찾는 아티스트</ToggleGroupItem>
        <ToggleGroupItem value="all">전체 아티스트</ToggleGroupItem>
      </ToggleGroup>
      <ToggleGroup type="multiple" v-model="kinds" aria-label="일정 종류">
        <ToggleGroupItem value="concert">
          <CalendarIcon />
          공연
        </ToggleGroupItem>
        <ToggleGroupItem value="birthday">
          <Cake />
          생일
        </ToggleGroupItem>
      </ToggleGroup>
    </div>
    <ResourceState :loading="loading" :error="error" @retry="reload">
      <div class="calendar-layout">
        <section class="calendar-surface">
          <CalendarRoot
            v-slot="{ grid, weekDays }"
            locale="ko-KR"
            :week-starts-on="1"
            fixed-weeks
            :model-value="selected"
            :placeholder="placeholder"
            @update:model-value="
              (v) => {
                if (v) selected = v as DateValue
              }
            "
            @update:placeholder="setMonth"
          >
            <CalendarHeader class="mb-6 justify-between gap-3 px-0">
              <CalendarHeading>
                {{ formatDate(month, { day: undefined, year: 'numeric', month: 'long' }) }}
              </CalendarHeading>
              <div class="flex items-center gap-2">
                <Button variant="outline" size="sm" @click="goToday">오늘</Button>
                <CalendarPrevButton class="size-9" aria-label="이전 달" />
                <CalendarNextButton class="size-9" aria-label="다음 달" />
              </div>
            </CalendarHeader>
            <CalendarGrid v-for="m in grid" :key="m.value.toString()" class="schedule-grid">
              <CalendarGridHead>
                <CalendarGridRow>
                  <CalendarHeadCell v-for="day in weekDays" :key="day" class="flex-1">
                    {{ day }}
                  </CalendarHeadCell>
                </CalendarGridRow>
              </CalendarGridHead>
              <CalendarGridBody>
                <CalendarGridRow v-for="(week, index) in m.rows" :key="index">
                  <CalendarCell
                    v-for="day in week"
                    :key="day.toString()"
                    :date="day"
                    class="calendar-day-cell flex-1"
                  >
                    <CalendarCellTrigger
                      :day="day"
                      :month="m.value"
                      class="calendar-trigger h-full w-full flex-col justify-start gap-1 p-2"
                      :aria-label="`${formatDate(day.toString())}, ${eventsOn(day.toString()).length}개 일정`"
                    >
                      <span class="day-number">{{ day.day }}</span>
                      <span class="day-events" aria-hidden="true">
                        <span
                          v-for="event in eventsOn(day.toString()).slice(0, 2)"
                          :key="event.id"
                          class="day-event"
                        >
                          <component
                            :is="event.kind === 'birthday' ? Cake : CalendarIcon"
                            class="size-3"
                          />
                          <span>
                            {{
                              event.kind === 'birthday'
                                ? event.title
                                : artist(event.artist_id)?.name
                            }}
                          </span>
                        </span>
                        <span v-if="eventsOn(day.toString()).length > 2" class="day-more">
                          +{{ eventsOn(day.toString()).length - 2 }}
                        </span>
                      </span>
                    </CalendarCellTrigger>
                  </CalendarCell>
                </CalendarGridRow>
              </CalendarGridBody>
            </CalendarGrid>
          </CalendarRoot>
          <p class="calendar-footnote">공연은 가상 일정 · 생일은 공식 프로필 기준 · 한국 시간</p>
        </section>
        <aside class="calendar-agenda">
          <p class="eyebrow">ON THIS DAY</p>
          <h2>
            {{
              formatDate(selected.toString(), { year: undefined, month: 'long', day: 'numeric' })
            }}
            <span>
              {{
                formatDate(selected.toString(), {
                  year: undefined,
                  month: undefined,
                  day: undefined,
                  weekday: 'short',
                })
              }}
            </span>
          </h2>
          <ResourceState
            :empty="!selectedEvents.length"
            title="여유로운 하루네요"
            description="선택한 날짜에 일정이 없어요."
          >
            <div class="agenda-items">
              <button
                v-for="event in selectedEvents"
                :key="event.id"
                class="agenda-item"
                @click="openEvent(event)"
              >
                <Avatar class="size-11">
                  <AvatarImage
                    :src="artist(event.artist_id)?.image || ''"
                    :alt="artist(event.artist_id)?.name || ''"
                  />
                  <AvatarFallback>M</AvatarFallback>
                </Avatar>
                <div>
                  <Badge variant="outline">
                    {{ event.kind === 'birthday' ? '생일' : '샘플 공연' }}
                  </Badge>
                  <h3>{{ event.title }}</h3>
                  <p>{{ event.concert?.venue || '오늘의 주인공에게 축하를!' }}</p>
                </div>
                <ArrowUpRight class="size-4 shrink-0" />
              </button>
            </div>
          </ResourceState>
        </aside>
      </div>
      <section class="month-agenda">
        <div class="section-heading">
          <h2>
            이번 달의 일정
            <span>{{ inMonth.length }}</span>
          </h2>
        </div>
        <ResourceState
          :empty="!inMonth.length"
          title="이번 달은 아직 비어 있어요"
          description="다음 달을 살펴보거나 전체 아티스트로 전환해 보세요."
        >
          <div class="month-event-list">
            <button
              v-for="event in inMonth"
              :key="event.id"
              class="month-event"
              @click="openEvent(event)"
            >
              <span class="month-event-day">{{ event.date.slice(-2) }}</span>
              <component :is="event.kind === 'birthday' ? Cake : CalendarIcon" class="size-4" />
              <div>
                <h3>{{ event.title }}</h3>
                <p>{{ artist(event.artist_id)?.name }}</p>
              </div>
              <Badge variant="outline">
                {{ event.kind === 'birthday' ? '생일' : '샘플 공연' }}
              </Badge>
              <ArrowUpRight class="size-4 ml-auto" />
            </button>
          </div>
        </ResourceState>
      </section>
    </ResourceState>
  </div>
</template>
