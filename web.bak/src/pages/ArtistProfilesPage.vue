<script setup lang="ts">
import { computed, ref } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import { useRouter } from 'vue-router'
import { api } from '@/api/client'
import type { Artist } from '@/api/types'
import PageHeader from '@/components/PageHeader.vue'

type AgencyTab = 'all' | 'rk' | 'kamitsubaki' | 'riot'
const router = useRouter()
const activeTab = ref<AgencyTab>('all')
const artistsQuery = useQuery({ queryKey: ['artists'], queryFn: api.artists.list })

function agencyGroup(artist: Artist): Exclude<AgencyTab, 'all'> | 'other' {
  const agency = (artist.agency || '').toLowerCase()
  if (agency.includes('rk music')) return 'rk'
  if (agency.includes('kamitsubaki')) return 'kamitsubaki'
  if (agency.includes('riot music')) return 'riot'
  return 'other'
}
const artists = computed(() => (artistsQuery.data.value || []).filter((artist) =>
  activeTab.value === 'all' ? true : agencyGroup(artist) === activeTab.value,
))
function artistImage(artist: Artist): string | undefined {
  if (artist.spotify_image_url) return artist.spotify_image_url
  const source = artist.sources.find((item) => item.source_type === 'x')
  if (!source) return undefined
  const username = source.value.includes('/') ? source.value.split('/').filter(Boolean).pop() : source.value.replace(/^@/, '')
  return username ? `https://unavatar.io/x/${encodeURIComponent(username)}` : undefined
}
function hideBrokenImage(event: Event): void { (event.currentTarget as HTMLImageElement).style.display = 'none' }
</script>

<template>
  <div class="page profile-catalog">
    <PageHeader eyebrow="VSINGER ARCHIVE / 07" title="Vsinger 아티스트 소개" description="아티스트의 기본 소개와 활동 연혁, 공연 기록을 한 곳에서 봅니다." />
    <div class="profile-tabs" role="tablist" aria-label="소속별 아티스트">
      <UButton :class="{ active: activeTab === 'all' }" @click="activeTab = 'all'">전체</UButton>
      <UButton :class="{ active: activeTab === 'rk' }" @click="activeTab = 'rk'">RK Music</UButton>
      <UButton :class="{ active: activeTab === 'kamitsubaki' }" @click="activeTab = 'kamitsubaki'">KAMITSUBAKI</UButton>
      <UButton :class="{ active: activeTab === 'riot' }" @click="activeTab = 'riot'">RIOT MUSIC</UButton>
    </div>

    <section v-if="artistsQuery.isPending.value" class="profile-card-grid"><i v-for="n in 8" :key="n" class="profile-card profile-card--loading" /></section>
    <section v-else-if="artists.length" class="profile-card-grid">
      <button v-for="artist in artists" :key="artist.id" class="profile-card" @click="router.push({ name: 'artist-profile', params: { artistId: artist.id } })">
        <span class="profile-card__image"><b>{{ (artist.display_name || artist.name).slice(0, 1) }}</b><img v-if="artistImage(artist)" :src="artistImage(artist)" :alt="artist.display_name || artist.name" @error="hideBrokenImage" /></span>
        <span class="profile-card__meta">{{ artist.agency || 'INDEPENDENT' }}</span>
        <strong>{{ artist.display_name || artist.name }}</strong>
        <small>{{ artist.debut_date ? `DEBUT · ${artist.debut_date}` : 'ARTIST PROFILE' }}</small>
      </button>
    </section>
    <div v-else class="empty-state"><span>✦</span><strong>표시할 아티스트가 없습니다</strong><p>해당 소속의 아티스트를 등록하면 소개 카드가 여기에 나타납니다.</p></div>
  </div>
</template>
