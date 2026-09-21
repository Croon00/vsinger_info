<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useMutation, useQuery } from '@tanstack/vue-query'
import { api } from '@/api/client'
import type { Artist, ArtistKind, LyricsSourceMode } from '@/api/types'
import PageHeader from '@/components/PageHeader.vue'

const artistKind = ref<ArtistKind>('vtuber')
const languageOptions = [
  { label: '일본어', value: 'ja' },
  { label: '한국어', value: 'ko' },
  { label: '영어', value: 'en' },
]
const lyricsSourceOptions = [
  { label: 'YouTube 수동 자막', value: 'caption' },
  { label: '영상 설명', value: 'description' },
  { label: '상단 댓글', value: 'comment' },
  { label: '음원 전사', value: 'audio' },
]
const agencyFilter = ref('all')
const selectedArtist = ref<Artist | null>(null)
const resultMessage = ref('')
const form = reactive({ title: '', youtube_url: '', source_mode: 'caption' as LyricsSourceMode, language_code: 'ja' })

const artistsQuery = useQuery({ queryKey: ['artists'], queryFn: api.artists.list })
const agenciesQuery = useQuery({ queryKey: ['artist-agencies'], queryFn: api.artistAgencies.list })
const artists = computed(() => (artistsQuery.data.value ?? []).filter((artist) =>
  artist.show_in_lyrics
  &&
  artist.artist_kind === artistKind.value
  && (artistKind.value !== 'vtuber' || agencyFilter.value === 'all' || artist.agency === agencyFilter.value),
))
const createSong = useMutation({
  mutationFn: api.songs.createFromYouTube,
  onSuccess: (song) => {
    resultMessage.value = `곡 #${song.id} ${song.artist_name} - ${song.title} 저장 완료`
    Object.assign(form, { title: '', youtube_url: '', source_mode: 'caption', language_code: 'ja' })
  },
})

function chooseKind(kind: ArtistKind): void {
  artistKind.value = kind
  agencyFilter.value = 'all'
  selectedArtist.value = null
}
function submit(): void {
  if (!selectedArtist.value) return
  createSong.mutate({ artist_id: selectedArtist.value.id, ...form })
}
function artistImage(artist: Artist): string | undefined {
  if (artist.spotify_image_url) return artist.spotify_image_url
  const source = artist.sources.find((item) => item.source_type === 'x')
  if (!source) return undefined
  const username = source.value.includes('/') ? source.value.split('/').filter(Boolean).pop() : source.value.replace(/^@/, '')
  return username ? `https://unavatar.io/x/${encodeURIComponent(username)}` : undefined
}
</script>

