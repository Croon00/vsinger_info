<script setup lang="ts">
import { computed, ref, shallowRef, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { CalendarRoot, type DateValue } from 'reka-ui'
import { parseDate } from '@internationalized/date'
import { useMediaQuery } from '@vueuse/core'
import { CalendarDays as CalendarIcon, Cake, ChevronRight } from '@lucide/vue'
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
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardFooter,
} from '@/components/ui/card'
import { Separator } from '@/components/ui/separator'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import ArtistAvatar from '@/components/ArtistAvatar.vue'
import { api } from '@/api/client'
import type { CalendarEvent } from '@/api/types'
import { useResource } from '@/composables/useResource'
import { favoriteIds, calendarScope } from '@/composables/preferences'
import { calendarEvents, formatDate, monthKey, todayKey } from '@/lib/dates'
import { openOverlay } from '@/lib/overlays'
import ResourceState from '@/components/ResourceState.vue'
const route = useRoute()
const router = useRouter()
const mobile = useMediaQuery('(max-width: 768px)')
const dayChosen = ref(false)
const month = computed(() => monthKey(route.query.month))
const placeholder = computed(() => parseDate(month.value))
const selected = shallowRef<DateValue>(
  parseDate(month.value.slice(0, 7) === todayKey().slice(0, 7) ? todayKey() : month.value),
)
watch(month, (value) => {
  if (!selected.value.toString().startsWith(value.slice(0, 7))) {
    dayChosen.value = false
    selected.value = parseDate(value)
  }
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
const visibleEvents = computed(() => (dayChosen.value ? selectedEvents.value : inMonth.value))
const agendaTitle = computed(() =>
  dayChosen.value
    ? formatDate(selected.value.toString(), {
        year: undefined,
        month: 'long',
        day: 'numeric',
        weekday: 'short',
      })
    : Number(month.value.slice(5, 7)) + '월 일정',
)
function eventsOn(date: string) {
  return allEvents.value.filter((e) => e.date === date)
}
function artist(id: number) {
  return data.value?.artists.find((a) => a.id === id)
}
async function setMonth(value: DateValue) {
  const key = `${value.toString().slice(0, 7)}-01`
  if (key !== month.value) await router.push({ query: { ...route.query, month: key } })
}
async function goToday() {
  selected.value = parseDate(todayKey())
  dayChosen.value = true
  await setMonth(selected.value)
}
async function chooseDate(value: DateValue | undefined) {
  if (!value) return
  selected.value = value
  dayChosen.value = true
  await setMonth(value)
}
function openEvent(event: CalendarEvent) {
  if (event.concert) openOverlay(router, route, 'event', event.concert.id)
  else router.push(`/artists/${event.artist_id}`)
}
</script>
<template>
  <div class="page-container calendar-page page-enter">
    <div class="page-heading calendar-page-heading">
      <h1>캘린더</h1>
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
        <ToggleGroupItem value="favorites" aria-label="즐겨찾는 아티스트">즐겨찾기</ToggleGroupItem>
        <ToggleGroupItem value="all" aria-label="전체 아티스트">전체 아티스트</ToggleGroupItem>
      </ToggleGroup>
    </div>
    <ResourceState :loading="loading" :error="error" @retry="reload">
      <div class="calendar-workspace">
        <Card class="calendar-board" :size="mobile ? 'sm' : 'default'">
          <CalendarRoot
            v-slot="{ grid, weekDays }"
            locale="ko-KR"
            :week-starts-on="1"
            fixed-weeks
            prevent-deselect
            :model-value="selected"
            :placeholder="placeholder"
            @update:model-value="chooseDate"
            @update:placeholder="setMonth"
          >
            <CardHeader>
              <CalendarHeader class="justify-between gap-3 px-0">
                <CalendarHeading>
                  {{ formatDate(month, { day: undefined, year: 'numeric', month: 'long' }) }}
                </CalendarHeading>
                <div class="flex items-center gap-1">
                  <Button variant="outline" size="sm" @click="goToday">오늘</Button>
                  <CalendarPrevButton aria-label="이전 달" />
                  <CalendarNextButton aria-label="다음 달" />
                </div>
              </CalendarHeader>
              <div class="calendar-options">
                <ToggleGroup type="multiple" v-model="kinds" :spacing="1" aria-label="일정 종류">
                  <ToggleGroupItem value="concert" size="sm">
                    <CalendarIcon data-icon="inline-start" />
                    공연
                  </ToggleGroupItem>
                  <ToggleGroupItem value="birthday" size="sm">
                    <Cake data-icon="inline-start" />
                    생일
                  </ToggleGroupItem>
                </ToggleGroup>
                <span class="calendar-count" aria-live="polite">{{ inMonth.length }}개 일정</span>
              </div>
            </CardHeader>
            <CardContent class="calendar-board-content">
              <CalendarGrid v-for="m in grid" :key="m.value.toString()" class="month-grid">
                <CalendarGridHead>
                  <CalendarGridRow>
                    <CalendarHeadCell v-for="day in weekDays" :key="day">
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
                      class="month-cell"
                    >
                      <CalendarCellTrigger
                        :day="day"
                        :month="m.value"
                        class="month-date"
                        :aria-label="
                          formatDate(day.toString()) +
                          ', ' +
                          eventsOn(day.toString()).length +
                          '개 일정'
                        "
                      >
                        {{ day.day }}
                      </CalendarCellTrigger>
                      <div v-if="day.month === m.value.month" class="cell-events">
                        <template v-if="!mobile">
                          <button
                            v-for="event in eventsOn(day.toString()).slice(0, 2)"
                            :key="event.id"
                            type="button"
                            class="cell-event-link"
                            :aria-label="event.title + ' 상세 보기'"
                            @click="openEvent(event)"
                          >
                            <Badge
                              :variant="event.kind === 'birthday' ? 'outline' : 'secondary'"
                              class="w-full min-w-0 justify-start"
                            >
                              <component
                                :is="event.kind === 'birthday' ? Cake : CalendarIcon"
                                data-icon="inline-start"
                              />
                              <span class="truncate">
                                {{
                                  event.kind === 'birthday'
                                    ? event.title
                                    : artist(event.artist_id)?.name
                                }}
                              </span>
                            </Badge>
                          </button>
                        </template>
                        <span v-else class="cell-markers" aria-hidden="true">
                          <component
                            v-for="event in eventsOn(day.toString()).slice(0, 2)"
                            :key="event.id"
                            :is="event.kind === 'birthday' ? Cake : CalendarIcon"
                            class="size-3"
                          />
                        </span>
                        <button
                          v-if="eventsOn(day.toString()).length > 2"
                          type="button"
                          class="cell-more"
                          @click="chooseDate(day)"
                        >
                          +{{ eventsOn(day.toString()).length - 2 }}
                        </button>
                      </div>
                    </CalendarCell>
                  </CalendarGridRow>
                </CalendarGridBody>
              </CalendarGrid>
            </CardContent>
          </CalendarRoot>
          <CardFooter class="calendar-board-footer">
            <span>공연은 가상 일정 · 생일은 공식 프로필 기준</span>
            <span>한국 시간</span>
          </CardFooter>
        </Card>
        <aside class="calendar-agenda-panel" aria-label="일정 목록">
          <Card
            :size="mobile ? 'sm' : 'default'"
            :class="cn(dayChosen ? 'calendar-agenda' : 'month-agenda')"
          >
            <CardHeader>
              <div class="agenda-heading">
                <CardTitle>
                  <h2>{{ agendaTitle }}</h2>
                </CardTitle>
                <Button v-if="dayChosen" variant="ghost" size="sm" @click="dayChosen = false">
                  월 전체 보기
                </Button>
                <Badge v-else variant="secondary">{{ visibleEvents.length }}</Badge>
              </div>
              <CardDescription>
                {{
                  dayChosen
                    ? '선택한 날짜의 공연과 생일'
                    : '날짜를 선택해 일정을 좁혀보세요.'
                }}
              </CardDescription>
            </CardHeader>
            <CardContent class="agenda-content">
              <ResourceState
                :empty="!visibleEvents.length"
                :title="dayChosen ? '이 날짜에 일정이 없습니다' : '이번 달에 일정이 없습니다'"
                :description="
                  !kinds.length
                    ? '공연 또는 생일 필터를 켜 주세요.'
                    : '다른 날짜나 전체 아티스트를 확인해 보세요.'
                "
              >
                <div class="agenda-list">
                  <template v-for="(event, index) in visibleEvents" :key="event.id + event.date">
                    <Separator v-if="index" />
                    <Button
                      variant="ghost"
                      :class="cn('schedule-entry', dayChosen ? 'agenda-item' : 'month-event')"
                      @click="openEvent(event)"
                    >
                      <span v-if="!dayChosen" class="entry-date">
                        <strong>{{ Number(event.date.slice(-2)) }}</strong>
                        <span>
                          {{
                            formatDate(event.date, {
                              year: undefined,
                              month: undefined,
                              day: undefined,
                              weekday: 'short',
                            })
                          }}
                        </span>
                      </span>
                      <ArtistAvatar :artist="artist(event.artist_id)" class="size-9" />
                      <span class="entry-copy">
                        <span class="entry-kind">
                          <component :is="event.kind === 'birthday' ? Cake : CalendarIcon" />
                          {{ event.kind === 'birthday' ? '생일' : '샘플 공연' }}
                        </span>
                        <span class="entry-title">{{ event.title }}</span>
                        <span class="entry-place">
                          {{ event.concert?.venue || artist(event.artist_id)?.name }}
                        </span>
                      </span>
                      <ChevronRight data-icon="inline-end" />
                    </Button>
                  </template>
                </div>
              </ResourceState>
            </CardContent>
          </Card>
        </aside>
      </div>
    </ResourceState>
  </div>
</template>
