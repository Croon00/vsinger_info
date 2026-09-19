<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { api } from '@/api/client'
import type { Artist, ArtistKind, SourceType } from '@/api/types'
import AppModal from '@/components/AppModal.vue'
import PageHeader from '@/components/PageHeader.vue'
import StatusPill from '@/components/StatusPill.vue'

const queryClient = useQueryClient()
const artistsQuery = useQuery({ queryKey: ['artists', 'registrations'], queryFn: api.artists.registrations })
const artistModal = ref(false)
const sourceArtist = ref<Artist | null>(null)
const feedback = ref('')
const artistForm = reactive({
  name: '',
  display_name: '',
  artist_kind: 'vtuber' as ArtistKind,
  agency: '',
  x_username: '',
  notes: '',
  profile_intro: '',
  debut_date: '',
})
const sourceForm = reactive({
  source_type: 'x' as SourceType,
  label: '',
  value: '',
  is_active: true,
})

const refresh = () => queryClient.invalidateQueries({ queryKey: ['artists'] })
const createArtist = useMutation({
  mutationFn: api.artists.create,
  onSuccess: async () => {
    await refresh()
    artistModal.value = false
    Object.assign(artistForm, {
      name: '',
      display_name: '',
      artist_kind: 'vtuber',
      agency: '',
      x_username: '',
      notes: '',
      profile_intro: '',
      debut_date: '',
    })
    feedback.value = '아티스트를 등록했습니다.'
  },
})
const addSource = useMutation({
  mutationFn: ({ artistId }: { artistId: number }) => api.artists.addSource(artistId, sourceForm),
  onSuccess: async () => {
    await refresh()
    sourceArtist.value = null
    Object.assign(sourceForm, { source_type: 'x', label: '', value: '', is_active: true })
    feedback.value = '수집 소스를 추가했습니다.'
  },
})
const removeArtist = useMutation({
  mutationFn: api.artists.remove,
  onSuccess: refresh,
})
const removeSource = useMutation({
  mutationFn: ({ artistId, sourceId }: { artistId: number; sourceId: number }) =>
    api.artists.removeSource(artistId, sourceId),
  onSuccess: refresh,
})
const updateVisibility = useMutation({
  mutationFn: ({ artistId, field, value }: { artistId: number; field: 'show_in_spotify' | 'show_in_lyrics' | 'show_in_youtube_lives'; value: boolean }) =>
    api.artists.update(artistId, { [field]: value }),
  onMutate: async ({ artistId, field, value }) => {
    await queryClient.cancelQueries({ queryKey: ['artists'] })
    const previous = queryClient.getQueryData<Artist[]>(['artists'])
    queryClient.setQueryData<Artist[]>(['artists'], (rows = []) =>
      rows.map((artist) => artist.id === artistId ? { ...artist, [field]: value } : artist),
    )
    return { previous }
  },
  onError: (_error, _variables, context) => {
    if (context?.previous) queryClient.setQueryData(['artists'], context.previous)
  },
  onSettled: refresh,
})
const artistKindOptions = [
  { label: 'VTuber', value: 'vtuber' },
  { label: '가수', value: 'singer' },
]
const sourceTypeOptions = [
  { label: 'X 계정', value: 'x' },
  { label: '공식 사이트', value: 'official_site' },
  { label: '티켓 사이트', value: 'ticket_site' },
  { label: 'RSS', value: 'rss' },
  { label: '기타', value: 'other' },
]

function submitArtist(): void {
  createArtist.mutate({
    name: artistForm.name,
    display_name: artistForm.display_name || undefined,
    artist_kind: artistForm.artist_kind,
    agency: artistForm.agency || undefined,
    x_username: artistForm.x_username || undefined,
    notes: artistForm.notes || undefined,
    profile_intro: artistForm.profile_intro || undefined,
    debut_date: artistForm.debut_date || undefined,
  })
}

