<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { api } from '@/api/client'
import type { CandidateStatus, EventCandidate, EventFormat, EventType } from '@/api/types'
import AppModal from '@/components/AppModal.vue'
import PageHeader from '@/components/PageHeader.vue'
import StatusPill from '@/components/StatusPill.vue'

const queryClient = useQueryClient()
const statusFilter = ref<CandidateStatus | ''>('')
const typeFilter = ref<EventType | ''>('live_event')
const formatFilter = ref<EventFormat | ''>('onsite')
const artistFilter = ref<number | ''>('')
const viewMode = ref<'calendar' | 'list'>('calendar')
const modalOpen = ref(false)
const dayScheduleOpen = ref(false)
const selectedCalendarDayKey = ref<string | null>(null)
const calendarMonth = ref(startOfMonth(new Date()))

const artistsQuery = useQuery({ queryKey: ['artists'], queryFn: api.artists.list })
const eventsQuery = useQuery({
  queryKey: computed(() => ['events', statusFilter.value, artistFilter.value, typeFilter.value, formatFilter.value]),
  queryFn: () => api.events.list(
    statusFilter.value || undefined,
    artistFilter.value || undefined,
    typeFilter.value || undefined,
    typeFilter.value === 'live_event' ? formatFilter.value || undefined : undefined,
  ),
})

const form = reactive({
  artist_id: '', event_type: 'live_event' as EventType, event_format: 'onsite' as EventFormat, title: '', starts_at: '', venue: '',
  ticket_opens_at: '', ticket_closes_at: '', ticket_url: '', source_url: '', price_text: '',
  capacity_text: '', setlist_json: '', merchandise_json: '',
  raw_text: '', status: 'needs_review' as CandidateStatus,
})

const artistMap = computed(() => new Map(
  (artistsQuery.data.value ?? []).flatMap((artist) =>
    (artist.related_artist_ids ?? [artist.id]).map((id) => [id, artist.display_name || artist.name] as const)),
))
const artistFilterOptions = computed(() => [
  { label: '전체 아티스트', value: '' },
  ...(artistsQuery.data.value ?? []).map((artist) => ({
    label: artist.display_name || artist.name,
    value: artist.id,
  })),
])
const eventTypeOptions = [
  { label: '라이브 공연', value: 'live_event' },
  { label: '티켓 접수', value: 'ticket' },
]
const eventFormatOptions = [
  { label: '현장 공연', value: 'onsite' },
  { label: '현장 + 온라인 중계', value: 'hybrid' },
  { label: '미확인', value: 'unknown' },
]
const statusOptions = [
  { label: '전체 상태', value: '' },
  { label: '검토 필요', value: 'needs_review' },
  { label: '준비 완료', value: 'ready' },
  { label: '동기화됨', value: 'synced' },
  { label: '무시됨', value: 'ignored' },
]
const eventStatusOptions = statusOptions.filter((item) => item.value)
const liveEvents = computed(() => (eventsQuery.data.value ?? []).filter(
  (event) => event.event_type === 'live_event'
    && ['onsite', 'hybrid'].includes(event.event_format)
    && event.starts_at,
))
const calendarDays = computed(() => buildCalendarDays(calendarMonth.value, liveEvents.value))
const selectedCalendarDay = computed(() => calendarDays.value.find((day) => day.key === selectedCalendarDayKey.value) ?? null)
const monthTitle = computed(() => new Intl.DateTimeFormat('ko-KR', {
  year: 'numeric', month: 'long',
}).format(calendarMonth.value))

const createEvent = useMutation({
  mutationFn: api.events.create,
  onSuccess: async () => {
    await queryClient.invalidateQueries({ queryKey: ['events'] })
    modalOpen.value = false
    Object.assign(form, {
      artist_id: '', event_type: 'live_event', event_format: 'onsite', title: '', starts_at: '', venue: '',
      ticket_opens_at: '', ticket_closes_at: '', ticket_url: '', source_url: '', price_text: '',
      capacity_text: '', setlist_json: '', merchandise_json: '',
      raw_text: '', status: 'needs_review',
    })
  },
})

