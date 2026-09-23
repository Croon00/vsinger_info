<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { Link2, Search, ChevronLeft, ChevronRight, X } from '@lucide/vue'
import { api, titleOf, type Data } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Skeleton } from '@/components/ui/skeleton'
const props = defineProps<{
  modelValue: any
  target: string
  batchId?: string
  label: string
  disabled?: boolean
  id?: string
}>()
const emit = defineEmits<{ 'update:modelValue': [value: any] }>()
const open = ref(false),
  source = ref('catalog'),
  q = ref(''),
  page = ref(1),
  items = ref<Data[]>([]),
  total = ref(0),
  busy = ref(false),
  error = ref(''),
  selectedLabel = ref('')
const valueLabel = computed(
  () =>
    selectedLabel.value ||
    (props.modelValue?.$ref
      ? '초안 · ' + props.modelValue.$ref
      : props.modelValue
        ? '#' + props.modelValue
        : '선택하세요'),
)
let sequence = 0,
  chosenKey = ''
async function search() {
  const seq = ++sequence
  busy.value = true
  error.value = ''
  try {
    const params = new URLSearchParams({
      q: q.value,
      page: String(page.value),
      page_size: '20',
    })
    const route =
      source.value === 'drafts'
        ? '/drafts?' +
          new URLSearchParams({
            ...Object.fromEntries(params),
            batch_id: props.batchId!,
            kind: props.target,
          })
        : '/catalog/' + props.target + '?' + params
    const data = await api(route)
    if (seq !== sequence) return
    items.value = data.items.filter(
      (r: Data) => !r.archived_at && r.status !== 'excluded',
    )
    total.value = data.total
  } catch (e) {
    if (seq === sequence) error.value = (e as Error).message
  } finally {
    if (seq === sequence) busy.value = false
  }
}
watch(
  () => props.modelValue,
  async (value) => {
    if (JSON.stringify(value) === chosenKey) return
    selectedLabel.value = ''
    if (typeof value === 'number') {
      try {
        const r = await api('/catalog/' + props.target + '/' + value)
        if (props.modelValue === value) selectedLabel.value = titleOf(r.data)
      } catch {}
    } else if (value?.$ref && props.batchId) {
      try {
        const result = await api(
          '/drafts?' +
            new URLSearchParams({
              batch_id: props.batchId,
              kind: props.target,
              q: value.$ref,
              page_size: '100',
            }),
        )
        const row = result.items.find((r: Data) => r.client_ref === value.$ref)
        if (row && props.modelValue?.$ref === value.$ref)
          selectedLabel.value = titleOf(row)
      } catch {}
    }
  },
  { immediate: true },
)
watch(open, (v) => {
  if (v) {
    source.value = props.batchId ? 'drafts' : 'catalog'
    q.value = ''
    page.value = 1
    void search()
  }
})
watch([source, page], () => {
  if (open.value) void search()
})
let timer: ReturnType<typeof setTimeout>
watch(q, () => {
  clearTimeout(timer)
  timer = setTimeout(() => {
    page.value = 1
    void search()
  }, 250)
})
function choose(row: Data) {
  const value = source.value === 'drafts' ? { $ref: row.client_ref } : row.id
  chosenKey = JSON.stringify(value)
  selectedLabel.value = titleOf(row)
  emit('update:modelValue', value)
  open.value = false
}
</script>
<template>
  <div class="flex min-w-0 gap-1">
    <Button
      :id="id"
      type="button"
      variant="outline"
      class="min-w-0 flex-1 justify-start"
      :disabled="disabled"
      @click="open = true"
      ><Link2 data-icon="inline-start" /><span class="truncate">{{
        valueLabel
      }}</span></Button
    >
    <Button
      v-if="modelValue != null"
      type="button"
      variant="ghost"
      size="icon"
      :disabled="disabled"
      :aria-label="label + ' 연결 해제'"
      @click="emit('update:modelValue', null)"
      ><X
    /></Button>
  </div>
  <Dialog v-model:open="open">
    <DialogContent class="sm:max-w-lg">
      <DialogHeader
        ><DialogTitle>{{ label }} 연결</DialogTitle
        ><DialogDescription
          >이름으로 찾아 연결할 자료를 선택하세요.</DialogDescription
        ></DialogHeader
      >
      <Tabs v-model="source"
        ><TabsList
          ><TabsTrigger v-if="batchId" value="drafts"
            >이 묶음의 초안</TabsTrigger
          ><TabsTrigger value="catalog">저장된 카탈로그</TabsTrigger></TabsList
        ></Tabs
      >
      <div class="relative">
        <Search
          class="pointer-events-none absolute left-3 top-2.5 size-4 text-muted-foreground"
        /><Input
          v-model="q"
          class="pl-9"
          placeholder="이름 또는 제목 검색"
          aria-label="연결할 자료 검색"
        />
      </div>
      <p v-if="error" role="alert" class="text-sm text-destructive">
        {{ error }}
      </p>
      <div class="h-72 overflow-y-auto">
        <div v-if="busy" class="space-y-2">
          <Skeleton v-for="n in 5" :key="n" class="h-10 w-full" />
        </div>
        <template v-else
          ><Button
            v-for="row in items"
            :key="row.id"
            variant="ghost"
            class="w-full justify-start"
            @click="choose(row)"
            ><span class="truncate">{{ titleOf(row) }}</span
            ><span class="ml-auto text-xs text-muted-foreground">{{
              source === 'drafts' ? '초안' : '#' + row.id
            }}</span></Button
          >
          <p
            v-if="!items.length"
            class="py-16 text-center text-sm text-muted-foreground"
          >
            연결할 자료가 없습니다.
          </p></template
        >
      </div>
      <div
        class="flex items-center justify-between text-xs text-muted-foreground"
      >
        <span>{{ total }}개</span>
        <div class="flex gap-1">
          <Button
            variant="ghost"
            size="icon-sm"
            :disabled="page === 1"
            aria-label="이전 결과"
            @click="page--"
            ><ChevronLeft /></Button
          ><Button
            variant="ghost"
            size="icon-sm"
            :disabled="page * 20 >= total"
            aria-label="다음 결과"
            @click="page++"
            ><ChevronRight
          /></Button>
        </div>
      </div>
    </DialogContent>
  </Dialog>
</template>
