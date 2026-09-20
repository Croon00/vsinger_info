<script setup lang="ts">
import PlatformRegistration from './components/PlatformRegistration.vue'
import { computed, onMounted, ref, watch, nextTick } from 'vue'
import {
  Inbox,
  Plus,
  Upload,
  FolderOpen,
  ArrowRight,
  ArrowLeft,
  Check,
  ChevronLeft,
  ChevronRight,
  Search,
  RefreshCw,
  Download,
  X,
  Archive,
  RotateCcw,
  Database,
  FileJson,
  LoaderCircle,
  CheckCheck,
} from '@lucide/vue'
import {
  api,
  initSession,
  download,
  titleOf,
  statuses,
  families,
  labels,
  ApiError,
  type Data,
  type Resource,
} from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/badge'
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Empty,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
  EmptyDescription,
  EmptyContent,
} from '@/components/ui/empty'
import {
  FieldGroup,
  Field,
  FieldLabel,
  FieldDescription,
} from '@/components/ui/field'
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectGroup,
  SelectItem,
} from '@/components/ui/select'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog'
import {
  SidebarProvider,
  SidebarInset,
  SidebarTrigger,
} from '@/components/ui/sidebar'
import AdminNav from '@/components/AdminNav.vue'
import ResourceForm from '@/components/ResourceForm.vue'

const workspaceEl = ref<HTMLElement | null>(null),
  workspaceTop = ref(320)
function measureWorkspace() {
  if (workspaceEl.value)
    workspaceTop.value =
      workspaceEl.value.getBoundingClientRect().top + window.scrollY
}
const platformEditor = ref<InstanceType<typeof PlatformRegistration> | null>(null)
const active = ref('review'),
  resources = ref<Resource[]>([]),
  connection = ref<Data>({ connected: false, initialized: false })
const batches = ref<Data[]>([]),
  batchId = ref(''),
  kind = ref('artists'),
  filter = ref('all'),
  q = ref(''),
  page = ref(1)
const rows = ref<Data[]>([]),
  total = ref(0),
  loading = ref(false),
  booting = ref(true),
  working = ref(false)
const error = ref(''),
  notice = ref(''),
  selected = ref<Data | null>(null),
  form = ref<Data>({}),
  editorTab = ref('fields')
const history = ref<Data[]>([]),
  remoteHistory = ref<Data[]>([])
const deleteTarget = ref<Data|null>(null)
const deleteOpen = ref(false)
const batchOpen = ref(false),
  batchName = ref(''),
  addOpen = ref(false),
  addKind = ref('artists'),
  addData = ref<Data>({})
const importOpen = ref(false),
  scanResults = ref<Data[]>([]),
  preview = ref<Data | null>(null),
  previewOpen = ref(false)
const reasonOpen = ref(false),
  reasonAction = ref('hold'),
  reason = ref(''),
  archiveOpen = ref(false)
const discardOpen = ref(false)
let afterDiscard: (() => void) | null = null
const theme = ref(localStorage.getItem('catalog-theme') || 'system')
const pending = ref<Data | null>(
  JSON.parse(sessionStorage.getItem('catalog-pending-save') || 'null'),
)
const batch = computed(() => batches.value.find((b) => b.id === batchId.value))
const completed = computed(() => batch.value?.status === 'published')
const reviewMode = computed(() => active.value === 'review')
const family = computed(() => families.find((f) => f.name === active.value))
const catalogMode = computed(() => Boolean(family.value))
const heading = computed(() =>
  active.value === 'review'
    ? '검수함'
    : active.value === 'history'
      ? '반영 이력'
      : active.value === 'settings'
        ? '설정 · 백업'
        : family.value?.title || '카탈로그',
)
const currentResource = computed(() =>
  resources.value.find(
    (r) => r.name === (selected.value?.entity_type || kind.value),
  ),
)
const addResource = computed(() =>
  resources.value.find((r) => r.name === addKind.value),
)
const availableResources = computed(() =>
  resources.value.filter((r) => family.value?.types.includes(r.name)),
)
const counts = computed(() => batch.value?.review_counts || batch.value?.counts || {})
const allCount = computed(() =>
  Object.values(counts.value).reduce(
    (sum: number, n: any) => sum + Number(n),
    0,
  ),
)
const resolvedCount = computed(
  () =>
    Number(counts.value.approved || 0) +
    Number(counts.value.excluded || 0) +
    Number(counts.value.published || 0),
)
const dirty = computed(
  () =>
    Boolean(selected.value) &&
    JSON.stringify(form.value) !==
      JSON.stringify(originalForm(selected.value!)),
)
const locked = computed(
  () =>
    working.value ||
    completed.value ||
    (!reviewMode.value && Boolean(pending.value)) ||
    (!reviewMode.value && kind.value === 'source_documents'),
)
const canPreview = computed(
  () =>
    batchId.value &&
    !completed.value &&
    allCount.value > 0 &&
    allCount.value === resolvedCount.value &&
    !dirty.value && !platformEditor.value?.dirty && !platformEditor.value?.busy,
)
const resourceTitle = (name: string) =>
  resources.value.find((r) => r.name === name)?.title || name
const formatDate = (value: string) =>
  value
    ? new Intl.DateTimeFormat('ko', {
        dateStyle: 'medium',
        timeStyle: 'short',
      }).format(new Date(value))
    : ''