function startOfMonth(date: Date): Date { return new Date(date.getFullYear(), date.getMonth(), 1) }
function dateKey(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}
type CalendarEvent = EventCandidate & { duplicate_count: number }
function calendarEventKey(event: EventCandidate): string {
  const title = event.title.normalize('NFKC').toLowerCase().replace(/[^a-z0-9가-힣ぁ-んァ-ヶ一-龯]/g, '')
  return `${event.event_type}|${event.starts_at}|${title}`
}
function buildCalendarDays(month: Date, events: EventCandidate[]) {
  const first = startOfMonth(month)
  const mondayOffset = (first.getDay() + 6) % 7
  const gridStart = new Date(first.getFullYear(), first.getMonth(), 1 - mondayOffset)
  const byDate = new Map<string, CalendarEvent[]>()
  for (const event of events) {
    const parsed = new Date(event.starts_at as string)
    if (Number.isNaN(parsed.getTime())) continue
    const key = dateKey(parsed)
    const dayEvents = byDate.get(key) ?? []
    const duplicateIndex = dayEvents.findIndex((current) => calendarEventKey(current) === calendarEventKey(event))
    if (duplicateIndex >= 0) {
      dayEvents[duplicateIndex] = { ...dayEvents[duplicateIndex], duplicate_count: dayEvents[duplicateIndex].duplicate_count + 1 }
    } else {
      dayEvents.push({ ...event, duplicate_count: 1 })
    }
    byDate.set(key, dayEvents)
  }
  return Array.from({ length: 42 }, (_, index) => {
    const date = new Date(gridStart)
    date.setDate(gridStart.getDate() + index)
    return {
      key: dateKey(date), date, currentMonth: date.getMonth() === month.getMonth(),
      today: dateKey(date) === dateKey(new Date()), events: byDate.get(dateKey(date)) ?? [],
    }
  })
}
function moveMonth(amount: number): void {
  calendarMonth.value = new Date(calendarMonth.value.getFullYear(), calendarMonth.value.getMonth() + amount, 1)
}
function openDaySchedule(key: string): void {
  selectedCalendarDayKey.value = key
  dayScheduleOpen.value = true
}
function dayScheduleTitle(): string {
  const date = selectedCalendarDay.value?.date
  return date ? new Intl.DateTimeFormat('ko-KR', { dateStyle: 'full' }).format(date) : '일정'
}
function selectType(value: EventType | ''): void {
  typeFilter.value = value
  if (value === 'live_event' && !formatFilter.value) formatFilter.value = 'onsite'
  if (value !== 'live_event') formatFilter.value = ''
}
function selectFormat(value: EventFormat | ''): void {
  typeFilter.value = 'live_event'
  formatFilter.value = value
  if (value === 'unknown') viewMode.value = 'list'
}
function optional(value: string): string | null { return value || null }
function submit(): void {
  createEvent.mutate({
    artist_id: form.artist_id ? Number(form.artist_id) : null,
    source_id: null,
    event_type: form.event_type,
    event_format: form.event_type === 'live_event' ? form.event_format : 'unknown',
    title: form.title,
    starts_at: optional(form.starts_at),
    venue: optional(form.venue),
    ticket_opens_at: optional(form.ticket_opens_at),
    ticket_closes_at: optional(form.ticket_closes_at),
    ticket_url: optional(form.ticket_url),
    source_url: optional(form.source_url),
    price_text: optional(form.price_text),
    capacity_text: optional(form.capacity_text),
    setlist_json: optional(form.setlist_json),
    merchandise_json: optional(form.merchandise_json),
    raw_text: optional(form.raw_text),
    status: form.status,
  })
}
function displayDate(value: string | null): string {
  if (!value) return '미정'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : new Intl.DateTimeFormat('ko-KR', {
    dateStyle: 'medium', timeStyle: 'short',
  }).format(parsed)
}
function displayTime(value: string | null): string {
  if (!value) return ''
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? '' : new Intl.DateTimeFormat('ko-KR', {
    hour: '2-digit', minute: '2-digit',
  }).format(parsed)
}