function confirmArtistDelete(artist: Artist): void {
  if (window.confirm(`${artist.display_name || artist.name}과 연결된 소스를 모두 삭제할까요?`)) {
    removeArtist.mutate(artist.id)
  }
}

function sourceLabel(type: SourceType): string {
  return { x: 'X', official_site: '공식 사이트', ticket_site: '티켓', rss: 'RSS', other: '기타' }[type]
}
</script>

<template>
  <div class="page">
    <PageHeader
      eyebrow="SOURCE REGISTRY / 02"
      title="아티스트와 공식 소스"
      description="신뢰할 수 있는 출처만 등록해 수집 범위를 선명하게 관리합니다."
    >
      <UButton class="button button--primary" @click="artistModal = true">+ 새 아티스트</UButton>
    </PageHeader>

    <div v-if="feedback" class="alert alert--success" @click="feedback = ''">{{ feedback }}</div>
    <div v-if="artistsQuery.isError.value" class="alert alert--error">
      목록을 불러오지 못했습니다. FastAPI 연결을 확인해 주세요.
    </div>
    <div v-if="updateVisibility.isError.value" class="alert alert--error">노출 설정을 변경하지 못했습니다. API 연결을 확인해 주세요.</div>

    <section class="panel panel--table">
      <div class="panel__heading">
        <div>
          <p class="eyebrow">MONITORED ARTISTS</p>
          <h2>등록 목록</h2>
        </div>
        <span class="count-label">{{ artistsQuery.data.value?.length || 0 }} ARTISTS</span>
      </div>
      <div v-if="artistsQuery.isPending.value" class="skeleton-list"><i /><i /><i /></div>
      <div v-else-if="artistsQuery.data.value?.length" class="artist-list">
        <article v-for="artist in artistsQuery.data.value" :key="artist.id" class="artist-row">
          <div class="artist-avatar">{{ (artist.display_name || artist.name).slice(0, 1) }}</div>
          <div class="artist-row__identity">
            <strong>{{ artist.display_name || artist.name }}</strong>
            <span>{{ artist.artist_kind === 'vtuber' ? 'VTUBER' : 'SINGER' }}</span>
            <span>{{ artist.name }} · ID {{ artist.id }}</span>
            <p v-if="artist.notes">{{ artist.notes }}</p>
          </div>
          <div class="source-tags">
            <span v-for="source in artist.sources" :key="source.id" class="source-tag">
              <b>{{ sourceLabel(source.source_type) }}</b>
              {{ source.label || source.value }}
              <UButton
                :aria-label="`${source.label || source.value} 삭제`"
                @click="removeSource.mutate({ artistId: artist.id, sourceId: source.id })"
              >
                ×
              </UButton>
            </span>
            <span v-if="!artist.sources.length" class="muted">연결된 소스 없음</span>
            <UButton class="button button--ghost source-add-button" @click="sourceArtist = artist">+ X 계정 추가</UButton>
          </div>
          <div class="artist-row__controls">
            <div class="visibility-controls" aria-label="화면 노출 설정">
              <UButton :class="{ active: artist.show_in_spotify }" :aria-pressed="artist.show_in_spotify" @click="updateVisibility.mutate({ artistId: artist.id, field: 'show_in_spotify', value: !artist.show_in_spotify })"><span>Spotify</span><b>{{ artist.show_in_spotify ? '표시' : '숨김' }}</b></UButton>
              <UButton :class="{ active: artist.show_in_lyrics }" :aria-pressed="artist.show_in_lyrics" @click="updateVisibility.mutate({ artistId: artist.id, field: 'show_in_lyrics', value: !artist.show_in_lyrics })"><span>가사</span><b>{{ artist.show_in_lyrics ? '표시' : '숨김' }}</b></UButton>
              <UButton :class="{ active: artist.show_in_youtube_lives }" :aria-pressed="artist.show_in_youtube_lives" @click="updateVisibility.mutate({ artistId: artist.id, field: 'show_in_youtube_lives', value: !artist.show_in_youtube_lives })"><span>우타와꾸</span><b>{{ artist.show_in_youtube_lives ? '표시' : '숨김' }}</b></UButton>
            </div>
            <div class="source-actions">
              <StatusPill :label="artist.sources.some((source) => source.is_active) ? 'X 수집 중' : '수집 대기'" :tone="artist.sources.some((source) => source.is_active) ? 'green' : 'muted'" />
              <UButton class="icon-button icon-button--danger" aria-label="아티스트 삭제" @click="confirmArtistDelete(artist)">×</UButton>
            </div>
          </div>
        </article>
      </div>
      <div v-else class="empty-state">
        <span>◉</span><strong>첫 아티스트를 등록해 보세요</strong>
        <p>X 계정이나 공식 사이트를 함께 등록하면 수집 준비가 끝납니다.</p>
      </div>
    </section>

    <AppModal
      :open="artistModal"
      title="새 아티스트 등록"
      description="표시 이름과 첫 X 계정을 한 번에 등록할 수 있습니다."
      @close="artistModal = false"
    >
      <form class="form-grid" @submit.prevent="submitArtist">
        <label>기준 이름<UInput v-model="artistForm.name" required maxlength="120" placeholder="예: HACHI" /></label>
        <label>표시 이름<UInput v-model="artistForm.display_name" maxlength="120" placeholder="예: HACHI / ハチ" /></label>
        <label>아티스트 유형<USelect v-model="artistForm.artist_kind" :items="artistKindOptions" /></label>
        <label v-if="artistForm.artist_kind === 'vtuber'">소속<UInput v-model="artistForm.agency" maxlength="120" placeholder="예: RK Music" /></label>
        <label class="form-grid__wide">X 사용자명<UInput v-model="artistForm.x_username" placeholder="@HACHI_08" /></label>
        <label class="form-grid__wide">메모<UTextarea v-model="artistForm.notes" rows="3" placeholder="레이블, 활동 그룹 등 운영 메모" /></label>
        <label>데뷔일<UInput v-model="artistForm.debut_date" type="date" /></label>
        <label class="form-grid__wide">소개글<UTextarea v-model="artistForm.profile_intro" rows="4" placeholder="아티스트 소개 페이지에 표시할 간단한 소개" /></label>
        <p v-if="createArtist.error.value" class="form-error">{{ createArtist.error.value.message }}</p>
        <div class="form-actions">
          <UButton type="button" class="button button--ghost" @click="artistModal = false">취소</UButton>
          <UButton class="button button--primary" :disabled="createArtist.isPending.value">
            {{ createArtist.isPending.value ? '등록 중…' : '등록하기' }}
          </UButton>
        </div>
      </form>
    </AppModal>

    <AppModal
      :open="Boolean(sourceArtist)"
      :title="`${sourceArtist?.display_name || sourceArtist?.name || ''} 소스 추가`"
      description="공식 계정과 공개 페이지만 등록해 주세요."
      @close="sourceArtist = null"
    >
      <form class="form-grid" @submit.prevent="sourceArtist && addSource.mutate({ artistId: sourceArtist.id })">
        <label>
          소스 종류
          <USelect v-model="sourceForm.source_type" :items="sourceTypeOptions" />
        </label>
        <label>표시 이름<UInput v-model="sourceForm.label" placeholder="Official news" /></label>
        <label class="form-grid__wide">URL 또는 사용자명<UInput v-model="sourceForm.value" required maxlength="500" /></label>
        <label class="check-label"><UCheckbox v-model="sourceForm.is_active" /> 즉시 수집 활성화</label>
        <p v-if="addSource.error.value" class="form-error">{{ addSource.error.value.message }}</p>
        <div class="form-actions">
          <UButton type="button" class="button button--ghost" @click="sourceArtist = null">취소</UButton>
          <UButton class="button button--primary" :disabled="addSource.isPending.value">소스 추가</UButton>
        </div>
      </form>
    </AppModal>
  </div>
</template>