const pretty = (value: any) => JSON.stringify(value, null, 2)
const clone = (value: any) => JSON.parse(JSON.stringify(value))
function originalForm(row: Data): Data {
  if (row.current_payload) return row.current_payload
  const resource = resources.value.find((r) => r.name === kind.value)
  return Object.fromEntries(
    (resource?.fields || [])
      .filter((f) => f.name in row)
      .map((f) => [f.name, row[f.name]]),
  )
}
function defaults(name: string) {
  return Object.fromEntries(
    (resources.value.find((r) => r.name === name)?.fields || [])
      .filter((f) => f.default !== undefined)
      .map((f) => [f.name, f.default]),
  )
}
async function task(fn: () => Promise<void>) {
  if (working.value) return
  working.value = true
  error.value = ''
  notice.value = ''
  try {
    await fn()
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    working.value = false
  }
}
function guarded(fn: () => void) {
  if (platformEditor.value?.busy) return
  if (dirty.value || platformEditor.value?.dirty) {
    afterDiscard = fn
    discardOpen.value = true
  } else fn()
}
function discard() {
  discardOpen.value = false
  selected.value = null
  afterDiscard?.()
  afterDiscard = null
}
function navigate(name: string) {
  guarded(() => {
    active.value = name
    selected.value = null
    q.value = ''
    page.value = 1
    filter.value = 'all'
    if (families.some((f) => f.name === name)) kind.value = name
    void refresh()
  })
}
async function refreshBatches() {
  batches.value = (await api('/batches')).data.items
}
let sequence = 0
async function loadRows() {
  const seq = ++sequence
  if (reviewMode.value && !batchId.value) {
    rows.value = []
    total.value = 0
    return
  }
  loading.value = true
  try {
    const params = new URLSearchParams({
      q: q.value,
      page: String(page.value),
      page_size: '30',
    })
    const route = reviewMode.value
      ? '/review-items?' +
        new URLSearchParams({
          ...Object.fromEntries(params),
          batch_id: batchId.value,
          status: filter.value === 'all' ? '' : filter.value,
        })
      : '/catalog/' + kind.value + '?' + params
    const result = await api(route)
    if (seq === sequence) {
      rows.value = result.items
      total.value = result.total
    }
  } catch (e) {
    if (seq === sequence) {
      error.value = (e as Error).message
      rows.value = []
      total.value = 0
    }
  } finally {
    if (seq === sequence) loading.value = false
  }
}
async function refresh() {
  error.value = ''
  if (active.value === 'history') {
    await task(async () => {
      history.value = (await api('/history')).data.items
      remoteHistory.value = connection.value.connected
        ? (await api('/catalog/history')).data.items
        : []
    })
  } else if (reviewMode.value || catalogMode.value) await loadRows()
}
function selectRow(row: Data) {
  guarded(() => {
    void task(async () => {
      const result = await api(
        reviewMode.value
          ? '/drafts/' + row.id
          : '/catalog/' + kind.value + '/' + row.id,
      )
      selected.value = row.review_group ? { ...result.data, review_group: row.review_group, status: row.status } : result.data
      form.value = clone(originalForm(selected.value!))
      editorTab.value = 'fields'
    })
  })
}
function changeBatch(value: any) {
  guarded(() => {
    batchId.value = String(value)
    selected.value = null
    page.value = 1
    void loadRows()
  })
}
function changeKind(value: any) {
  guarded(() => {
    kind.value = String(value)
    selected.value = null
    page.value = 1
    void loadRows()
  })
}
let searchTimer: ReturnType<typeof setTimeout>
watch(q, () => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    page.value = 1
    void loadRows()
  }, 250)
})
watch(filter, () => {
  page.value = 1
  void loadRows()
})
watch(page, () => {
  void loadRows()
})
watch(addKind, (value) => {
  addData.value = defaults(value)
})
watch(
  pending,
  (value) =>
    sessionStorage.setItem('catalog-pending-save', JSON.stringify(value)),
  { deep: true },
)
function setTheme() {
  localStorage.setItem('catalog-theme', theme.value)
  document.documentElement.classList.toggle(
    'dark',
    theme.value === 'dark' ||
      (theme.value === 'system' &&
        matchMedia('(prefers-color-scheme: dark)').matches),
  )
}
watch(theme, setTheme, { immediate: true })
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', setTheme)
async function createBatch() {
  await task(async () => {
    const result = await api('/batches', 'POST', {
      name: batchName.value.trim(),
    })
    batchId.value = result.data.id
    batchOpen.value = false
    batchName.value = ''
    selected.value = null
    await refreshBatches()
    await loadRows()
  })
}
function requestDeleteBatch() {
  deleteTarget.value = clone(batch.value)
  deleteOpen.value = true
}
async function deleteBatch() {
  await task(async () => {
    const target = deleteTarget.value!
    await api('/batches/'+target.id+'?revision='+target.revision, 'DELETE')
    selected.value=null
    form.value={}
    preview.value=null
    previewOpen.value=false
    deleteOpen.value=false
    await refreshBatches()
    batchId.value=batches.value.find(b=>b.status!=='published')?.id||batches.value[0]?.id||''
    page.value=1
    q.value=''
    filter.value='all'
    await loadRows()
    notice.value='검수 묶음을 삭제했습니다. 원본 파일과 DB에 반영된 자료는 유지됩니다.'
  })
}
function openImport() {
  importOpen.value=true
  scanResults.value=[]
}
function openAdd() {
  addKind.value = catalogMode.value ? kind.value : 'artists'
  addData.value = defaults(addKind.value)
  addOpen.value = true
}
async function saveDraft() {
  await task(async () => {
    const result = await api('/drafts/' + selected.value!.id, 'PATCH', {
      revision: selected.value!.revision,
      data: form.value,
    })
    selected.value = result.data
    form.value = clone(result.data.current_payload)
    await refreshBatches()
    await loadRows()
    notice.value = '초안을 저장했습니다. 변경된 내용은 다시 승인해 주세요.'
  })
}
async function review(action: string) {
  await task(async () => {
    const current = selected.value!
    const contextBatch = batchId.value
    let approved = false
    try {
      const result = await api('/drafts/' + current.id + '/review', 'POST', {
        revision: current.revision, action, note: reason.value || null,
      })
      approved = action === 'approve'
      if (selected.value?.id !== current.id || batchId.value !== contextBatch || !reviewMode.value) return
      selected.value = result.data
      form.value = clone(result.data.current_payload)
      reasonOpen.value = false
      reason.value = ''
      notice.value = approved
        ? '승인했습니다. DB 반영은 미리보기에서 진행하세요.'
        : '검수 상태를 변경했습니다.'
    } finally {
      if (selected.value?.id === current.id && batchId.value === contextBatch && reviewMode.value) {
        if (!approved) {
          selected.value = (await api('/drafts/' + current.id)).data
          form.value = clone(selected.value!.current_payload)
        }
        await refreshBatches()
        await loadRows()
      }
    }
    if (!approved || selected.value?.id !== current.id || batchId.value !== contextBatch || !reviewMode.value) return
    const nextFilter = filter.value === 'all' ? 'all' : 'pending'
    const result = await api('/review-items/' + current.id + '/next-pending?' + new URLSearchParams({
      q: q.value, status: nextFilter, page_size: '30',
    }))
    if (selected.value?.id !== current.id || batchId.value !== contextBatch || !reviewMode.value) return
    if (result.data.item) {
      selected.value = result.data.item
      form.value = clone(result.data.item.current_payload)
      editorTab.value = 'fields'
      filter.value = nextFilter
      await nextTick()
      page.value = result.data.page
      await loadRows()
      notice.value = '승인하고 다음 검수 대기 항목으로 이동했습니다.'
    }
  })
}
async function platformChanged(item?: Data) {
  if (item && selected.value && selected.value.id === item.id) {
    selected.value.status = item.status
    if (item.current_payload) {
      selected.value.current_payload = clone(item.current_payload)
      form.value = clone(originalForm(selected.value))
    }
  }
  await refreshBatches()
  await loadRows()
}
async function platformCreated(item?: Data) {
  if (!item?.id) return
  selected.value = { ...(await api('/drafts/' + item.id)).data, review_group: 'platform', status: item.status }
  form.value = clone(originalForm(selected.value!))
  addOpen.value = false
  await platformChanged(item)
}
async function advancePlatform(id: string) {
  const contextBatch = batchId.value
  const nextFilter = filter.value === 'all' ? 'all' : 'pending'
  try {
    const result = await api('/review-items/' + id + '/next-pending?' + new URLSearchParams({ q: q.value, status: nextFilter, page_size: '30' }))
    if (selected.value?.id !== id || batchId.value !== contextBatch || !reviewMode.value) return
    if (result.data.item) {
      selected.value = result.data.item
      form.value = clone(originalForm(selected.value!))
      editorTab.value = 'fields'
      filter.value = nextFilter
      await nextTick()
      page.value = result.data.page
      await loadRows()
    }
  } catch (e) { error.value = (e as Error).message }
}
function requestReason(action: string) {
  reasonAction.value = action
  reason.value = ''
  reasonOpen.value = true
}
async function savePending() {
  if (!pending.value) return
  const request = pending.value
  try {
    await api(request.route, 'POST', request.body)
    pending.value = null
    addOpen.value = false
    archiveOpen.value = false
    notice.value = '새 카탈로그에 저장했습니다.'
    if (selected.value && !reviewMode.value) {
      selected.value = (
        await api('/catalog/' + kind.value + '/' + selected.value.id)
      ).data
      form.value = clone(originalForm(selected.value!))
    }
    await loadRows()
  } catch (e) {
    if (e instanceof ApiError && e.status >= 400 && e.status < 500)
      pending.value = null
    throw e
  }
}
async function saveCatalog() {
  await task(async () => {
    if (!pending.value)
      pending.value = {
        route: '/catalog/save',
        body: {
          operation_id: crypto.randomUUID(),
          catalog_id: connection.value.catalog_id,
          entity: {
            client_ref: 'manual:' + crypto.randomUUID(),
            entity_type: kind.value,
            operation: 'update',
            target_id: selected.value!.id,
            expected_version: selected.value!._version,
            data: form.value,
          },
        },
      }
    await savePending()
  })
}
async function add() {
  await task(async () => {
    if (connection.value.initialized && !reviewMode.value) {
      if (!pending.value)
        pending.value = {
          route: '/catalog/save',
          body: {
            operation_id: crypto.randomUUID(),
            catalog_id: connection.value.catalog_id,
            entity: {
              client_ref: 'manual:' + crypto.randomUUID(),
              entity_type: addKind.value,
              data: addData.value,
            },
          },
        }
      await savePending()
    } else {
      if (!batchId.value || completed.value) {
        const b = await api('/batches', 'POST', { name: '수동 입력 검수' })
        batchId.value = b.data.id
      }
      const result = await api('/drafts', 'POST', {
        batch_id: batchId.value,
        client_ref: addKind.value + ':' + crypto.randomUUID(),
        entity_type: addKind.value,
        data: addData.value,
      })
      active.value = 'review'
      addOpen.value = false
      selected.value = result.data
      form.value = clone(result.data.current_payload)
      await refreshBatches()
      await loadRows()
      notice.value = '검수할 초안을 추가했습니다.'
    }
  })
}
async function uploadFile(event: Event) {
  const input = event.target as HTMLInputElement,
    file = input.files?.[0]
  if (!file) return
  await task(async () => {
    if (file.size > 10 * 1024 * 1024)
      throw new Error('파일당 최대 10MiB입니다.')
    let envelope: Data
    try {
      envelope = JSON.parse(await file.text())
    } catch {
      throw new Error('올바른 JSON 파일을 선택하세요.')
    }
    const result = await api('/imports', 'POST', {
      batch_id: batchId.value,
      filename: file.name,
      envelope,
    })
    scanResults.value = [{ file: file.name, ...result.data }]
    await refreshBatches()
    await loadRows()
  })
  input.value = ''
}
async function scan() {
  await task(async () => {
    scanResults.value = (
      await api('/batches/' + batchId.value + '/scan', 'POST')
    ).data.files
    await refreshBatches()
    await loadRows()
  })
}
async function makePreview() {
  await task(async () => {
    preview.value = (
      await api('/batches/' + batchId.value + '/preview', 'POST')
    ).data
    previewOpen.value = true
    await refreshBatches()
  })
}
async function publish() {
  await task(async () => {
    const p = preview.value!
    await api('/publish', 'POST', {
      manifest_id: p.manifest_id,
      manifest_hash: p.manifest_hash,
      operation_id: p.operation_id,
    })
    previewOpen.value = false
    selected.value = null
    connection.value = await api('/connection')
    await refreshBatches()
    await loadRows()
    notice.value = '승인한 자료를 새 카탈로그에 반영했습니다.'
  })
}
async function recover(row: Data) {
  await task(async () => {
    const r = await api('/publish/' + row.operation_id + '/recover', 'POST')
    notice.value = r.data.committed
      ? '반영 완료를 확인했습니다.'
      : '반영 영수증이 아직 없습니다. 같은 작업 재시도를 사용할 수 있습니다.'
    history.value = (await api('/history')).data.items
    await refreshBatches()
    connection.value = await api('/connection')
  })
}
async function retry(row: Data) {
  await task(async () => {
    await api('/publish', 'POST', {
      manifest_id: row.id,
      manifest_hash: row.manifest_hash,
      operation_id: row.operation_id,
    })
    history.value = (await api('/history')).data.items
    await refreshBatches()
    connection.value = await api('/connection')
    notice.value = '반영 완료를 확인했습니다.'
  })
}
async function archiveItem() {
  await task(async () => {
    if (!pending.value)
      pending.value = {
        route: '/catalog/' + kind.value + '/' + selected.value!.id + '/archive',
        body: {
          operation_id: crypto.randomUUID(),
          catalog_id: connection.value.catalog_id,
          expected_version: selected.value!._version,
          archived: !selected.value!.archived_at,
        },
      }
    await savePending()
  })
}
watch([active, batchId, selected, notice, error, booting], () => {
  void nextTick(measureWorkspace)
})
window.addEventListener('resize', measureWorkspace)
onMounted(async () => {
  try {
    await initSession()
    resources.value = (await api('/metadata')).resources
    await refreshBatches()
    batchId.value =
      batches.value.find((b) => b.status !== 'published')?.id ||
      batches.value[0]?.id ||
      ''
    connection.value = await api('/connection')
    await loadRows()
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    booting.value = false
  }
})
window.addEventListener('beforeunload', (event) => {
  if (dirty.value) {
    event.preventDefault()
    event.returnValue = ''
  }
})
</script>