const tones: Record<CandidateStatus, 'amber' | 'cyan' | 'green' | 'muted'> = {
  needs_review: 'amber', ready: 'cyan', synced: 'green', ignored: 'muted',
}
const statusLabels: Record<CandidateStatus, string> = {
  needs_review: '검토 필요', ready: '준비 완료', synced: '동기화됨', ignored: '무시됨',
}
const typeLabels: Record<EventType, string> = { live_event: '라이브', ticket: '티켓 일정' }
const formatLabels: Record<EventFormat, string> = {
  onsite: '현장', hybrid: '현장 + 중계', online: '온라인', unknown: '미확인',
}
</script>

<template>
  <div class="page events-page">
    <PageHeader
      eyebrow="LIVE SCHEDULE / 03"
      title="라이브 일정"
      description="공연 일정과 티켓 접수 일정을 분리하고, 아티스트별 라이브를 달력에서 확인합니다."
    >
      <UButton class="button button--primary" @click="modalOpen = true">+ 일정 등록</UButton>
    </PageHeader>

    <section class="panel schedule-controls">
      <div class="filter-group">
        <span>종류</span>
        <div class="filter-tabs">
          <UButton :class="{ active: typeFilter === 'live_event' }" @click="selectType('live_event')">라이브</UButton>
          <UButton :class="{ active: typeFilter === 'ticket' }" @click="selectType('ticket')">티켓</UButton>
        </div>
      </div>
      <div v-if="typeFilter === 'live_event'" class="filter-group format-filter">
        <span>공연 형태</span>
        <div class="filter-tabs">
          <UButton :class="{ active: formatFilter === 'onsite' }" @click="selectFormat('onsite')">현장</UButton>
          <UButton :class="{ active: formatFilter === 'hybrid' }" @click="selectFormat('hybrid')">현장+중계</UButton>
          <UButton :class="{ active: formatFilter === 'unknown' }" @click="selectFormat('unknown')">미확인</UButton>
        </div>
      </div>
      <label>아티스트
        <USelect v-model="artistFilter" :items="artistFilterOptions" />
      </label>
      <label>상태
        <USelect v-model="statusFilter" :items="statusOptions" />
      </label>
      <div class="view-switch">
        <UButton :class="{ active: viewMode === 'calendar' }" @click="viewMode = 'calendar'">달력</UButton>
        <UButton :class="{ active: viewMode === 'list' }" @click="viewMode = 'list'">목록</UButton>
      </div>
    </section>

    <div v-if="eventsQuery.isError.value" class="alert alert--error">일정을 불러오지 못했습니다.</div>
    <div v-else-if="eventsQuery.isPending.value" class="panel skeleton-list"><i /><i /><i /></div>

    <section v-else-if="viewMode === 'calendar'" class="panel calendar-panel">
      <div class="calendar-header">
        <UButton aria-label="이전 달" @click="moveMonth(-1)">‹</UButton>
        <div><p>MONTHLY LIVE CALENDAR</p><h2>{{ monthTitle }}</h2></div>
        <UButton aria-label="다음 달" @click="moveMonth(1)">›</UButton>
      </div>
      <div class="calendar-weekdays"><span v-for="day in ['월','화','수','목','금','토','일']" :key="day">{{ day }}</span></div>
      <div class="calendar-grid">
        <article v-for="day in calendarDays" :key="day.key" class="calendar-day" :class="{ muted: !day.currentMonth, today: day.today }" role="button" tabindex="0" @click="openDaySchedule(day.key)" @keydown.enter="openDaySchedule(day.key)">
          <time>{{ day.date.getDate() }}</time>
          <a v-for="event in day.events" :key="event.id" :href="event.source_url || event.ticket_url || undefined" :target="event.source_url || event.ticket_url ? '_blank' : undefined" class="calendar-event" @click.stop>
            <b>{{ displayTime(event.starts_at) }}</b>
            <strong>{{ event.title }}</strong>
            <em v-if="event.duplicate_count > 1" class="duplicate-count">같은 공지 {{ event.duplicate_count }}건</em>
            <span>{{ event.artist_id ? artistMap.get(event.artist_id) : '아티스트 미지정' }}</span>
          </a>
        </article>
      </div>
      <p v-if="typeFilter !== 'live_event' || formatFilter === 'unknown'" class="calendar-notice">달력에는 날짜가 확정된 현장·하이브리드 공연만 표시합니다. 미확인 일정은 목록에서 검토하세요.</p>
    </section>

    <AppModal :open="dayScheduleOpen" :title="dayScheduleTitle()" description="선택한 날짜의 공연 일정을 모두 확인합니다." @close="dayScheduleOpen = false">
      <div v-if="selectedCalendarDay?.events.length" class="day-schedule-list">
        <article v-for="event in selectedCalendarDay.events" :key="event.id" class="day-schedule-item">
          <div><time>{{ displayTime(event.starts_at) || '시간 미정' }}</time><h3>{{ event.title }}</h3><p>{{ event.artist_id ? artistMap.get(event.artist_id) : '아티스트 미정' }}<template v-if="event.venue"> · {{ event.venue }}</template></p></div>
          <a v-if="event.source_url || event.ticket_url" :href="event.ticket_url || event.source_url || '#'" target="_blank" rel="noreferrer" class="text-link">원문 열기</a>
        </article>
      </div>
      <div v-else class="empty-state compact"><strong>등록된 일정이 없습니다</strong><p>다른 날짜를 선택해 보세요.</p></div>
    </AppModal>

    <section v-if="viewMode === 'list'" class="panel panel--table">
      <div class="toolbar"><strong>{{ typeFilter ? typeLabels[typeFilter] : '전체 일정' }}</strong><span class="count-label">{{ eventsQuery.data.value?.length || 0 }} EVENTS</span></div>
      <div v-if="eventsQuery.data.value?.length" class="event-table-wrap">
        <table class="data-table">
          <thead><tr><th>일정</th><th>종류</th><th>공연 형태</th><th>아티스트</th><th>시작</th><th>티켓 마감</th><th>상태</th><th>링크</th></tr></thead>
          <tbody><tr v-for="event in eventsQuery.data.value" :key="event.id">
            <td><strong>{{ event.title }}</strong><span>{{ event.venue || '장소 미정' }}</span></td>
            <td><span class="event-kind" :class="`event-kind--${event.event_type}`">{{ typeLabels[event.event_type] }}</span></td>
            <td><span class="event-format" :class="`event-format--${event.event_format}`">{{ formatLabels[event.event_format] }}</span></td>
            <td>{{ event.artist_id ? artistMap.get(event.artist_id) || `ID ${event.artist_id}` : '미지정' }}</td>
            <td>{{ displayDate(event.starts_at) }}</td><td>{{ displayDate(event.ticket_closes_at) }}</td>
            <td><StatusPill :label="statusLabels[event.status]" :tone="tones[event.status]" /></td>
            <td><a v-if="event.source_url || event.ticket_url" :href="event.ticket_url || event.source_url || '#'" target="_blank" rel="noreferrer" class="text-link">원문 ↗</a><span v-else>—</span></td>
          </tr></tbody>
        </table>
      </div>
      <div v-else class="empty-state"><span>◇</span><strong>조건에 맞는 일정이 없습니다</strong><p>아티스트나 일정 종류 필터를 바꿔보세요.</p></div>
    </section>

    <AppModal :open="modalOpen" title="일정 등록" description="공연 자체와 티켓 접수 일정을 구분해서 저장합니다." @close="modalOpen = false">
      <form class="form-grid" @submit.prevent="submit">
        <label>일정 종류<USelect v-model="form.event_type" :items="eventTypeOptions" /></label>
        <label v-if="form.event_type === 'live_event'">공연 형태<USelect v-model="form.event_format" :items="eventFormatOptions" /></label>
        <label>아티스트<USelect v-model="form.artist_id" :items="artistFilterOptions.map((item) => item.value === '' ? { ...item, label: '미지정' } : item)" /></label>
        <label class="form-grid__wide">제목<UInput v-model="form.title" required maxlength="200" placeholder="HACHI 2nd LIVE" /></label>
        <label>공연 시작 일시<UInput v-model="form.starts_at" type="datetime-local" /></label>
        <label>장소<UInput v-model="form.venue" /></label>
        <label>티켓 접수 시작<UInput v-model="form.ticket_opens_at" type="datetime-local" /></label>
        <label>티켓 접수 마감<UInput v-model="form.ticket_closes_at" type="datetime-local" /></label>
        <label class="form-grid__wide">티켓 URL<UInput v-model="form.ticket_url" type="url" /></label>
        <label class="form-grid__wide">원문 URL<UInput v-model="form.source_url" type="url" /></label>
        <label>가격 정보<UInput v-model="form.price_text" placeholder="¥7,500" /></label>
        <label>수용 인원<UInput v-model="form.capacity_text" placeholder="예: 약 1,500명" /></label>
        <label>상태<USelect v-model="form.status" :items="eventStatusOptions" /></label>
        <label class="form-grid__wide">셋리스트<UTextarea v-model="form.setlist_json" rows="4" placeholder="한 줄에 한 곡씩 입력하세요." /></label>
        <label class="form-grid__wide">현장 굿즈<UTextarea v-model="form.merchandise_json" rows="3" placeholder="한 줄에 한 상품씩 입력하세요." /></label>
        <label class="form-grid__wide">원문 메모<UTextarea v-model="form.raw_text" rows="3" /></label>
        <p v-if="createEvent.error.value" class="form-error">{{ createEvent.error.value.message }}</p>
        <div class="form-actions"><UButton type="button" class="button button--ghost" @click="modalOpen = false">취소</UButton><UButton class="button button--primary" :disabled="createEvent.isPending.value">일정 저장</UButton></div>
      </form>
    </AppModal>
  </div>