<template>
  <div class="page lyrics-registration-page">
    <PageHeader eyebrow="LYRICS LIBRARY" title="YouTube 곡 · 가사 등록" description="아티스트를 선택하고 YouTube 영상에서 원문 가사, 번역과 발음을 생성해 저장합니다." />
    <div class="artist-kind-picker">
      <UButton :class="{ active: artistKind === 'vtuber' }" @click="chooseKind('vtuber')"><span>VIRTUAL ARTIST</span><strong>VTuber</strong><em>{{ (artistsQuery.data.value || []).filter(a => a.artist_kind === 'vtuber').length }}명</em></UButton>
      <UButton :class="{ active: artistKind === 'singer' }" @click="chooseKind('singer')"><span>MUSIC ARTIST</span><strong>가수</strong><em>{{ (artistsQuery.data.value || []).filter(a => a.artist_kind === 'singer').length }}명</em></UButton>
    </div>
    <div v-if="artistKind === 'vtuber'" class="agency-filter">
      <UButton :class="{ active: agencyFilter === 'all' }" @click="agencyFilter = 'all'">전체</UButton>
      <UButton v-for="agency in agenciesQuery.data.value || []" :key="agency.id" :class="{ active: agencyFilter === agency.name }" @click="agencyFilter = agency.name">{{ agency.name === 'KAMITSUBAKI STUDIO' ? 'KAMITSUBAKI' : agency.name }}</UButton>
    </div>
    <section class="panel">
      <div class="section-heading"><div><p class="eyebrow">SELECT ARTIST</p><h2>아티스트 선택</h2></div><span class="count-label">{{ artists.length }} ARTISTS</span></div>
      <div class="lyrics-artist-grid">
        <UButton v-for="artist in artists" :key="artist.id" class="lyrics-artist-card" :class="{ active: selectedArtist?.id === artist.id }" @click="selectedArtist = artist">
          <span><b>{{ (artist.display_name || artist.name).slice(0, 1) }}</b><img v-if="artistImage(artist)" :src="artistImage(artist)" :alt="artist.display_name || artist.name" /></span>
          <strong>{{ artist.display_name || artist.name }}</strong><small>{{ artist.agency || (artist.artist_kind === 'vtuber' ? 'VTUBER' : 'SINGER') }}</small>
        </UButton>
      </div>
    </section>
    <section v-if="selectedArtist" class="panel lyrics-song-form-panel">
      <div class="selected-artist-line"><strong>{{ selectedArtist.display_name || selectedArtist.name }}</strong><span>{{ selectedArtist.agency || '' }}</span></div>
      <form class="form-grid" @submit.prevent="submit">
        <label>곡 제목<UInput v-model="form.title" required maxlength="200" placeholder="원문 곡 제목" /></label>
        <label>원문 언어<USelect v-model="form.language_code" :items="languageOptions" /></label>
        <label class="form-grid__wide">YouTube URL<UInput v-model="form.youtube_url" type="url" required placeholder="https://www.youtube.com/watch?v=..." /></label>
        <label class="form-grid__wide">가사 추출 방식<USelect v-model="form.source_mode" :items="lyricsSourceOptions" /></label>
        <p class="form-grid__wide lyrics-cost-note">음원 전사는 처리 시간이 길고 비용이 발생할 수 있습니다. 기본적으로 수동 자막을 권장합니다.</p>
        <p v-if="createSong.error.value" class="form-error form-grid__wide">{{ createSong.error.value.message }}</p>
        <div class="form-actions"><UButton class="button button--primary" :disabled="createSong.isPending.value">{{ createSong.isPending.value ? '가사 추출·번역·저장 중…' : '곡과 가사 저장' }}</UButton></div>
      </form>
    </section>
    <div v-if="resultMessage" class="alert alert--success">{{ resultMessage }}</div>
  </div>
</template>

<style scoped>
.lyrics-artist-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-top:16px}.lyrics-artist-card{min-height:210px;padding:20px;border:1px solid var(--line);border-radius:11px;color:#8290a4;background:rgba(255,255,255,.015);cursor:pointer}.lyrics-artist-card>span{position:relative;display:grid;place-items:center;width:92px;height:92px;margin:0 auto 13px;overflow:hidden;border-radius:9px;color:var(--cyan);background:rgba(50,214,255,.08);font-size:22px}.lyrics-artist-card img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}.lyrics-artist-card strong,.lyrics-artist-card small{display:block}.lyrics-artist-card strong{overflow:hidden;color:#dce5ef;font-size:15px;text-overflow:ellipsis;white-space:nowrap}.lyrics-artist-card small{margin-top:7px;font:10px ui-monospace,monospace}.lyrics-artist-card:hover,.lyrics-artist-card.active{border-color:var(--cyan);background:rgba(50,214,255,.07);transform:translateY(-2px)}.lyrics-song-form-panel{margin-top:18px}.selected-artist-line{display:flex;justify-content:space-between;margin-bottom:18px;padding-bottom:14px;border-bottom:1px solid var(--line)}.selected-artist-line span,.lyrics-cost-note{color:#718096;font-size:9px}@media(max-width:1100px){.lyrics-artist-grid{grid-template-columns:repeat(3,minmax(0,1fr))}}@media(max-width:700px){.lyrics-artist-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
</style>

<style scoped>
.lyrics-artist-card { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; text-align: center; }
.lyrics-artist-card > span { flex: none; }
.lyrics-artist-card strong { max-width: 100%; white-space: normal; overflow-wrap: anywhere; }
@media (max-width: 600px) {
  .lyrics-artist-card { min-width: 0; min-height: 175px; padding: 12px; }
  .lyrics-artist-card > span { width: min(80px, 100%); height: auto; aspect-ratio: 1; }
  .selected-artist-line { flex-wrap: wrap; gap: 10px; }
}
</style>