<template>
  <SidebarProvider>
    <AdminNav
      :active="active"
      :connected="connection.connected"
      :initialized="connection.initialized"
      @navigate="navigate"
    />
    <SidebarInset class="min-w-0">
      <header
        class="flex h-14 shrink-0 items-center gap-3 border-b px-5 md:px-8"
      >
        <SidebarTrigger aria-label="메뉴 열기 · 닫기" /><span
          class="text-xs text-muted-foreground"
          >작업 공간</span
        ><span class="text-border">/</span
        ><span class="text-sm">{{ heading }}</span>
        <Badge variant="outline" class="ml-auto">로컬 관리자</Badge>
      </header>
      <main class="mx-auto w-full max-w-[1560px] px-5 py-7 md:px-8 lg:px-10">
        <div class="mb-7 flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 class="text-2xl font-semibold tracking-tight">{{ heading }}</h1>
            <p class="mt-2 text-sm text-muted-foreground">
              {{
                reviewMode
                  ? '자료를 검토하고 승인된 내용만 새 카탈로그에 반영합니다.'
                  : catalogMode
                    ? '등록된 자료와 연결 관계를 관리합니다.'
                    : active === 'history'
                      ? 'DB에 보낸 작업의 결과를 확인합니다.'
                      : '이 PC의 작업 환경과 검수 데이터를 관리합니다.'
              }}
            </p>
          </div>
          <div v-if="reviewMode || catalogMode" class="flex gap-2">
            <Button
              v-if="reviewMode"
              variant="outline"
              :disabled="working"
              @click="batchOpen = true"
              ><Plus data-icon="inline-start" />새 검수 묶음</Button
            >
            <Button
              v-if="catalogMode || batchId"
              :disabled="working || Boolean(pending)"
              @click="openAdd"
              ><Plus data-icon="inline-start" />추가</Button
            >
          </div>
        </div>
        <Alert v-if="error" variant="destructive" role="alert" class="mb-5"
          ><AlertTitle>작업을 완료하지 못했습니다</AlertTitle
          ><AlertDescription class="flex items-start justify-between gap-3"
            ><span class="whitespace-pre-wrap break-words">{{ error }}</span
            ><Button
              variant="ghost"
              size="icon-xs"
              aria-label="오류 닫기"
              @click="error = ''"
              ><X /></Button></AlertDescription
        ></Alert>
        <Alert v-if="notice" class="mb-5" role="status"
          ><CheckCheck /><AlertDescription
            class="flex items-center justify-between gap-3"
            ><span>{{ notice }}</span
            ><Button
              variant="ghost"
              size="icon-xs"
              aria-label="안내 닫기"
              @click="notice = ''"
              ><X /></Button></AlertDescription
        ></Alert>
        <Alert v-if="pending" class="mb-5"
          ><AlertTitle>저장 결과 확인이 필요합니다</AlertTitle
          ><AlertDescription
            class="flex flex-wrap items-center justify-between gap-3"
            ><span>같은 작업 번호로 확인하여 중복 등록을 방지합니다.</span
            ><Button size="sm" :disabled="working" @click="task(savePending)"
              >저장 결과 확인 · 재시도</Button
            ></AlertDescription
          ></Alert
        >
        <div v-if="booting" class="space-y-5">
          <Skeleton class="h-12 w-full" /><Skeleton class="h-80 w-full" />
        </div>
        <template v-else-if="reviewMode">
          <div v-if="batchId" class="mb-5 space-y-4">
            <div class="flex flex-wrap items-center justify-between gap-3">
              <Select :model-value="batchId" @update:model-value="changeBatch"
                ><SelectTrigger class="w-full sm:w-72" aria-label="검수 묶음"
                  ><SelectValue /></SelectTrigger
                ><SelectContent
                  ><SelectGroup
                    ><SelectItem
                      v-for="b in batches"
                      :key="b.id"
                      :value="b.id"
                      >{{ b.name }}</SelectItem
                    ></SelectGroup
                  ></SelectContent
                ></Select
              >
              <div class="flex flex-wrap gap-2">
                <Button variant="ghost" size="sm" :disabled="working" @click="requestDeleteBatch">묶음 삭제</Button>

                <Button
                  variant="outline"
                  size="sm"
                  :disabled="working"
                  @click="
                    task(() =>
                      download(
                        '/batches/' + batchId + '/export',
                        'catalog-review.json',
                      ),
                    )
                  "
                  ><Download data-icon="inline-start" />내보내기</Button
                ><Button
                  variant="outline"
                  size="sm"
                  :disabled="working || completed"
                  @click="openImport"
                  ><Upload data-icon="inline-start" />JSON 가져오기</Button
                ><Button
                  size="sm"
                  :disabled="working || !canPreview"
                  @click="makePreview"
                  >반영 미리보기<ArrowRight data-icon="inline-end"
                /></Button>
              </div>
            </div>
            <div
              class="flex flex-wrap items-center gap-x-5 gap-y-2 border-b pb-4 text-xs text-muted-foreground"
            >
              <Badge variant="secondary">{{
                statuses[batch?.status] || '검수 중'
              }}</Badge
              ><span
                >전체
                <strong class="ml-1 font-medium text-foreground">{{
                  allCount
                }}</strong></span
              ><span
                >승인
                <strong class="ml-1 font-medium text-foreground">{{
                  counts.approved || 0
                }}</strong></span
              ><span
                >보류·오류
                <strong class="ml-1 font-medium text-foreground">{{
                  (counts.held || 0) + (counts.blocked || 0)
                }}</strong></span
              ><span class="ml-auto tabular-nums"
                >{{ resolvedCount }} / {{ allCount }} 검수 완료</span
              >
            </div>
          </div>
          <Empty v-else class="min-h-[440px] border"
            ><EmptyHeader
              ><EmptyMedia variant="icon"><Inbox /></EmptyMedia
              ><EmptyTitle>첫 검수 묶음을 만들어 주세요</EmptyTitle
              ><EmptyDescription
                >JSON 파일을 불러오거나 직접 자료를 입력하세요.<br />검수가
                끝나기 전까지 데이터는 이 PC에만 저장됩니다.</EmptyDescription
              ></EmptyHeader
            ><EmptyContent
              ><Button @click="batchOpen = true"
                ><Plus data-icon="inline-start" />새 검수 묶음</Button
              ></EmptyContent
            ></Empty
          >
        </template>
        <div
          v-if="!booting && catalogMode"
          class="mb-5 flex flex-wrap items-center gap-3"
        >
          <Select :model-value="kind" @update:model-value="changeKind"
            ><SelectTrigger class="w-64" aria-label="자료 종류"
              ><SelectValue /></SelectTrigger
            ><SelectContent
              ><SelectGroup
                ><SelectItem
                  v-for="r in availableResources"
                  :key="r.name"
                  :value="r.name"
                  >{{ reviewMode && r.name === 'external_accounts' ? '외부 플랫폼 등록' : r.title }}</SelectItem
                ></SelectGroup
              ></SelectContent
            ></Select
          >
          <span
            v-if="!connection.initialized"
            class="text-xs text-muted-foreground"
            >초기 구축 중입니다. 추가한 자료는 검수함에서 확인합니다.</span
          >
        </div>
        <div
          v-if="!booting && ((reviewMode && batchId) || catalogMode)"
          ref="workspaceEl"
          :style="{ '--workspace-top': workspaceTop + 'px' }"
          class="workspace-grid overflow-hidden rounded-2xl border"
        >
          <section
            class="min-h-0 min-w-0 border-b lg:border-r lg:border-b-0"
            :class="selected ? 'hidden lg:flex lg:flex-col' : 'flex flex-col'"
          >
            <div class="space-y-3 border-b p-4">
              <div class="relative">
                <Search
                  class="pointer-events-none absolute left-3 top-2.5 size-4 text-muted-foreground"
                /><Input
                  v-model="q"
                  placeholder="이름 또는 제목 검색"
                  class="pl-9"
                  aria-label="목록 검색"
                />
              </div>
              <div class="flex items-center justify-between gap-2">
                <Select v-if="reviewMode" v-model="filter"
                  ><SelectTrigger size="sm" aria-label="검수 상태"
                    ><SelectValue /></SelectTrigger
                  ><SelectContent
                    ><SelectGroup
                      ><SelectItem value="all">모든 상태</SelectItem
                      ><SelectItem
                        v-for="s in [
                          'pending',
                          'editing',
                          'approved',
                          'held',
                          'blocked',
                          'excluded',
                          'published',
                        ]"
                        :key="s"
                        :value="s"
                        >{{ statuses[s] }}</SelectItem
                      ></SelectGroup
                    ></SelectContent
                  ></Select
                >
                <span class="text-xs text-muted-foreground">{{ total }}개</span
                ><Button
                  variant="ghost"
                  size="icon-sm"
                  :disabled="loading"
                  aria-label="목록 새로고침"
                  @click="loadRows"
                  ><RefreshCw
                /></Button>
              </div>
            </div>
            <div class="min-h-64 flex-1 overflow-y-auto p-2">
              <div v-if="loading" class="space-y-2 p-2">
                <Skeleton v-for="n in 5" :key="n" class="h-16 w-full" />
              </div>
              <template v-else
                ><button
                  v-for="row in rows"
                  :key="row.id"
                  class="catalog-row"
                  :class="selected?.id === row.id ? 'bg-muted' : ''"
                  @click="selectRow(row)"
                >
                  <div class="flex min-w-0 items-start justify-between gap-2">
                    <span
                      class="line-clamp-2 break-words text-sm font-medium"
                      >{{ titleOf(row) }}</span
                    ><Badge
                      v-if="row.status && reviewMode"
                      :variant="
                        row.status === 'approved' ? 'default' : 'secondary'
                      "
                      class="shrink-0"
                      >{{ statuses[row.status] }}</Badge
                    ><Badge v-else-if="row.archived_at" variant="outline"
                      >보관</Badge
                    >
                  </div>
                  <p class="mt-1.5 truncate text-xs text-muted-foreground">
                    {{
                      reviewMode
                        ? row.review_group === 'platform' ? '외부 플랫폼 등록' : resourceTitle(row.entity_type)
                        : row.name_ko || row.title_ko || resourceTitle(kind)
                    }}<span v-if="reviewMode" class="ml-2">{{
                      row.operation === 'update' ? '수정' : '신규'
                    }}</span>
                  </p>
                </button>
                <p
                  v-if="!rows.length"
                  class="px-4 py-16 text-center text-sm text-muted-foreground"
                >
                  {{
                    q
                      ? '검색 결과가 없습니다.'
                      : reviewMode
                        ? 'JSON을 가져오거나 자료를 추가하세요.'
                        : '등록된 자료가 없습니다.'
                  }}
                </p></template
              >
            </div>
            <div class="flex items-center justify-center gap-2 border-t p-3">
              <Button
                variant="ghost"
                size="icon-sm"
                :disabled="page === 1"
                aria-label="이전 페이지"
                @click="page--"
                ><ChevronLeft /></Button
              ><span
                class="min-w-12 text-center text-xs tabular-nums text-muted-foreground"
                >{{ page }} / {{ Math.max(1, Math.ceil(total / 30)) }}</span
              ><Button
                variant="ghost"
                size="icon-sm"
                :disabled="page * 30 >= total"
                aria-label="다음 페이지"
                @click="page++"
                ><ChevronRight
              /></Button>
            </div>
          </section>
          <section
            class="min-h-0 min-w-0"
            :class="!selected ? 'hidden lg:flex' : 'flex flex-col'"
          >
            <Empty v-if="!selected"
              ><EmptyHeader
                ><EmptyMedia variant="icon"
                  ><FileJson v-if="reviewMode" /><Database v-else /></EmptyMedia
                ><EmptyTitle>{{
                  reviewMode ? '검수할 항목을 선택하세요' : '자료를 선택하세요'
                }}</EmptyTitle
                ><EmptyDescription>{{
                  reviewMode
                    ? '원본과 수정 내용을 비교한 뒤 승인할 수 있습니다.'
                    : '상세 정보를 확인하고 수정할 수 있습니다.'
                }}</EmptyDescription></EmptyHeader
              ></Empty
            >
            <template v-else>
              <div
                class="flex items-start justify-between gap-3 border-b p-5 lg:px-7"
              >
                <div class="min-w-0">
                  <Button
                    variant="ghost"
                    size="sm"
                    class="mb-2 lg:hidden"
                    @click="guarded(() => (selected = null))"
                    ><ArrowLeft data-icon="inline-start" />목록</Button
                  >
                  <p class="mb-1.5 text-xs text-muted-foreground">
                    {{ selected.review_group === 'platform' ? '외부 플랫폼 등록' : resourceTitle(selected.entity_type || kind) }}
                  </p>
                  <h2 class="break-words text-lg font-semibold">
                    {{ titleOf(selected) }}
                  </h2>
                </div>
                <Badge variant="outline">{{
                  reviewMode
                    ? statuses[selected.status]
                    : selected.archived_at
                      ? '보관 중'
                      : '등록됨'
                }}</Badge>
              </div>
              <div v-if="reviewMode && selected.review_group === 'platform'" class="editor-scroll px-5 py-6 lg:px-7">
                <PlatformRegistration :key="selected.id" ref="platformEditor" :resources="resources" :batches="batches" :initial-batch="batchId" :account-id="selected.id" inspector @changed="platformChanged" @approved="advancePlatform" />
              </div>
              <Tabs v-else v-model="editorTab" class="min-h-0 min-w-0 flex-1 gap-0">
                <div class="border-b px-5 py-3 lg:px-7">
                  <TabsList
                    ><TabsTrigger value="fields">정보</TabsTrigger
                    ><TabsTrigger value="source">{{
                      reviewMode ? '원본 · 변경' : '저장된 데이터'
                    }}</TabsTrigger
                    ><TabsTrigger v-if="reviewMode" value="events"
                      >검수 이력</TabsTrigger
                    ></TabsList
                  >
                </div>
                <TabsContent
                  value="fields"
                  class="editor-scroll px-5 py-6 lg:px-7"
                >
                  <Alert
                    v-for="issue in selected.issues || []"
                    :key="issue.id"
                    variant="destructive"
                    class="mb-5"
                    ><AlertDescription>{{
                      issue.message
                    }}</AlertDescription></Alert
                  >
                  <ResourceForm
                    v-if="currentResource"
                    v-model="form"
                    :resource="currentResource"
                    :batch-id="reviewMode ? batchId : undefined"
                    :disabled="locked"
                  />
                </TabsContent>
                <TabsContent
                  value="source"
                  class="editor-scroll space-y-5 px-5 py-6 lg:px-7"
                >
                  <template v-if="reviewMode"
                    ><h3 class="text-sm font-medium">입력 원본</h3>
                    <pre class="data-block">{{
                      pretty(selected.original_payload)
                    }}</pre>
                    <h3 class="text-sm font-medium">현재 수정본</h3>
                    <pre class="data-block">{{ pretty(form) }}</pre>
                    <h3 class="text-sm font-medium">출처 정보</h3>
                    <pre class="data-block">{{
                      pretty(selected.provenance)
                    }}</pre>
                  </template>
                  <pre v-else class="data-block">{{ pretty(selected) }}</pre>
                </TabsContent>
                <TabsContent
                  value="events"
                  class="editor-scroll px-5 py-6 lg:px-7"
                  ><ol class="space-y-5">
                    <li
                      v-for="event in selected.events || []"
                      :key="event.id"
                      class="border-l-2 pl-4"
                    >
                      <p class="text-sm font-medium">
                        {{
                          (
                            {
                              edit: '초안 수정',
                              approve: '승인',
                              hold: '보류',
                              exclude: '제외',
                              reopen: '다시 검수',
                              invalidate_approval: '연결 변경으로 승인 해제',
                              publish: 'DB 반영',
                            } as Data
                          )[event.action] || event.action
                        }}
                      </p>
                      <p v-if="event.note" class="mt-1 text-sm">
                        {{ event.note }}
                      </p>
                      <p class="mt-1 text-xs text-muted-foreground">
                        {{ formatDate(event.created_at) }} · 수정
                        {{ event.revision }}
                      </p>
                      <details
                        v-if="event.action === 'edit'"
                        class="mt-2 text-xs"
                      >
                        <summary class="cursor-pointer text-muted-foreground">
                          수정 내역
                        </summary>
                        <pre class="data-block mt-2">{{
                          pretty(JSON.parse(event.change_data))
                        }}</pre>
                      </details>
                    </li>
                    <li
                      v-if="!selected.events?.length"
                      class="text-sm text-muted-foreground"
                    >
                      아직 검수 이력이 없습니다.
                    </li>
                  </ol></TabsContent
                >
              </Tabs>
              <div
                v-if="!(reviewMode && selected.review_group === 'platform')"
                class="flex flex-wrap items-center justify-between gap-3 border-t bg-background p-4 lg:px-7"
              >
                <span class="text-xs text-muted-foreground">{{
                  dirty
                    ? '저장하지 않은 변경이 있습니다.'
                    : reviewMode
                      ? '승인해도 아직 DB에 반영되지 않습니다.'
                      : '저장하면 새 카탈로그에 반영됩니다.'
                }}</span>
                <div
                  v-if="reviewMode && !completed"
                  class="flex flex-wrap gap-2"
                >
                  <Button
                    variant="ghost"
                    size="sm"
                    :disabled="working || dirty"
                    @click="requestReason('exclude')"
                    >제외</Button
                  ><Button
                    variant="outline"
                    size="sm"
                    :disabled="working || dirty"
                    @click="requestReason('hold')"
                    >보류</Button
                  ><Button
                    v-if="dirty"
                    size="sm"
                    :disabled="working"
                    @click="saveDraft"
                    >초안 저장</Button
                  ><Button
                    v-else-if="
                      selected.status === 'approved' ||
                      selected.status === 'excluded'
                    "
                    variant="outline"
                    size="sm"
                    :disabled="working"
                    @click="review('reopen')"
                    >다시 검수</Button
                  ><Button
                    v-else
                    size="sm"
                    :disabled="working"
                    @click="review('approve')"
                    ><Check data-icon="inline-start" />승인</Button
                  >
                </div>
                <div v-else-if="catalogMode" class="flex gap-2">
                  <Button
                    v-if="currentResource?.archivable"
                    variant="outline"
                    size="sm"
                    :disabled="working || dirty || Boolean(pending)"
                    @click="archiveOpen = true"
                    ><Archive data-icon="inline-start" />{{
                      selected.archived_at ? '보관 해제' : '보관'
                    }}</Button
                  ><Button
                    v-if="kind !== 'source_documents'"
                    size="sm"
                    :disabled="working || !dirty || Boolean(pending)"
                    @click="saveCatalog"
                    >변경 저장</Button
                  >
                </div>
              </div>
            </template>
          </section>
        </div>
        <section v-if="!booting && active === 'history'" class="space-y-9">
          <div>
            <h2 class="mb-4 text-base font-semibold">검수 묶음의 반영 작업</h2>
            <Empty v-if="!history.length" class="border"
              ><EmptyHeader
                ><EmptyTitle>아직 반영한 작업이 없습니다</EmptyTitle
                ><EmptyDescription
                  >검수함에서 반영 미리보기를 만들면 여기에
                  기록됩니다.</EmptyDescription
                ></EmptyHeader
              ></Empty
            >
            <div v-else class="divide-y rounded-2xl border">
              <article
                v-for="h in history"
                :key="h.id"
                class="flex flex-wrap items-center justify-between gap-4 p-5"
              >
                <div class="min-w-0">
                  <div class="flex items-center gap-3">
                    <h3 class="font-medium">{{ h.name }}</h3>
                    <Badge variant="secondary">{{
                      statuses[h.status] || h.status
                    }}</Badge>
                  </div>
                  <p class="mt-2 text-xs text-muted-foreground">
                    {{ formatDate(h.created_at) }}
                  </p>
                </div>
                <div
                  v-if="h.status === 'publishing' || h.status === 'ready'"
                  class="flex gap-2"
                >
                  <Button
                    size="sm"
                    variant="outline"
                    :disabled="working"
                    @click="recover(h)"
                    >결과 확인</Button
                  ><Button size="sm" :disabled="working" @click="retry(h)"
                    >같은 작업 재시도</Button
                  >
                </div>
              </article>
            </div>
          </div>
          <div>
            <h2 class="mb-4 text-base font-semibold">DB 반영 영수증</h2>
            <p
              v-if="!remoteHistory.length"
              class="text-sm text-muted-foreground"
            >
              새 카탈로그에 반영된 작업이 없습니다.
            </p>
            <div
              v-for="h in remoteHistory"
              :key="h.id"
              class="flex flex-wrap justify-between gap-3 border-b py-4 text-sm"
            >
              <span
                >{{
                  h.source_kind === 'initial_import'
                    ? '초기 반영'
                    : h.source_kind === 'manual'
                      ? '수동 저장'
                      : '묶음 반영'
                }}
                · 신규 {{ h.result_summary.created_count || 0 }} / 수정
                {{ h.result_summary.updated_count || 0 }} / 보관 변경
                {{ h.result_summary.archived_count || 0 }}</span
              ><span class="text-xs text-muted-foreground">{{
                formatDate(h.created_at)
              }}</span>
            </div>
          </div>
        </section>
        <section
          v-if="!booting && active === 'settings'"
          class="max-w-3xl space-y-9"
        >
          <section class="space-y-4">
            <h2 class="font-semibold">새 카탈로그 연결</h2>
            <div
              class="flex flex-wrap items-center justify-between gap-4 rounded-2xl border p-5"
            >
              <div>
                <p class="text-sm font-medium">
                  {{
                    connection.connected
                      ? 'Neon에 연결되었습니다'
                      : '연결을 확인해 주세요'
                  }}
                </p>
                <p class="mt-2 text-xs text-muted-foreground">
                  {{
                    connection.initialized
                      ? '초기 반영 완료 · 수동 저장 가능'
                      : '초기 검수 단계 · 직접 저장 잠금'
                  }}
                </p>
                <p
                  v-if="connection.catalog_id"
                  class="mt-2 break-all font-mono text-xs text-muted-foreground"
                >
                  {{ connection.catalog_id }}
                </p>
              </div>
              <Button
                variant="outline"
                :disabled="working"
                @click="
                  task(async () => {
                    connection = await api('/connection')
                    notice = connection.connected
                      ? '연결을 확인했습니다.'
                      : connection.message
                  })
                "
                ><RefreshCw data-icon="inline-start" />연결 확인</Button
              >
            </div>
          </section>
          <section class="space-y-4">
            <h2 class="font-semibold">화면</h2>
            <FieldGroup
              ><Field
                ><FieldLabel for="theme">화면 밝기</FieldLabel
                ><Select v-model="theme"
                  ><SelectTrigger id="theme" class="w-56"
                    ><SelectValue /></SelectTrigger
                  ><SelectContent
                    ><SelectGroup
                      ><SelectItem value="system">기기 설정 따르기</SelectItem
                      ><SelectItem value="light">라이트</SelectItem
                      ><SelectItem value="dark">다크</SelectItem></SelectGroup
                    ></SelectContent
                  ></Select
                ></Field
              ></FieldGroup
            >
          </section>
          <section class="space-y-4">
            <h2 class="font-semibold">검수 작업 백업</h2>
            <p class="text-sm leading-6 text-muted-foreground">
              초안, 승인·수정 이력과 입력 원본을 함께 내려받습니다. DB 접속
              정보는 포함하지 않습니다.
            </p>
            <Button
              variant="outline"
              :disabled="working"
              @click="
                task(() => download('/backup', 'catalog-review-backup.zip'))
              "
              ><Download data-icon="inline-start" />검수 데이터 백업</Button
            >
          </section>
        </section>
      </main>
    </SidebarInset>
  </SidebarProvider>

  <Dialog v-model:open="deleteOpen">
    <DialogContent>
      <DialogHeader><DialogTitle>검수 묶음을 삭제할까요?</DialogTitle>
        <DialogDescription>이 묶음의 초안과 승인·수정·로컬 반영 기록을 삭제합니다. 되돌릴 수 없습니다. 불러온 원본 파일과 이미 DB에 반영된 자료는 유지됩니다.</DialogDescription>
      </DialogHeader>
      <p class="font-medium break-words">{{deleteTarget?.name}}</p>
      <p v-if="dirty" class="text-sm text-muted-foreground">저장하지 않은 수정 내용도 함께 사라집니다.</p>
      <p v-if="error" role="alert" class="text-sm text-destructive">{{error}}</p>
      <DialogFooter><Button variant="outline" :disabled="working" @click="deleteOpen=false">취소</Button><Button variant="destructive" :disabled="working" @click="deleteBatch">검수 묶음 삭제</Button></DialogFooter>
    </DialogContent>
  </Dialog>
  <Dialog v-model:open="batchOpen"
    ><DialogContent
      ><DialogHeader
        ><DialogTitle>새 검수 묶음</DialogTitle
        ><DialogDescription
          >함께 검수하고 반영할 자료를 묶습니다.</DialogDescription
        ></DialogHeader
      >
      <form @submit.prevent="createBatch">
        <FieldGroup
          ><Field
            ><FieldLabel for="batch-name">묶음 이름</FieldLabel
            ><Input
              id="batch-name"
              v-model="batchName"
              maxlength="120"
              placeholder="예: 9월 아티스트 · 라이브 정리"
              autofocus /></Field></FieldGroup
        ><DialogFooter class="mt-6"
          ><Button type="submit" :disabled="working || !batchName.trim()"
            >만들기</Button
          ></DialogFooter
        >
      </form></DialogContent
    ></Dialog
  >
  <Dialog v-model:open="addOpen"
    ><DialogContent class="max-h-[90dvh] overflow-y-auto sm:max-w-3xl"
      ><DialogHeader
        ><DialogTitle>{{
          connection.initialized && !reviewMode
            ? '자료 등록'
            : '검수할 자료 추가'
        }}</DialogTitle
        ><DialogDescription>{{
          connection.initialized && !reviewMode
            ? '입력한 자료를 새 카탈로그에 저장합니다.'
            : '이 PC에 초안으로 저장합니다. 검수를 마친 뒤 DB에 반영하세요.'
        }}</DialogDescription></DialogHeader
      ><FieldGroup
        ><Field
          ><FieldLabel for="add-kind">자료 종류</FieldLabel
          ><Select v-model="addKind" :disabled="working || Boolean(pending)"
            ><SelectTrigger id="add-kind" class="w-full"
              ><SelectValue /></SelectTrigger
            ><SelectContent
              ><SelectGroup
                ><SelectItem
                  v-for="r in resources.filter(r => !reviewMode || r.name !== 'artist_external_accounts')"
                  :key="r.name"
                  :value="r.name"
                  >{{ reviewMode && r.name === 'external_accounts' ? '외부 플랫폼 등록' : r.title }}</SelectItem
                ></SelectGroup
              ></SelectContent
            ></Select
          ></Field
        ></FieldGroup
      ><PlatformRegistration v-if="reviewMode && addKind === 'external_accounts'" :key="batchId" :resources="resources" :batches="batches" :initial-batch="batchId" account-id="new" inspector @changed="platformCreated" />
      <ResourceForm
        v-else-if="addResource"
        v-model="addData"
        :key="addKind"
        :resource="addResource"
        :batch-id="!connection.initialized || reviewMode ? batchId : undefined"
        :disabled="working || Boolean(pending)"
      />
      <p v-if="error" role="alert" class="text-sm text-destructive">
        {{ error }}
      </p>
      <DialogFooter v-if="!(reviewMode && addKind === 'external_accounts')"
        ><Button :disabled="working || Boolean(pending)" @click="add"
          ><LoaderCircle
            v-if="working"
            data-icon="inline-start"
            class="animate-spin"
          />{{
            connection.initialized && !reviewMode ? 'DB에 저장' : '초안 추가'
          }}</Button
        ></DialogFooter
      ></DialogContent
    ></Dialog
  >
  <Dialog v-model:open="importOpen"
    ><DialogContent class="sm:max-w-xl"
      ><DialogHeader
        ><DialogTitle>JSON 가져오기</DialogTitle
        ><DialogDescription
          >원본 파일을 보존하고 검수할 초안을 만듭니다.</DialogDescription
        ></DialogHeader
      ><FieldGroup
        ><Field
          ><FieldLabel for="json-file">파일 선택</FieldLabel
          ><Input
            id="json-file"
            type="file"
            accept=".json,application/json"
            :disabled="working"
            @change="uploadFile"
          /><FieldDescription
            >파일당 10MiB, 최대 1,000개 항목</FieldDescription
          ></Field
        ></FieldGroup
      >
      <div class="space-y-3 border-t pt-5">
        <p class="text-sm text-muted-foreground">
          프로젝트의 db-migration/input 폴더에 넣은 파일도 불러올 수 있습니다.
        </p>
        <Button variant="outline" :disabled="working" @click="scan"
          ><FolderOpen data-icon="inline-start" />input 폴더 불러오기</Button
        >
      </div>
      <div
        v-if="scanResults.length"
        class="max-h-56 space-y-3 overflow-auto text-sm"
      >
        <div v-for="(r, i) in scanResults" :key="i">
          <p class="break-all font-medium">{{ r.file }}</p>
          <p :class="r.error ? 'text-destructive' : 'text-muted-foreground'">
            {{
              r.error ||
              (r.duplicate ? '이미 가져온 파일' : r.imported + '개 가져옴')
            }}
          </p>
        </div>
      </div>
      <p v-if="error" role="alert" class="text-sm text-destructive">
        {{ error }}
      </p></DialogContent
    ></Dialog
  >
  <Dialog v-model:open="previewOpen"
    ><DialogContent class="max-h-[90dvh] overflow-y-auto sm:max-w-4xl"
      ><DialogHeader
        ><DialogTitle>{{
          preview?.initial ? '초기 데이터 반영' : '검수 묶음 반영'
        }}</DialogTitle
        ><DialogDescription
          >아래 변경 내용을 확인한 뒤 새 DB에 반영하세요.</DialogDescription
        ></DialogHeader
      ><template v-if="preview"
        ><div class="flex flex-wrap gap-3 text-sm">
          <Badge variant="secondary">승인 {{ preview.changes.length }}개</Badge
          ><Badge variant="outline">제외 {{ preview.excluded_count }}개</Badge>
        </div>
        <p class="break-all text-xs text-muted-foreground">
          대상 카탈로그 · {{ preview.catalog_id }}
        </p>
        <div class="max-h-[50dvh] divide-y overflow-y-auto rounded-xl border">
          <details
            v-for="change in preview.changes"
            :key="change.client_ref"
            class="p-4"
          >
            <summary class="cursor-pointer text-sm">
              <span class="mr-2 text-muted-foreground">{{
                change.operation === 'create' ? '신규' : '수정'
              }}</span
              >{{ resourceTitle(change.entity_type) }} ·
              {{ titleOf(change.after) }}
            </summary>
            <div class="mt-3 grid gap-3 sm:grid-cols-2">
              <div v-if="change.before">
                <p class="mb-2 text-xs text-muted-foreground">변경 전</p>
                <pre class="data-block">{{ pretty(change.before) }}</pre>
              </div>
              <div>
                <p class="mb-2 text-xs text-muted-foreground">반영할 내용</p>
                <pre class="data-block">{{ pretty(change.after) }}</pre>
              </div>
            </div>
          </details>
        </div>
        <p v-if="error" role="alert" class="text-sm text-destructive">
          {{ error }}
        </p>
        <DialogFooter
          ><Button :disabled="working" @click="publish"
            ><LoaderCircle
              v-if="working"
              data-icon="inline-start"
              class="animate-spin"
            />{{
              preview.initial
                ? '초기 데이터 DB에 반영'
                : '승인한 자료 DB에 반영'
            }}</Button
          ></DialogFooter
        ></template
      ></DialogContent
    ></Dialog
  >
  <Dialog v-model:open="reasonOpen"
    ><DialogContent
      ><DialogHeader
        ><DialogTitle
          >{{ reasonAction === 'hold' ? '보류' : '제외' }} 사유</DialogTitle
        ><DialogDescription>{{
          reasonAction === 'hold'
            ? '추가 확인이 필요한 이유를 남겨 주세요.'
            : '이번 반영 대상에서 제외하는 이유를 남겨 주세요.'
        }}</DialogDescription></DialogHeader
      ><FieldGroup
        ><Field
          ><FieldLabel for="review-note">메모</FieldLabel
          ><Textarea
            id="review-note"
            v-model="reason"
            :rows="3" /></Field></FieldGroup
      ><DialogFooter
        ><Button
          :disabled="working || !reason.trim()"
          @click="review(reasonAction)"
          >{{ reasonAction === 'hold' ? '보류' : '제외' }}</Button
        ></DialogFooter
      ></DialogContent
    ></Dialog
  >
  <Dialog v-model:open="archiveOpen"
    ><DialogContent
      ><DialogHeader
        ><DialogTitle>{{
          selected?.archived_at ? '보관을 해제할까요?' : '자료를 보관할까요?'
        }}</DialogTitle
        ><DialogDescription
          >기존 연결과 이력은 유지됩니다. 보관 중인 자료는 새 연결 선택 목록에서
          제외됩니다.</DialogDescription
        ></DialogHeader
      >
      <p class="text-sm font-medium">{{ selected ? titleOf(selected) : '' }}</p>
      <p v-if="error" role="alert" class="text-sm text-destructive">
        {{ error }}
      </p>
      <DialogFooter
        ><Button :disabled="working" @click="archiveItem">{{
          selected?.archived_at ? '보관 해제' : '보관'
        }}</Button></DialogFooter
      ></DialogContent
    ></Dialog
  >
  <Dialog v-model:open="discardOpen"
    ><DialogContent
      ><DialogHeader
        ><DialogTitle>저장하지 않은 변경이 있습니다</DialogTitle
        ><DialogDescription
          >이동하면 현재 입력한 변경 내용은 사라집니다.</DialogDescription
        ></DialogHeader
      ><DialogFooter
        ><Button variant="outline" @click="discardOpen = false"
          >계속 편집</Button
        ><Button @click="discard">변경을 버리고 이동</Button></DialogFooter
      ></DialogContent
    ></Dialog
  >
</template>