</template>

<style scoped>
.schedule-controls{display:flex;align-items:end;gap:18px;margin-bottom:14px;padding:17px 20px}.schedule-controls label,.filter-group{display:grid;gap:7px;color:#8491a6;font-size:9px;font-weight:700}.schedule-controls select{min-width:180px}.view-switch{display:flex;margin-left:auto;border:1px solid var(--line);border-radius:7px;overflow:hidden}.view-switch button{height:38px;padding:0 15px;border:0;color:#748198;background:transparent;cursor:pointer}.view-switch button.active{color:var(--cyan);background:rgba(50,214,255,.08)}.calendar-panel{padding:0;overflow:hidden}.calendar-header{display:grid;grid-template-columns:42px 1fr 42px;align-items:center;padding:20px;text-align:center;border-bottom:1px solid var(--line)}.calendar-header button{height:38px;border:1px solid var(--line);border-radius:8px;color:#a8b5c7;background:rgba(255,255,255,.02);font-size:24px;cursor:pointer}.calendar-header p{margin:0 0 4px;color:var(--cyan);font:700 8px ui-monospace,monospace;letter-spacing:.16em}.calendar-header h2{margin:0;font-size:20px}.calendar-weekdays,.calendar-grid{display:grid;grid-template-columns:repeat(7,minmax(0,1fr))}.calendar-weekdays span{padding:10px;border-right:1px solid var(--line);color:#637087;text-align:center;font:700 8px ui-monospace,monospace}.calendar-day{min-height:135px;padding:9px;border-top:1px solid var(--line);border-right:1px solid var(--line);background:rgba(255,255,255,.008)}.calendar-day:nth-child(7n){border-right:0}.calendar-day>time{display:grid;place-items:center;width:25px;height:25px;margin-bottom:6px;color:#8c99ac;font:700 9px ui-monospace,monospace}.calendar-day.muted{opacity:.3}.calendar-day.today>time{border-radius:50%;color:#061017;background:var(--cyan)}.calendar-event{display:block;margin-top:5px;padding:7px;border-left:2px solid var(--cyan);border-radius:3px;background:rgba(50,214,255,.075)}.calendar-event b,.calendar-event strong,.calendar-event span{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.calendar-event b{color:var(--cyan);font:700 8px ui-monospace,monospace}.calendar-event strong{margin-top:3px;color:#d9e3ef;font-size:9px}.calendar-event span{margin-top:3px;color:#718096;font-size:8px}.calendar-notice{margin:0;padding:13px 20px;color:var(--amber);font-size:9px;border-top:1px solid var(--line)}.event-kind{display:inline-block!important;padding:5px 7px;border-radius:5px;color:var(--cyan);background:rgba(50,214,255,.08)}.event-kind--ticket{color:var(--amber);background:rgba(255,202,98,.08)}@media(max-width:820px){.schedule-controls{align-items:stretch;flex-direction:column}.schedule-controls select{min-width:0}.view-switch{margin-left:0}.calendar-day{min-height:90px;padding:5px}.calendar-event span,.calendar-event b{display:none}.calendar-event strong{font-size:8px}.calendar-weekdays span{padding:8px 2px}}
.schedule-controls{flex-wrap:wrap}.format-filter{flex-basis:100%;order:2}.event-format{display:inline-block!important;padding:5px 7px;border-radius:5px;color:var(--green);background:rgba(77,230,168,.08)}.event-format--hybrid{color:#b9a8ff;background:rgba(154,124,255,.1)}.event-format--online{color:#ff91a5;background:rgba(255,116,140,.09)}.event-format--unknown{color:#8995a7;background:rgba(137,149,167,.09)}
.duplicate-count{display:block;margin-top:3px;color:var(--amber);font:700 7px ui-monospace,monospace}
.calendar-day{min-height:175px;cursor:pointer;transition:background .18s,box-shadow .18s}.calendar-day:hover{background:linear-gradient(145deg,rgba(50,214,255,.13),rgba(154,124,255,.06));box-shadow:inset 0 0 0 1px rgba(50,214,255,.38)}.calendar-day:hover>time{color:#061017;background:var(--cyan)}.calendar-day:focus-visible{outline:2px solid var(--cyan);outline-offset:-2px}.calendar-weekdays span{font-size:10px}.calendar-day>time{width:30px;height:30px;font-size:11px;transition:color .18s,background .18s}.calendar-event{padding:9px}.calendar-event b{font-size:10px}.calendar-event strong{font-size:12px;line-height:1.35}.calendar-event span{font-size:10px}.duplicate-count{font-size:9px}.day-schedule-list{display:grid;gap:10px}.day-schedule-item{display:flex;align-items:start;justify-content:space-between;gap:18px;padding:15px;border:1px solid var(--line);border-left:3px solid var(--cyan);border-radius:8px;background:rgba(50,214,255,.05)}.day-schedule-item time{color:var(--cyan);font:700 11px ui-monospace,monospace}.day-schedule-item h3{margin:7px 0 5px;font-size:16px}.day-schedule-item p{margin:0;color:#8d9bb0;font-size:12px}.day-schedule-item .text-link{flex:none;padding-top:3px}@media(max-width:820px){.calendar-day{min-height:115px}.calendar-event strong{font-size:10px}.calendar-event span,.calendar-event b{display:block}.day-schedule-item{display:grid;gap:10px}.day-schedule-item h3{font-size:14px}}
</style>

<style scoped>
@media (max-width: 600px) {
  .calendar-header { padding: 12px; }
  .calendar-day { min-height: 96px; padding: 3px; }
  .calendar-day > time { width: 24px; height: 24px; }
  .calendar-event { padding: 4px 2px; }
  .calendar-event strong { font-size: 10px; }
  .calendar-event b, .calendar-event span { display: none; }
  .view-switch button { min-height: 44px; }
}
</style>
