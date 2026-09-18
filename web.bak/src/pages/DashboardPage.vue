<script setup lang="ts">
import { computed } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import { api } from '@/api/client'
import PageHeader from '@/components/PageHeader.vue'
import StatusPill from '@/components/StatusPill.vue'

const artistsQuery = useQuery({ queryKey: ['artists'], queryFn: api.artists.list })
const eventsQuery = useQuery({ queryKey: ['events'], queryFn: () => api.events.list() })

const artists = computed(() => artistsQuery.data.value ?? [])
const events = computed(() => eventsQuery.data.value ?? [])
const sourceCount = computed(() => artists.value.reduce((sum, artist) => sum + artist.sources.length, 0))
const reviewCount = computed(() => events.value.filter((event) => event.status === 'needs_review').length)
const upcoming = computed(() =>
  events.value
    .filter((event) => event.starts_at)
    .sort((a, b) => String(a.starts_at).localeCompare(String(b.starts_at)))
    .slice(0, 4),
)

function formatDate(value: string | null): string {
  if (!value) return '일정 미정'
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat('ko-KR', {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      }).format(date)
}
</script>

<template>
  <div class="page">
    <PageHeader
      eyebrow="MUSIC NOTES / 01"
      title="오늘의 운영 상황"
      description="아티스트 소식에서 일정 후보까지, 놓치면 안 되는 신호만 한곳에 모았습니다."
    >
      <RouterLink to="/artists" class="button button--primary">+ 아티스트 등록</RouterLink>
    </PageHeader>

    <div v-if="artistsQuery.isError.value || eventsQuery.isError.value" class="alert alert--error">
      FastAPI에서 데이터를 불러오지 못했습니다. API 서버 실행 여부와 주소를 확인해 주세요.
    </div>

    <section class="metric-grid" aria-label="운영 요약">
      <article class="metric-card metric-card--hero">
        <div>
          <span>수집 중인 아티스트</span>
          <strong>{{ artistsQuery.isPending.value ? '—' : artists.length }}</strong>
        </div>
        <p>{{ sourceCount }}개의 공식 소식을 살피는 중</p>
        <div class="signal-bars"><i /><i /><i /><i /><i /></div>
      </article>
      <article class="metric-card">
        <span>일정 후보</span>
        <strong>{{ eventsQuery.isPending.value ? '—' : events.length }}</strong>
        <StatusPill :label="`${reviewCount}건 검토 필요`" tone="amber" />
      </article>
      <article class="metric-card">
        <span>활성 수집 소스</span>
        <strong>{{ sourceCount }}</strong>
        <StatusPill label="중복 차단 적용" tone="green" />
      </article>
      <article class="metric-card">
        <span>자동 구매</span>
        <strong class="metric-card__text">사용 안 함</strong>
        <StatusPill label="사람 승인 원칙" tone="violet" />
      </article>
    </section>

    <section class="dashboard-grid">
      <article class="panel">
        <div class="panel__heading">
          <div>
            <p class="eyebrow">UPCOMING</p>
            <h2>다가오는 일정</h2>
          </div>
          <RouterLink to="/events" class="text-link">전체 보기 →</RouterLink>
        </div>
        <div v-if="eventsQuery.isPending.value" class="skeleton-list"><i /><i /><i /></div>
        <div v-else-if="upcoming.length" class="timeline">
          <div v-for="event in upcoming" :key="event.id" class="timeline__item">
            <div class="timeline__date">{{ formatDate(event.starts_at) }}</div>
            <div>
              <strong>{{ event.title }}</strong>
              <span>{{ event.venue || '장소 정보 없음' }}</span>
            </div>
            <StatusPill
              :label="event.status === 'needs_review' ? '검토' : event.status"
              :tone="event.status === 'needs_review' ? 'amber' : 'cyan'"
            />
          </div>
        </div>
        <div v-else class="empty-state">
          <span>◇</span>
          <strong>아직 예정된 일정이 없습니다</strong>
          <p>새 일정 후보를 등록하거나 수집 에이전트의 결과를 기다려 주세요.</p>
        </div>
      </article>

      <article class="panel panel--accent">
        <p class="eyebrow">PIPELINE</p>
        <h2>자동화 흐름</h2>
        <div class="pipeline">
          <div><b>01</b><span>공식 소스 수집</span><em>deterministic</em></div>
          <div><b>02</b><span>새 글 분류</span><em>AI assist</em></div>
          <div><b>03</b><span>일정 정보 추출</span><em>structured</em></div>
          <div><b>04</b><span>사람 검토 · 알림</span><em>safe route</em></div>
        </div>
        <p class="panel__note">구매·응모·결제는 자동화하지 않습니다.</p>
      </article>
    </section>
  </div>
</template>
