<script setup lang="ts">
import { computed } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import { useRoute, useRouter } from 'vue-router'
import { api } from '@/api/client'

const route = useRoute(); const router = useRouter()
const artistId = computed(() => Number(route.params.artistId)); const eventId = computed(() => Number(route.params.eventId))
const eventsQuery = useQuery({ queryKey: ['events', 'live-detail', artistId], queryFn: () => api.events.list(undefined, artistId.value, 'live_event') })
const event = computed(() => eventsQuery.data.value?.find((item) => item.id === eventId.value))
function array(value: string | null): string[] { try { const parsed: unknown = JSON.parse(value || '[]'); return Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === 'string') : [] } catch { return value ? value.split('\n').filter(Boolean) : [] } }
function date(value: string | null): string { if (!value) return '날짜 미정'; const parsed = new Date(value); return Number.isNaN(parsed.getTime()) ? value : new Intl.DateTimeFormat('ko-KR', { dateStyle: 'full', timeStyle: 'short' }).format(parsed) }
</script>

<template>
  <div class="page live-detail-page"><UButton class="back-link" @click="router.push({ name: 'artist-profile', params: { artistId } })">← 연혁으로 돌아가기</UButton>
    <div v-if="eventsQuery.isPending.value" class="panel skeleton-list"><i /><i /><i /></div>
    <template v-else-if="event"><section class="live-detail-hero"><p class="eyebrow">LIVE EVENT DETAIL</p><h1>{{ event.title }}</h1><p>{{ date(event.starts_at) }}</p><a v-if="event.source_url || event.ticket_url" :href="event.ticket_url || event.source_url || '#'" target="_blank" rel="noreferrer">공식 안내 열기 ↗</a></section>
      <section class="live-facts"><article><span>PLACE</span><strong>{{ event.venue || '등록 예정' }}</strong></article><article><span>CAPACITY</span><strong>{{ event.capacity_text || '등록 예정' }}</strong></article><article><span>TICKET</span><strong>{{ event.price_text || '등록 예정' }}</strong></article></section>
      <section class="detail-block"><div><p class="eyebrow">SETLIST</p><h2>공연 셋리스트</h2></div><ol v-if="array(event.setlist_json).length" class="setlist"><li v-for="(song, index) in array(event.setlist_json)" :key="song"><b>{{ String(index + 1).padStart(2, '0') }}</b><span>{{ song }}</span></li></ol><div v-else class="empty-state compact"><strong>셋리스트가 아직 등록되지 않았습니다.</strong></div></section>
      <section class="detail-block"><div><p class="eyebrow">EVENT MERCH</p><h2>현장 판매 굿즈</h2></div><ul v-if="array(event.merchandise_json).length" class="merch-list"><li v-for="item in array(event.merchandise_json)" :key="item">{{ item }}</li></ul><div v-else class="empty-state compact"><strong>굿즈 정보가 아직 등록되지 않았습니다.</strong></div></section>
    </template><div v-else class="empty-state"><strong>공연 정보를 찾을 수 없습니다.</strong></div>
  </div>
</template>
