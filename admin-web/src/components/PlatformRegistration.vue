<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { Plus, Trash2, ChevronLeft, ChevronRight } from '@lucide/vue'
import { api, titleOf, statuses, type Data, type Resource } from '@/lib/api'
import ResourceForm from './ResourceForm.vue'
import RelationPicker from './RelationPicker.vue'
import { Textarea } from '@/components/ui/textarea'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Field, FieldLabel } from '@/components/ui/field'
import { Select, SelectTrigger, SelectValue, SelectContent, SelectGroup, SelectItem } from '@/components/ui/select'
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog'
const props = defineProps<{ resources: Resource[]; batches: Data[]; initialBatch: string; embedded?: boolean; accountId?: string; inspector?: boolean }>()
const emit = defineEmits<{ changed: [item?: Data]; batch: [id: string]; approved: [id: string] }>()
const batchId = ref(props.initialBatch || props.batches.find(b => b.status !== 'published')?.id || '')
const account = ref<Data | null>(null), artists = ref<Data[]>([]), rows = ref<Data[]>([])
const page = ref(1), total = ref(0), busy = ref(false), error = ref(''), message = ref('')
const existingAccount = ref<number | null>(null)
const baseline = ref(''), discardOpen = ref(false)
let continuation: (() => void) | null = null
const accountResource = computed(() => props.resources.find(r => r.name === 'external_accounts')!)
const linkResource = computed(() => {
  const resource = props.resources.find(r => r.name === 'artist_external_accounts')!
  return { ...resource, fields: resource.fields.filter(f => f.name !== 'account_id') }
})
const snapshot = () => JSON.stringify({ account: account.value, artists: artists.value })
const dirty = computed(() => !!account.value && snapshot() !== baseline.value)
const completed = computed(() => props.batches.find(b => b.id === batchId.value)?.status === 'published')
defineExpose({ dirty, busy })
function guard(fn: () => void) {
  if (dirty.value) { continuation = fn; discardOpen.value = true } else fn()
}
function discard() { discardOpen.value = false; continuation?.(); continuation = null }
function beforeUnload(event: BeforeUnloadEvent) { if (dirty.value) event.preventDefault() }
onMounted(() => {
  window.addEventListener('beforeunload', beforeUnload)
  if (props.accountId === 'new') newAccount()
  else if (props.accountId) void run(async () => { accept((await api('/platform-registrations/' + props.accountId)).data) })
  else void run(load)
})
onBeforeUnmount(() => window.removeEventListener('beforeunload', beforeUnload))
async function run(fn: () => Promise<void>) {
  if (busy.value) return
  busy.value = true; error.value = ''; message.value = ''
  try { await fn() } catch (e) { error.value = (e as Error).message } finally { busy.value = false }
}
async function load() {
  if (props.inspector) return
  if (!batchId.value) { rows.value = []; total.value = 0; return }
  const result = await api('/drafts?' + new URLSearchParams({ batch_id: batchId.value, kind: 'external_accounts', page: String(page.value), page_size: '20' }))
  rows.value = result.items; total.value = result.total
}
function accept(group: Data) {
  const adapt = (r: Data) => ({ ...r, data: r.current_payload })
  account.value = adapt(group.account); artists.value = group.artists.map(adapt); baseline.value = snapshot()
}
function choose(row: Data) { guard(() => void run(async () => { accept((await api('/platform-registrations/' + row.id)).data) })) }
function changeBatch(id: any) { guard(() => void run(async () => {
  batchId.value = String(id); emit('batch', batchId.value); page.value = 1; account.value = null; artists.value = []; await load()
})) }
function changePage(delta: number) { guard(() => void run(async () => { page.value += delta; await load() })) }
function newAccount() { guard(() => {
  account.value = { client_ref: 'account:' + crypto.randomUUID(), data: { collection_enabled: false } }
  artists.value = []; baseline.value = ''
}) }
async function newBatch() {
  guard(() => void run(async () => {
    batchId.value = (await api('/batches', 'POST', { name: '외부 플랫폼 등록' })).data.id
    emit('batch', batchId.value); emit('changed'); account.value = null; artists.value = []; page.value = 1; await load()
  }))
}
function addArtist() { artists.value.push({ client_ref: 'account-link:' + crypto.randomUUID(), data: { relationship: 'owner', is_primary: false, position: artists.value.length } }) }
function fromCatalog() { guard(() => void run(async () => {
  accept((await api('/platform-registrations/from-catalog', 'POST', { batch_id: batchId.value, account_id: existingAccount.value })).data)
  emit('changed'); await load()
})) }
async function save() { await run(async () => {
  const clean = (item: Data) => ({ id: item.id, revision: item.revision, client_ref: item.client_ref, data: item.data })
  const result = await api('/platform-registrations', 'POST', { batch_id: batchId.value, account: clean(account.value!), artists: artists.value.map(clean) })
  accept(result.data); changed(); await load(); message.value = '계정과 아티스트 연결을 함께 저장했습니다.'
}) }
async function review(item: Data, action: string) { await run(async () => {
  try {
    await api('/drafts/' + item.id + '/review', 'POST', { revision: item.revision, action, ...(action === 'exclude' ? { note: '외부 플랫폼 등록 화면에서 연결 제외' } : {}) })
    message.value = action === 'approve' ? '승인했습니다. 상단 반영 미리보기에서 DB에 반영하세요.' : '검수 상태를 변경했습니다.'
  } finally {
    accept((await api('/platform-registrations/' + account.value!.id)).data); changed(); await load()
  }
}) }
const groupState = computed(() => {
  const states = [account.value?.status, ...artists.value.map(a => a.status)]
  if (states.every(s => s === states[0])) return states[0] || 'pending'
  return ['blocked', 'editing', 'pending', 'held', 'approved', 'published', 'excluded'].find(s => states.includes(s)) || 'pending'
})
function changed() { emit('changed', { id: account.value?.id, status: groupState.value, current_payload: account.value?.data }) }
const reasonOpen = ref(false), reasonAction = ref('hold'), note = ref('')
function askReason(action: string) { reasonAction.value = action; note.value = ''; reasonOpen.value = true }
async function groupReview(action: string) { await run(async () => {
  const id = account.value!.id
  const result = await api('/platform-registrations/' + id + '/review', 'POST', {
    items: [account.value!, ...artists.value].map(m => ({ id: m.id, revision: m.revision })),
    action, note: note.value || null,
  })
  accept(result.data); changed(); reasonOpen.value = false
  message.value = action === 'approve' ? '외부 플랫폼 등록을 승인했습니다.' : '검수 상태를 변경했습니다.'
  if (action === 'approve') emit('approved', id)
}) }
</script>
<template>
  <section class="flex flex-col gap-5">
    <Alert v-if="error" variant="destructive" role="alert"><AlertTitle>작업을 완료하지 못했습니다</AlertTitle><AlertDescription>{{ error }}</AlertDescription></Alert>
    <Alert v-if="message" role="status"><AlertDescription>{{ message }}</AlertDescription></Alert>
    <div v-if="!inspector" class="flex flex-wrap items-center gap-2">
      <Select v-if="!embedded" :model-value="batchId" :disabled="busy" @update:model-value="changeBatch">
        <SelectTrigger class="w-full sm:w-72" aria-label="외부 플랫폼 검수 묶음"><SelectValue placeholder="검수 묶음 선택" /></SelectTrigger>
        <SelectContent><SelectGroup><SelectItem v-for="b in batches" :key="b.id" :value="b.id">{{ b.name }}</SelectItem></SelectGroup></SelectContent>
      </Select>
      <Button v-if="!embedded" variant="outline" :disabled="busy" @click="newBatch">새 검수 묶음</Button>
      <Button :disabled="busy || !batchId || completed" @click="newAccount"><Plus />플랫폼 계정 추가</Button>
    </div>
    <div v-if="!inspector && batchId && !completed" class="flex flex-wrap items-end gap-2">
      <Field class="w-full sm:w-80"><FieldLabel for="existing-platform">기존 DB 계정</FieldLabel><RelationPicker id="existing-platform" v-model="existingAccount" target="external_accounts" label="기존 DB 계정" :disabled="busy" /></Field>
      <Button variant="outline" :disabled="busy || !existingAccount" @click="fromCatalog">계정과 연결 불러오기</Button>
    </div>
    <p v-if="!inspector" class="text-sm text-muted-foreground">계정 정보와 연결 아티스트를 함께 검토합니다. 초안 저장·승인 후 상단 반영 미리보기에서 DB에 반영하세요.</p>
    <div :class="inspector ? 'min-w-0' : 'grid min-w-0 gap-6 lg:grid-cols-[260px_minmax(0,1fr)]'">
      <aside v-if="!inspector" class="flex min-w-0 flex-col gap-2">
        <p v-if="!rows.length" class="py-4 text-sm text-muted-foreground">이 묶음에 등록된 플랫폼 계정이 없습니다.</p>
        <Button v-for="row in rows" :key="row.id" :variant="account?.id === row.id ? 'secondary' : 'ghost'" class="h-auto justify-start py-3" :disabled="busy" @click="choose(row)">
          <span class="flex min-w-0 flex-col items-start gap-1"><span class="max-w-full truncate">{{ titleOf(row) }}</span><span class="text-xs text-muted-foreground">{{ row.current_payload.platform }} · {{ statuses[row.status] }}</span></span>
        </Button>
        <div v-if="total > 20" class="flex justify-center gap-2">
          <Button variant="outline" size="icon-sm" aria-label="이전 계정 페이지" :disabled="busy || page === 1" @click="changePage(-1)"><ChevronLeft /></Button>
          <Button variant="outline" size="icon-sm" aria-label="다음 계정 페이지" :disabled="busy || page * 20 >= total" @click="changePage(1)"><ChevronRight /></Button>
        </div>
      </aside>
      <div v-if="account" :class="inspector ? 'flex min-w-0 flex-col gap-6' : 'flex min-w-0 flex-col gap-6 rounded-xl border p-4 sm:p-6'">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <h2 class="font-semibold">플랫폼 계정 정보</h2>
          <div class="flex items-center gap-2"><Badge variant="outline">{{ statuses[account.status] || '작성 중' }}</Badge>
            <Button v-if="!inspector && account.id && account.status !== 'approved' && !completed" size="sm" variant="outline" :disabled="busy || dirty" @click="review(account, 'approve')">계정 승인</Button>
          </div>
        </div>
        <ResourceForm v-model="account.data" :resource="accountResource" :batch-id="batchId" :disabled="busy || completed" />
        <section class="flex flex-col gap-4 border-t pt-6">
          <div class="flex items-center justify-between gap-2"><h2 class="font-semibold">연결 아티스트</h2><Button size="sm" variant="outline" :disabled="busy || completed" @click="addArtist"><Plus />아티스트 추가</Button></div>
          <p v-if="!artists.length" class="text-sm text-muted-foreground">이 계정을 사용하는 아티스트를 추가하세요. 공유 계정은 여러 명을 연결할 수 있습니다.</p>
          <section v-for="(link, index) in artists" :key="link.client_ref" class="flex flex-col gap-4 rounded-lg border p-4">
            <div class="flex flex-wrap items-center justify-between gap-2">
              <h3 class="text-sm font-medium">연결 {{ index + 1 }}</h3>
              <div class="flex flex-wrap items-center gap-2">
                <Badge variant="outline">{{ statuses[link.status] || '작성 중' }}</Badge>
                <template v-if="!completed">
                  <Button v-if="!inspector && link.id && !['approved', 'excluded'].includes(link.status)" size="sm" variant="outline" :disabled="busy || dirty" @click="review(link, 'approve')">연결 승인</Button>
                  <Button v-if="link.status === 'excluded'" size="sm" variant="outline" :disabled="busy || dirty" @click="review(link, 'reopen')">다시 검수</Button>
                  <Button v-else-if="link.id" size="sm" variant="ghost" :disabled="busy || dirty" @click="review(link, 'exclude')">연결 제외</Button>
                  <Button v-else size="icon-sm" variant="ghost" :aria-label="'연결 ' + (index + 1) + ' 삭제'" :disabled="busy" @click="artists.splice(index, 1)"><Trash2 /></Button>
                </template>
              </div>
            </div>
            <ResourceForm v-model="link.data" :resource="linkResource" :batch-id="batchId" :disabled="busy || completed || link.status === 'excluded'" />
          </section>
        </section>
        <details v-if="inspector && account.id" class="text-sm">
          <summary class="cursor-pointer text-muted-foreground">원본 · 변경</summary>
          <div v-for="item in [account, ...artists]" :key="item.id" class="mt-3 flex flex-col gap-2">
            <p class="font-medium">{{ item === account ? '계정 정보' : '아티스트 연결' }}</p>
            <span class="text-xs text-muted-foreground">입력 원본</span><pre class="data-block">{{ JSON.stringify(item.original_payload, null, 2) }}</pre>
            <span class="text-xs text-muted-foreground">현재 내용</span><pre class="data-block">{{ JSON.stringify(item.data, null, 2) }}</pre>
          </div>
        </details>
        <div class="flex flex-wrap items-center justify-end gap-3">
          <span v-if="dirty" class="text-xs text-muted-foreground">저장하지 않은 변경사항</span>
          <template v-if="inspector && account.id && !dirty && !completed">
            <Button variant="ghost" :disabled="busy" @click="askReason('exclude')">제외</Button>
            <Button variant="outline" :disabled="busy" @click="askReason('hold')">보류</Button>
            <Button v-if="['approved', 'excluded'].includes(groupState)" variant="outline" :disabled="busy" @click="groupReview('reopen')">다시 검수</Button>
            <Button v-else :disabled="busy" @click="groupReview('approve')">승인</Button>
          </template>
          <Button v-if="!inspector || dirty" :disabled="busy || completed || !dirty" @click="save">계정과 연결 저장</Button>
        </div>
      </div>
      <p v-else class="py-8 text-sm text-muted-foreground">계정을 선택하거나 새 플랫폼 계정을 추가하세요.</p>
    </div>
  </section>
  <Dialog v-model:open="reasonOpen"><DialogContent><DialogHeader><DialogTitle>{{ reasonAction === 'hold' ? '보류 사유' : '제외 사유' }}</DialogTitle><DialogDescription>계정과 연결을 함께 {{ reasonAction === 'hold' ? '보류' : '제외' }}합니다.</DialogDescription></DialogHeader><Field><FieldLabel for="platform-review-note">사유</FieldLabel><Textarea id="platform-review-note" v-model="note" /></Field><DialogFooter><Button :disabled="busy || !note.trim()" @click="groupReview(reasonAction)">확인</Button></DialogFooter></DialogContent></Dialog>
  <Dialog v-model:open="discardOpen"><DialogContent><DialogHeader><DialogTitle>변경사항을 버릴까요?</DialogTitle><DialogDescription>저장하지 않은 계정 정보와 아티스트 연결이 있습니다.</DialogDescription></DialogHeader><DialogFooter><Button variant="outline" @click="discardOpen = false">계속 편집</Button><Button variant="destructive" @click="discard">변경사항 버리기</Button></DialogFooter></DialogContent></Dialog>
</template>
