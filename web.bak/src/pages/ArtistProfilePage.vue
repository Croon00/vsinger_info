<script setup lang="ts">
import { computed } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import { useRoute, useRouter } from 'vue-router'
import { api } from '@/api/client'
import type { Artist, EventCandidate } from '@/api/types'

const route = useRoute(); const router = useRouter()
const artistId = computed(() => Number(route.params.artistId))
const artistsQuery = useQuery({ queryKey: ['artists'], queryFn: api.artists.list })
const eventsQuery = useQuery({ queryKey: ['events', 'profile', artistId], queryFn: () => api.events.list(undefined, artistId.value, 'live_event') })
const artist = computed(() => artistsQuery.data.value?.find((item) => item.id === artistId.value || item.related_artist_ids?.includes(artistId.value)))
const events = computed(() => (eventsQuery.data.value || [])
  .filter(showInProfileTimeline)
  .sort((a, b) => String(a.starts_at || '').localeCompare(String(b.starts_at || ''))))
function image(value: Artist): string | undefined { if (value.spotify_image_url) return value.spotify_image_url; const source = value.sources.find((item) => item.source_type === 'x'); const name = source?.value.includes('/') ? source?.value.split('/').filter(Boolean).pop() : source?.value.replace(/^@/, ''); return name ? `https://unavatar.io/x/${encodeURIComponent(name)}` : undefined }
function hideBrokenImage(event: Event): void { (event.currentTarget as HTMLImageElement).style.display = 'none' }
function date(value: string | null): string { if (!value) return '날짜 미정'; const parsed = new Date(value); return Number.isNaN(parsed.getTime()) ? value : new Intl.DateTimeFormat('ko-KR', { year: 'numeric', month: 'long', day: 'numeric' }).format(parsed) }
function year(value: string | null): string { return value ? (value.match(/^\d{4}/)?.[0] || 'DATE') : 'DATE' }
function isDetailed(event: EventCandidate): boolean { return Boolean(event.venue || event.price_text || event.capacity_text || event.setlist_json || event.merchandise_json) }
function showInProfileTimeline(event: EventCandidate): boolean {
  const text = [event.title, event.raw_text, event.venue, event.source_url, event.ticket_url]
    .filter(Boolean).join(' ').toLowerCase()
  const isRoutineStream = /youtube|youtu\.be|歌枠|우타와꾸|雑談|정기.?방송|regular.?stream|livestream|ライブ配信|生配信/.test(text)
  const isSpecialLive = /생일|birthday|誕生日|生誕|기념|anniversary|周年|원맨|one.?man|ワンマン|concert|フェス|fes|3d.?live|특별.?라이브/.test(text)
  return !isRoutineStream || isSpecialLive
}
</script>

<template>
  <div class="page artist-profile-page">
    <UButton class="back-link" @click="router.push({ name: 'artist-profiles' })">← 아티스트 목록</UButton>
    <div v-if="artistsQuery.isPending.value" class="profile-hero profile-hero--loading" />
    <section v-else-if="artist" class="profile-hero">
      <span class="profile-hero__image"><b>{{ (artist.display_name || artist.name).slice(0, 1) }}</b><img v-if="image(artist)" :src="image(artist)" :alt="artist.display_name || artist.name" @error="hideBrokenImage" /></span>
      <div><p class="eyebrow">{{ artist.agency || 'VSINGER' }}</p><h1>{{ artist.display_name || artist.name }}</h1><p>{{ artist.profile_intro || artist.notes || '소개가 아직 등록되지 않았습니다.' }}</p><dl><div><dt>DEBUT</dt><dd>{{ artist.debut_date || '등록 예정' }}</dd></div><div><dt>TYPE</dt><dd>{{ artist.artist_kind === 'vtuber' ? 'VSINGER / VTUBER' : 'SINGER' }}</dd></div></dl></div>
    </section>
    <div v-else class="empty-state"><strong>아티스트를 찾을 수 없습니다.</strong></div>

    <section v-if="artist" class="history-section"><div class="section-heading"><div><p class="eyebrow">CAREER TIMELINE</p><h2>{{ artist.display_name || artist.name }}의 연혁</h2></div><span class="count-label">{{ events.length }} LIVE RECORDS</span></div>
      <div v-if="eventsQuery.isPending.value" class="history-line"><i /><i /><i /></div>
      <div v-else class="history-line">
        <article v-if="artist.debut_date" class="history-entry history-entry--debut"><time>{{ year(artist.debut_date) }}</time><div class="history-entry__dot" /><div class="history-entry__card"><span>DEBUT</span><h3>아티스트 활동 시작</h3><p>{{ artist.debut_date }}</p></div></article>
        <article v-for="event in events" :key="event.id" class="history-entry" :class="{ 'history-entry--clickable': isDetailed(event) }" @click="router.push({ name: 'artist-live-detail', params: { artistId: artist.id, eventId: event.id } })"><time>{{ year(event.starts_at) }}</time><div class="history-entry__dot" /><div class="history-entry__card"><span>{{ date(event.starts_at) }}</span><h3>{{ event.title }}</h3><p>{{ event.venue || '공연 장소 정보 등록 예정' }}</p><small v-if="isDetailed(event)">공연 상세 보기 →</small></div></article>
        <div v-if="!artist.debut_date && !events.length" class="empty-state compact"><strong>연혁이 아직 등록되지 않았습니다.</strong><p>데뷔일과 공연 일정을 등록하면 시간순으로 이어집니다.</p></div>
      </div>
    </section>
  </div>
</template>
