<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { CalendarRoot, type DateValue } from 'reka-ui'
import { parseDate } from '@internationalized/date'
import { useMediaQuery, useResizeObserver, useWindowSize } from '@vueuse/core'
import { CalendarDays as CalendarIcon, Cake, List, X } from '@lucide/vue'
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
import { Card, CardHeader, CardContent } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import CalendarEventList from '@/components/CalendarEventList.vue'
import {
  Drawer,
  DrawerContent,
  DrawerHeader,
  DrawerTitle,
  DrawerDescription,
  DrawerClose,
} from '@/components/ui/drawer'
import { Badge } from '@/components/ui/badge'
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
const calendarContent = ref<InstanceType<typeof CardContent>>()
const pageElement = ref<HTMLElement>()
const { height: viewportHeight } = useWindowSize()
const eventSpace = ref(96)
function measureCalendar() {
  const root = calendarContent.value?.$el as HTMLElement | undefined
  const cell = root?.querySelector<HTMLElement>('.month-cell')
  const label = cell?.querySelector<HTMLElement>('.month-day-label')
  const page = pageElement.value
  const body = root?.querySelector('tbody')
  if (!mobile.value && page && body) {
    let pageTop = 0
    let element: HTMLElement | null = page
    while (element) {
      pageTop += element.offsetTop
      element = element.offsetParent as HTMLElement | null
    }
    const surroundingHeight = page.offsetHeight - body.getBoundingClientRect().height
    const rowHeight =
      (viewportHeight.value - pageTop - surroundingHeight - 1) / Math.max(5, body.children.length)
    page.style.setProperty('--calendar-row-height', `${rowHeight}px`)
  }
  if (cell && label) {
    // Reserve the number label, the gap above events, and bottom breathing room.
    eventSpace.value =
      cell.getBoundingClientRect().bottom - label.getBoundingClientRect().bottom - 10
  }
}
useResizeObserver([calendarContent, pageElement], measureCalendar)
watch(viewportHeight, () => nextTick(measureCalendar))
function visibleEventCount(date: string) {
  if (mobile.value) return monthWeekCount.value === 6 ? 2 : 3
  const capacity = Math.floor((eventSpace.value + 2) / 24)
  // Reserve only a compact text line when some events overflow.
  return eventsOn(date).length <= capacity
    ? capacity
    : Math.max(3, Math.floor((eventSpace.value - 12) / 24))
}
const listView = ref(false)
const dayDialog = ref(false)
const month = computed(() => monthKey(route.query.month))
const placeholder = computed(() => parseDate(month.value))
const monthWeekCount = computed(() => {
  const date = placeholder.value
  const mondayOffset = (new Date(Date.UTC(date.year, date.month - 1, 1)).getUTCDay() + 6) % 7
  return Math.max(5, Math.ceil((mondayOffset + date.calendar.getDaysInMonth(date)) / 7))
})
const selected = shallowRef<DateValue>(
  parseDate(month.value.slice(0, 7) === todayKey().slice(0, 7) ? todayKey() : month.value),
)
watch(month, (value) => {
  if (!selected.value.toString().startsWith(value.slice(0, 7))) {
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
function visibleWeeks<T extends DateValue>(rows: T[][], value: DateValue) {
  return rows[5]?.some((day) => day.month === value.month) ? rows : rows.slice(0, 5)
}
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
const monthSurface = ref<HTMLElement>()
const reducedMotion = useMediaQuery('(prefers-reduced-motion: reduce)')
let touchOrigin: { x: number; y: number; time: number } | undefined
let dragOffset = 0
let horizontalDrag = false
let swipeBusy = false
let swipeAnimation: Animation | undefined
let suppressDateUntil = 0
onBeforeUnmount(() => swipeAnimation?.cancel())
function startMonthSwipe(event: TouchEvent) {
  const touch = event.touches[0]
  horizontalDrag = false
  dragOffset = 0
  touchOrigin =
    mobile.value && !swipeBusy && event.touches.length === 1 && touch
      ? { x: touch.clientX, y: touch.clientY, time: Date.now() }
      : undefined
}
function moveMonthSwipe(event: TouchEvent) {
  const touch = event.touches[0]
  if (!touchOrigin || !touch || event.touches.length !== 1) {
    cancelMonthSwipe()
    return
  }
  const dx = touch.clientX - touchOrigin.x
  const dy = touch.clientY - touchOrigin.y
  if (!horizontalDrag && Math.abs(dy) > 10 && Math.abs(dy) > Math.abs(dx)) {
    touchOrigin = undefined
    return
  }
  if (!horizontalDrag && Math.abs(dx) > 10 && Math.abs(dx) > Math.abs(dy) * 1.3)
    horizontalDrag = true
  if (!horizontalDrag) return
  if (event.cancelable) event.preventDefault()
  const width = monthSurface.value?.clientWidth ?? 320
  dragOffset = Math.max(-width, Math.min(width, dx))
  if (monthSurface.value && !reducedMotion.value)
    monthSurface.value.style.transform = `translateX(${dragOffset}px)`
}
async function animateMonth(from: number, to: number) {
  const surface = monthSurface.value
  if (!surface || reducedMotion.value) return
  const style = getComputedStyle(surface)
  swipeAnimation = surface.animate(
    [{ transform: `translateX(${from}px)` }, { transform: `translateX(${to}px)` }],
    {
      duration: parseFloat(style.getPropertyValue('--duration-fast')) || 250,
      easing: style.getPropertyValue('--ease-smooth-out').trim() || 'ease-out',
      fill: 'forwards',
    },
  )
  try {
    await swipeAnimation.finished
  } catch {
    /* Cancellation resets the gesture below. */
  }
  surface.style.transform = `translateX(${to}px)`
  swipeAnimation.cancel()
  swipeAnimation = undefined
}
async function settleMonthSwipe(changeMonth: boolean) {
  swipeBusy = true
  suppressDateUntil = Number.POSITIVE_INFINITY
  const direction = dragOffset < 0 ? 1 : -1
  try {
    if (changeMonth) {
      const width = monthSurface.value?.clientWidth ?? 320
      await animateMonth(dragOffset, -direction * width)
      await setMonth(placeholder.value.add({ months: direction }))
      await nextTick()
      if (monthSurface.value)
        monthSurface.value.style.transform = `translateX(${direction * width}px)`
      await animateMonth(direction * width, 0)
    } else await animateMonth(dragOffset, 0)
  } finally {
    if (monthSurface.value) monthSurface.value.style.removeProperty('transform')
    swipeBusy = false
    suppressDateUntil = Date.now() + 100
    dragOffset = 0
  }
}
function cancelMonthSwipe() {
  touchOrigin = undefined
  if (horizontalDrag && !swipeBusy) void settleMonthSwipe(false)
  horizontalDrag = false
}
function finishMonthSwipe(event: TouchEvent) {
  const origin = touchOrigin
  touchOrigin = undefined
  if (!origin || !horizontalDrag || swipeBusy) return
  horizontalDrag = false
  if (event.cancelable) event.preventDefault()
  void settleMonthSwipe(!event.touches.length && Math.abs(dragOffset) >= 50)
}
async function goToday() {
  selected.value = parseDate(todayKey())
  await setMonth(selected.value)
}
async function chooseDate(value: DateValue | undefined) {
  if (!value || Date.now() < suppressDateUntil) return
  selected.value = value
  await setMonth(value)
  dayDialog.value = true
}
async function openEvent(event: CalendarEvent) {
  dayDialog.value = false
  await nextTick()
  if (event.concert) openOverlay(router, route, 'event', event.concert.id)
  else router.push(`/artists/${event.artist_id}`)
}
</script>
<template>
  <div
    ref="pageElement"
    class="page-container calendar-page page-enter"
    :data-weeks="monthWeekCount"
  >
    <div class="page-heading calendar-page-heading">
      <h1>캘린더</h1>
      <div class="calendar-view-controls flex items-center gap-3">
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
          <ToggleGroupItem value="favorites" aria-label="즐겨찾는 아티스트">
            즐겨찾기
          </ToggleGroupItem>
          <ToggleGroupItem value="all" aria-label="전체 아티스트">전체 아티스트</ToggleGroupItem>
        </ToggleGroup>
        <Button variant="outline" :aria-pressed="listView" @click="listView = !listView">
          <component :is="listView ? CalendarIcon : List" data-icon="inline-start" />
          {{ listView ? '캘린더 보기' : '리스트 보기' }}
        </Button>
      </div>
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
            <CardHeader class="calendar-toolbar">
              <CalendarHeader class="calendar-toolbar-main justify-between gap-3 px-0">
                <CalendarHeading>
                  {{ formatDate(month, { day: undefined, year: 'numeric', month: 'long' }) }}
                </CalendarHeading>
                <div class="calendar-navigation flex items-center gap-1">
                  <Button variant="outline" size="sm" @click="goToday">오늘</Button>
                  <CalendarPrevButton v-if="!mobile" aria-label="이전 달" />
                  <CalendarNextButton v-if="!mobile" aria-label="다음 달" />
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
              </div>
            </CardHeader>
            <CardContent
              ref="calendarContent"
              class="calendar-board-content"
              @touchstart.passive="startMonthSwipe"
              @touchmove="moveMonthSwipe"
              @touchend="finishMonthSwipe"
              @touchcancel="cancelMonthSwipe"
            >
              <div class="calendar-swipe-viewport">
                <div ref="monthSurface" class="calendar-month-surface">
                  <div v-if="listView" class="calendar-list-view">
                    <ResourceState :empty="!inMonth.length" title="이번 달에 일정이 없습니다">
                      <CalendarEventList
                        :events="inMonth"
                        :artists="data?.artists ?? []"
                        show-date
                        @select="openEvent"
                      />
                    </ResourceState>
                  </div>
                  <template v-else>
                    <CalendarGrid v-for="m in grid" :key="m.value.toString()" class="month-grid">
                      <CalendarGridHead>
                        <CalendarGridRow>
                          <CalendarHeadCell v-for="day in weekDays" :key="day">
                            {{ day }}
                          </CalendarHeadCell>
                        </CalendarGridRow>
                      </CalendarGridHead>
                      <CalendarGridBody>
                        <CalendarGridRow
                          v-for="(week, index) in visibleWeeks(m.rows, m.value)"
                          :key="index"
                        >
                          <CalendarCell
                            v-for="day in week"
                            :key="day.toString()"
                            :date="day"
                            class="month-cell"
                            :data-outside="day.month !== m.value.month || undefined"
                            @click="
                              (event: MouseEvent) => {
                                if (!(event.target as HTMLElement).closest('button'))
                                  chooseDate(day)
                              }
                            "
                          >
                            <CalendarCellTrigger
                              :day="day"
                              :month="m.value"
                              class="month-date"
                              @click="chooseDate(day)"
                              :aria-label="
                                formatDate(day.toString()) +
                                ', ' +
                                eventsOn(day.toString()).length +
                                '개 일정'
                              "
                            ></CalendarCellTrigger>
                            <span class="month-day-label" aria-hidden="true">
                              {{ day.day }}
                            </span>
                            <div v-if="day.month === m.value.month" class="cell-events">
                              <template v-if="!mobile">
                                <Button
                                  v-for="event in eventsOn(day.toString()).slice(
                                    0,
                                    visibleEventCount(day.toString()),
                                  )"
                                  :key="event.id"
                                  variant="ghost"
                                  size="xs"
                                  class="cell-event-link h-auto p-0"
                                  :aria-label="event.title + ' 상세 보기'"
                                  @click="openEvent(event)"
                                >
                                  <Badge variant="secondary" class="w-full min-w-0 justify-start">
                                    <component
                                      :is="event.kind === 'birthday' ? Cake : CalendarIcon"
                                      data-icon="inline-start"
                                    />
                                    <span class="truncate">
                                      {{
                                        event.kind === 'birthday'
                                          ? event.title
                                          : `${artist(event.artist_id)?.name ?? ''} 공연`
                                      }}
                                    </span>
                                  </Badge>
                                </Button>
                              </template>
                              <div v-else class="cell-mobile-events" aria-hidden="true">
                                <Badge
                                  v-for="event in eventsOn(day.toString()).slice(
                                    0,
                                    visibleEventCount(day.toString()),
                                  )"
                                  :key="event.id"
                                  variant="secondary"
                                  class="mobile-event-label"
                                >
                                  <Cake v-if="event.kind === 'birthday'" class="size-2" />
                                  <span class="truncate">{{ artist(event.artist_id)?.name }}</span>
                                </Badge>
                              </div>
                              <span
                                v-if="
                                  eventsOn(day.toString()).length >
                                  visibleEventCount(day.toString())
                                "
                                class="cell-more"
                              >
                                +{{
                                  eventsOn(day.toString()).length -
                                  visibleEventCount(day.toString())
                                }}
                              </span>
                            </div>
                          </CalendarCell>
                        </CalendarGridRow>
                      </CalendarGridBody>
                    </CalendarGrid>
                  </template>
                </div>
              </div>
            </CardContent>
          </CalendarRoot>
        </Card>
      </div>
    </ResourceState>
    <component :is="mobile ? Drawer : Dialog" :open="dayDialog" @update:open="dayDialog = $event">
      <component :is="mobile ? DrawerContent : DialogContent" class="day-events-dialog sm:max-w-xl">
        <component :is="mobile ? DrawerHeader : DialogHeader" class="pr-8">
          <component :is="mobile ? DrawerTitle : DialogTitle">
            {{ formatDate(selected.toString()) }}
          </component>
          <component :is="mobile ? DrawerDescription : DialogDescription">일정 리스트</component>
        </component>
        <DrawerClose v-if="mobile" as-child>
          <Button variant="ghost" size="icon-sm" class="absolute right-5 top-5" aria-label="닫기">
            <X />
          </Button>
        </DrawerClose>
        <div class="max-h-[60dvh] overflow-y-auto">
          <ResourceState :empty="!selectedEvents.length" title="이 날짜에 일정이 없습니다">
            <CalendarEventList
              :events="selectedEvents"
              :artists="data?.artists ?? []"
              @select="openEvent"
            />
          </ResourceState>
        </div>
      </component>
    </component>
  </div>
</template>
