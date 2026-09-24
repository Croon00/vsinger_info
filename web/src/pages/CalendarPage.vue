<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { CalendarRoot, type DateValue } from 'reka-ui'
import { parseDate } from '@internationalized/date'
import { useMediaQuery, useResizeObserver, useWindowSize } from '@vueuse/core'
import { CalendarDays as CalendarIcon, Cake, ChevronLeft, ChevronRight, List, X } from '@lucide/vue'
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
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Skeleton } from '@/components/ui/skeleton'
import { capabilities } from '@/api/config'
import { api } from '@/api/client'
import type { CalendarEvent, Concert } from '@/api/types'
import { useResource } from '@/composables/useResource'
import { favoriteIds, calendarScope, calendarView } from '@/composables/preferences'
import { calendarEvents, dateKey, formatDate, monthKey, todayKey, changeMonth } from '@/lib/dates'
import { openOverlay } from '@/lib/overlays'
import ResourceState from '@/components/ResourceState.vue'
const route = useRoute()
const router = useRouter()
const mobile = useMediaQuery('(max-width: 768px)')
const calendarContent = ref<InstanceType<typeof CardContent> | HTMLElement>()
const pageElement = ref<HTMLElement>()
const { height: viewportHeight } = useWindowSize()
const eventSpace = ref(96)
function measureCalendar() {
  const content = calendarContent.value
  const root = content instanceof HTMLElement ? content : (content?.$el as HTMLElement | undefined)
  const cell = root?.querySelector<HTMLElement>('.month-cell')
  const label = cell?.querySelector<HTMLElement>('.month-day-label')
  const page = pageElement.value
  const body = root?.querySelector('tbody')
  if (mobile.value && page) {
    const dock = document.querySelector<HTMLElement>('.mobile-dock')
    if (dock) {
      const bottomGap = parseFloat(getComputedStyle(dock).bottom) || 14
      page.style.setProperty(
        '--calendar-dock-clearance',
        `${dock.getBoundingClientRect().height + bottomGap * 2}px`,
      )
    }
    if (root) {
      const contentTop = root.getBoundingClientRect().top + window.scrollY
      const bottomClearance = parseFloat(getComputedStyle(page).paddingBottom) || 0
      page.style.setProperty(
        '--calendar-list-swipe-height',
        `${Math.max(368, viewportHeight.value - contentTop - bottomClearance)}px`,
      )
    }
  }
  if (page && body) {
    let pageTop = 0
    let element: HTMLElement | null = page
    while (element) {
      pageTop += element.offsetTop
      element = element.offsetParent as HTMLElement | null
    }
    const surroundingHeight = page.offsetHeight - body.getBoundingClientRect().height
    const rowHeight =
      (viewportHeight.value - pageTop - surroundingHeight - 1) / Math.max(5, body.children.length)
    page.style.setProperty('--calendar-week-count', String(Math.max(5, body.children.length)))
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
  const rowStep = mobile.value ? 18 : 24
  const capacity = Math.floor((eventSpace.value + 2) / rowStep)
  // Reserve only a compact text line when some events overflow.
  return eventsOn(date).length <= capacity
    ? capacity
    : Math.max(mobile.value ? 1 : 3, Math.floor((eventSpace.value - 12) / rowStep))
}
const listView = computed({
  get: () => calendarView.value === 'list',
  set: (value: boolean) => {
    calendarView.value = value ? 'list' : 'calendar'
  },
})
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
const kinds = ref<string[]>(capabilities.birthdays ? ['concert', 'birthday'] : ['concert'])
const {
  data: artists,
  loading: artistsLoading,
  error: artistsError,
  reload: reloadArtists,
} = useResource((signal) => api.artists(signal))
const {
  data: monthData,
  error: concertsError,
  reload: reloadConcerts,
} = useResource(
  async (signal) => {
    const key = month.value
    const start = changeMonth(key, -1)
    const concerts = await api.concerts(signal, {
      start,
      end: changeMonth(key, 2),
    })
    return { start, concerts }
  },
  [month],
)
const concertsByMonth = shallowRef(new Map<string, Concert[]>())
watch(monthData, (value) => {
  if (!value) return
  const fetched = new Map<string, Concert[]>()
  for (let offset = 0; offset < 3; offset++) fetched.set(changeMonth(value.start, offset), [])
  for (const concert of value.concerts) {
    const date = new Date(concert.starts_at)
    if (!Number.isFinite(date.getTime())) continue
    const key = `${dateKey(date).slice(0, 7)}-01`
    fetched.get(key)?.push(concert)
  }
  const grouped = new Map(concertsByMonth.value)
  for (const [key, concerts] of fetched) {
    grouped.delete(key)
    grouped.set(key, concerts)
  }
  while (grouped.size > 12) grouped.delete(grouped.keys().next().value!)
  concertsByMonth.value = grouped
})
const hasMonthData = computed(() => !!artists.value && concertsByMonth.value.has(month.value))
const visibleMonths = computed(() => [-1, 0, 1].map((offset) => changeMonth(month.value, offset)))
const error = computed(() => artistsError.value || concertsError.value)
const loading = computed(
  () => !error.value && (artistsLoading.value || !concertsByMonth.value.has(month.value)),
)
function reload() {
  if (artistsError.value) void reloadArtists()
  if (concertsError.value) void reloadConcerts()
}
const allEvents = computed(() => {
  const artistRows = artists.value
  if (!hasMonthData.value || !artistRows) return []
  const years = [...new Set(visibleMonths.value.map((key) => Number(key.slice(0, 4))))]
  const concerts = visibleMonths.value.flatMap((key) => concertsByMonth.value.get(key) ?? [])
  const events = years.flatMap((year, index) =>
    calendarEvents(artistRows, index === 0 ? concerts : [], year),
  )
  const visible = new Set(visibleMonths.value)
  return events
    .filter(
      (e) =>
        visible.has(`${e.date.slice(0, 7)}-01`) &&
        kinds.value.includes(e.kind) &&
        (calendarScope.value === 'all' ||
          (e.concert?.artist_ids ?? [e.artist_id]).some((id) => favoriteIds.value.includes(id))),
    )
    .sort((a, b) => a.date.localeCompare(b.date))
})
const eventsByDate = computed(() => {
  const grouped = new Map<string, CalendarEvent[]>()
  for (const event of allEvents.value) {
    const events = grouped.get(event.date) ?? []
    events.push(event)
    grouped.set(event.date, events)
  }
  return grouped
})
const inMonth = computed(() =>
  allEvents.value.filter((e) => e.date.startsWith(month.value.slice(0, 7))),
)
const selectedEvents = computed(() => eventsOn(selected.value.toString()))
function visibleWeeks<T extends DateValue>(rows: T[][], value: DateValue) {
  return rows[5]?.some((day) => day.month === value.month) ? rows : rows.slice(0, 5)
}
function eventsOn(date: string) {
  return eventsByDate.value.get(date) ?? []
}
function dateLabel(date: string) {
  return hasMonthData.value
    ? `${formatDate(date)}, ${eventsOn(date).length}개 일정`
    : formatDate(date)
}
function artist(id: number) {
  return artists.value?.find((a) => a.id === id)
}
const artistThemeStyles = computed(() => {
  const styles = new Map<number, Record<string, string>>()
  for (const item of artists.value ?? []) {
    const color = item.theme_color?.trim()
    if (!color || !/^#[0-9a-f]{6}$/i.test(color)) continue
    styles.set(item.id, { '--calendar-event-color': color })
  }
  return styles
})
function eventThemeStyle(event: CalendarEvent) {
  return artistThemeStyles.value.get(event.artist_id)
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
const swipeBusy = ref(false)
let swipeAnimation: Animation | undefined
let suppressDateUntil = 0
onBeforeUnmount(() => swipeAnimation?.cancel())
function startMonthSwipe(event: TouchEvent) {
  const touch = event.touches[0]
  horizontalDrag = false
  dragOffset = 0
  touchOrigin =
    mobile.value && !swipeBusy.value && event.touches.length === 1 && touch
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
async function animateMonth(from: number, to: number, durationToken = '--duration-fast') {
  const surface = monthSurface.value
  if (!surface || reducedMotion.value) return
  const style = getComputedStyle(surface)
  const rawDuration = style.getPropertyValue(durationToken).trim()
  const durationMs = rawDuration.endsWith('ms')
    ? Number(rawDuration.slice(0, -2))
    : rawDuration.endsWith('s')
      ? Number(rawDuration.slice(0, -1)) * 1000
      : NaN
  swipeAnimation = surface.animate(
    [{ transform: `translateX(${from}px)` }, { transform: `translateX(${to}px)` }],
    {
      duration: Number.isFinite(durationMs) ? durationMs : 250,
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
async function settleMonthSwipe(changeMonth: boolean, buttonDirection?: -1 | 1) {
  if (swipeBusy.value) return
  swipeBusy.value = true
  suppressDateUntil = Number.POSITIVE_INFINITY
  const direction = buttonDirection ?? (dragOffset < 0 ? 1 : -1)
  const durationToken = buttonDirection ? '--duration-quick' : '--duration-fast'
  try {
    if (changeMonth) {
      const width = monthSurface.value?.clientWidth ?? 320
      await animateMonth(buttonDirection ? 0 : dragOffset, -direction * width, durationToken)
      await setMonth(placeholder.value.add({ months: direction }))
      await nextTick()
      if (monthSurface.value && !reducedMotion.value)
        monthSurface.value.style.transform = `translateX(${direction * width}px)`
      await animateMonth(direction * width, 0, durationToken)
    } else await animateMonth(dragOffset, 0)
  } finally {
    if (monthSurface.value) monthSurface.value.style.removeProperty('transform')
    swipeBusy.value = false
    suppressDateUntil = Date.now() + 100
    dragOffset = 0
  }
}
function navigateMonth(direction: -1 | 1) {
  if (swipeBusy.value) return
  touchOrigin = undefined
  horizontalDrag = false
  dragOffset = 0
  void settleMonthSwipe(true, direction)
}
function cancelMonthSwipe() {
  touchOrigin = undefined
  if (horizontalDrag && !swipeBusy.value) void settleMonthSwipe(false)
  horizontalDrag = false
}
function finishMonthSwipe(event: TouchEvent) {
  const origin = touchOrigin
  touchOrigin = undefined
  if (!origin || !horizontalDrag || swipeBusy.value) return
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
  else
    router.push({
      path: `/artists/${event.artist_id}`,
      state: { artistReturnTo: route.fullPath, artistBackSteps: 1 },
    })
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
          <ToggleGroupItem value="all" aria-label="전체 아티스트">
            {{ mobile ? '전체' : '전체 아티스트' }}
          </ToggleGroupItem>
        </ToggleGroup>
        <Button variant="outline" :aria-pressed="listView" @click="listView = !listView">
          <component :is="listView ? CalendarIcon : List" data-icon="inline-start" />
          {{ listView ? (mobile ? '캘린더' : '캘린더 보기') : mobile ? '리스트' : '리스트 보기' }}
        </Button>
      </div>
    </div>
    <div class="calendar-workspace">
      <component
        :is="mobile ? 'div' : Card"
        class="calendar-board"
        :size="mobile ? undefined : 'default'"
      >
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
          <component :is="mobile ? 'div' : CardHeader" class="calendar-toolbar">
            <CalendarHeader class="calendar-toolbar-main justify-between gap-3 px-0">
              <Button
                v-if="mobile"
                variant="ghost"
                size="icon-sm"
                class="calendar-mobile-prev"
                aria-label="이전 달"
                :disabled="swipeBusy"
                @click="navigateMonth(-1)"
              >
                <ChevronLeft />
              </Button>
              <CalendarHeading>
                {{ formatDate(month, { day: undefined, year: 'numeric', month: 'long' }) }}
              </CalendarHeading>
              <Button
                v-if="mobile"
                variant="ghost"
                size="icon-sm"
                class="calendar-mobile-next"
                aria-label="다음 달"
                :disabled="swipeBusy"
                @click="navigateMonth(1)"
              >
                <ChevronRight />
              </Button>
              <div class="calendar-navigation flex items-center gap-1">
                <Button variant="outline" size="sm" @click="goToday">오늘</Button>
                <Button
                  v-if="!mobile"
                  variant="outline"
                  size="icon-sm"
                  class="size-7 bg-transparent opacity-50 hover:opacity-100"
                  aria-label="이전 달"
                  :disabled="swipeBusy"
                  @click="navigateMonth(-1)"
                >
                  <ChevronLeft />
                </Button>
                <Button
                  v-if="!mobile"
                  variant="outline"
                  size="icon-sm"
                  class="size-7 bg-transparent opacity-50 hover:opacity-100"
                  aria-label="다음 달"
                  :disabled="swipeBusy"
                  @click="navigateMonth(1)"
                >
                  <ChevronRight />
                </Button>
              </div>
            </CalendarHeader>
            <div class="calendar-options">
              <ToggleGroup type="multiple" v-model="kinds" :spacing="1" aria-label="일정 종류">
                <ToggleGroupItem value="concert" size="sm">
                  <CalendarIcon data-icon="inline-start" />
                  공연
                </ToggleGroupItem>
                <ToggleGroupItem v-if="capabilities.birthdays" value="birthday" size="sm">
                  <Cake data-icon="inline-start" />
                  생일
                </ToggleGroupItem>
              </ToggleGroup>
            </div>
          </component>
          <component
            :is="mobile ? 'div' : CardContent"
            ref="calendarContent"
            class="calendar-board-content"
            @touchstart.passive="startMonthSwipe"
            @touchmove="moveMonthSwipe"
            @touchend="finishMonthSwipe"
            @touchcancel="cancelMonthSwipe"
          >
            <Alert v-if="error" variant="destructive" class="mb-3">
              <AlertTitle>일정을 불러오지 못했어요</AlertTitle>
              <AlertDescription>{{ error }}</AlertDescription>
              <Button variant="outline" size="sm" class="mt-2" @click="reload">다시 시도</Button>
            </Alert>
            <div class="calendar-swipe-viewport">
              <div
                ref="monthSurface"
                class="calendar-month-surface"
                :class="{ 'calendar-month-surface--list': mobile && listView }"
              >
                <div v-if="listView" class="calendar-list-view">
                  <div v-if="loading && !error" class="flex flex-col gap-3 py-4" aria-hidden="true">
                    <Skeleton v-for="n in 3" :key="n" class="h-20 w-full" />
                  </div>
                  <ResourceState
                    v-else-if="!error || hasMonthData"
                    :empty="!inMonth.length"
                    title="이번 달에 일정이 없습니다"
                  >
                    <CalendarEventList
                      :events="inMonth"
                      :artists="artists ?? []"
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
                          :data-today="day.toString() === todayKey() || undefined"
                          @click="
                            (event: MouseEvent) => {
                              if (!(event.target as HTMLElement).closest('button')) chooseDate(day)
                            }
                          "
                        >
                          <CalendarCellTrigger
                            :day="day"
                            :month="m.value"
                            class="month-date"
                            @click="chooseDate(day)"
                            :aria-label="dateLabel(day.toString())"
                          ></CalendarCellTrigger>
                          <span class="month-day-label" aria-hidden="true">
                            {{ day.day }}
                          </span>
                          <div v-if="hasMonthData" class="cell-events">
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
                                <Badge
                                  variant="secondary"
                                  class="calendar-event-theme w-full min-w-0 justify-start"
                                  :style="eventThemeStyle(event)"
                                >
                                  <component
                                    :is="event.kind === 'birthday' ? Cake : CalendarIcon"
                                    data-icon="inline-start"
                                  />
                                  <span class="calendar-event-name">
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
                                class="calendar-event-theme mobile-event-label"
                                :style="eventThemeStyle(event)"
                              >
                                <span class="calendar-event-name">
                                  {{
                                    event.kind === 'birthday'
                                      ? `${artist(event.artist_id)?.name ?? ''} 생일`
                                      : artist(event.artist_id)?.name
                                  }}
                                </span>
                              </Badge>
                            </div>
                            <span
                              v-if="
                                eventsOn(day.toString()).length > visibleEventCount(day.toString())
                              "
                              class="cell-more"
                            >
                              +{{
                                eventsOn(day.toString()).length - visibleEventCount(day.toString())
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
          </component>
        </CalendarRoot>
      </component>
    </div>
    <component
      :is="mobile ? Drawer : Dialog"
      :key="mobile ? 'drawer' : 'dialog'"
      :open="dayDialog"
      @update:open="dayDialog = $event"
    >
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
          <ResourceState
            :loading="loading"
            :error="hasMonthData ? '' : error"
            :empty="!selectedEvents.length"
            title="이 날짜에 일정이 없습니다"
            @retry="reload"
          >
            <CalendarEventList
              :events="selectedEvents"
              :artists="artists ?? []"
              @select="openEvent"
            />
          </ResourceState>
        </div>
      </component>
    </component>
  </div>
</template>
