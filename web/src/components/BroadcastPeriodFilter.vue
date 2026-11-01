<script setup lang="ts">
import { computed, ref, shallowRef, watch } from 'vue'
import { parseDate, today } from '@internationalized/date'
import type { DateValue, DateRange } from 'reka-ui'
import { CalendarDays } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { Field, FieldLabel } from '@/components/ui/field'
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
  PopoverTitle,
  PopoverDescription,
} from '@/components/ui/popover'
import { RangeCalendar } from '@/components/ui/range-calendar'

const props = withDefaults(defineProps<{ start?: string; end?: string; title?: string }>(), {
  title: '방송 기간',
})
const emit = defineEmits<{ apply: [range: { start: string; end: string }] }>()
const open = ref(false)
const draft = shallowRef<DateRange>({ start: undefined, end: undefined })
const month = shallowRef<DateValue>(today('Asia/Seoul'))
function date(value?: string) {
  try {
    return value ? parseDate(value) : undefined
  } catch {
    return undefined
  }
}
watch(open, (value) => {
  if (!value) return
  draft.value = { start: date(props.start), end: date(props.end) }
  month.value = draft.value.start ?? draft.value.end ?? today('Asia/Seoul')
})
const label = computed(() => {
  const start = date(props.start)?.toString().replaceAll('-', '.')
  const end = date(props.end)?.toString().replaceAll('-', '.')
  return start && end
    ? `${start} ~ ${end}`
    : start
      ? `${start}부터`
      : end
        ? `${end}까지`
        : `${props.title} 전체`
})
const years = computed(() =>
  Array.from({ length: today('Asia/Seoul').year - 1999 + 2 }, (_, i) => 2000 + i),
)
const ready = computed(() => !!draft.value.start && !!draft.value.end)
function preset(kind: 'month' | 'year' | number) {
  const end = today('Asia/Seoul')
  const start =
    kind === 'month'
      ? end.set({ day: 1 })
      : kind === 'year'
        ? end.set({ month: 1, day: 1 })
        : end.subtract({ days: kind - 1 })
  draft.value = { start, end }
  month.value = start
}
function apply() {
  if (!ready.value) return
  emit('apply', { start: draft.value.start!.toString(), end: draft.value.end!.toString() })
  open.value = false
}
function clear() {
  emit('apply', { start: '', end: '' })
  open.value = false
}
</script>

<template>
  <Popover v-model:open="open">
    <PopoverTrigger as-child>
      <Button
        variant="outline"
        :aria-label="`${props.title} 선택`"
        :aria-description="label"
        class="shrink-0 whitespace-nowrap"
      >
        <CalendarDays data-icon="inline-start" />
        {{ label }}
      </Button>
    </PopoverTrigger>
    <PopoverContent
      align="end"
      aria-labelledby="broadcast-period-title"
      aria-describedby="broadcast-period-description"
      :collision-padding="16"
      class="w-80 max-w-[calc(100vw-2rem)] max-h-[min(calc(100dvh-2rem),var(--reka-popover-content-available-height))] overflow-y-auto gap-3"
    >
      <div class="flex flex-col gap-1">
        <PopoverTitle id="broadcast-period-title">{{ props.title }}</PopoverTitle>
        <PopoverDescription id="broadcast-period-description">
          달력에서 시작일과 종료일을 선택해 주세요.
        </PopoverDescription>
      </div>
      <div class="grid grid-cols-2 gap-2">
        <Button variant="outline" size="sm" @click="preset(30)">최근 30일</Button>
        <Button variant="outline" size="sm" @click="preset(90)">최근 90일</Button>
        <Button variant="outline" size="sm" @click="preset('month')">이번 달</Button>
        <Button variant="outline" size="sm" @click="preset('year')">올해</Button>
      </div>
      <div class="grid grid-cols-2 gap-2">
        <Field class="min-w-0">
          <FieldLabel for="period-year" class="sr-only">기간 연도</FieldLabel>
          <NativeSelect
            id="period-year"
            :model-value="String(month.year)"
            @update:model-value="month = month.set({ year: Number($event) })"
          >
            <NativeSelectOption v-for="year in years" :key="year" :value="String(year)">
              {{ year }}년
            </NativeSelectOption>
          </NativeSelect>
        </Field>
        <Field class="min-w-0">
          <FieldLabel for="period-month" class="sr-only">기간 월</FieldLabel>
          <NativeSelect
            id="period-month"
            :model-value="String(month.month)"
            @update:model-value="month = month.set({ month: Number($event) })"
          >
            <NativeSelectOption v-for="value in 12" :key="value" :value="String(value)">
              {{ value }}월
            </NativeSelectOption>
          </NativeSelect>
        </Field>
      </div>
      <RangeCalendar
        v-model="draft"
        v-model:placeholder="month"
        locale="ko-KR"
        weekday-format="short"
        class="w-full p-0"
      />
      <p aria-live="polite" class="text-sm text-muted-foreground">
        {{ draft.start?.toString().replaceAll('-', '.') ?? '시작일' }} ~
        {{ draft.end?.toString().replaceAll('-', '.') ?? '종료일 선택' }}
      </p>
      <div class="flex items-center justify-between gap-2">
        <Button variant="ghost" size="sm" @click="clear">전체 기간</Button>
        <div class="flex gap-2">
          <Button variant="outline" size="sm" @click="open = false">취소</Button>
          <Button size="sm" :disabled="!ready" @click="apply">적용</Button>
        </div>
      </div>
    </PopoverContent>
  </Popover>
</template>
