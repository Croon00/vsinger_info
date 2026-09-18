<script setup lang="ts">
import { useQuery } from '@tanstack/vue-query'
import { api } from '@/api/client'

defineProps<{ closeOnNavigate?: boolean }>()
const emit = defineEmits<{ navigate: [] }>()

const health = useQuery({ queryKey: ['health'], queryFn: api.health, refetchInterval: 60_000 })

const navigation = [
  { to: '/', label: '대시보드', icon: '⌁' },
  { to: '/artists', label: '아티스트 · 소스', icon: '◉' },
  { to: '/profiles', label: 'Vsinger 소개', icon: '✦' },
  { to: '/events', label: '일정 후보', icon: '◇' },
  { to: '/music', label: 'Spotify 음악', icon: '♫' },
  { to: '/lyrics', label: '가사 등록', icon: '文' },
  { to: '/youtube-lives', label: 'YouTube 우타와꾸', icon: 'YT' },
  { to: '/youtube-covers', label: 'YouTube 커버곡', icon: '♪' },
  { to: '/settings', label: '연동 설정', icon: '⚙' },
]
</script>

<template>
        <div class="brand">
          <div class="brand__mark">S</div>
          <div>
            <strong>SCHEDULE MUSIC</strong>
            <span>音楽のしおり · MUSIC NOTES</span>
          </div>
        </div>

        <nav aria-label="주요 메뉴">
          <RouterLink
            v-for="item in navigation"
            :key="item.to"
            :to="item.to"
            class="nav-link"
            @click="closeOnNavigate && emit('navigate')"
          >
            <span class="nav-link__icon">{{ item.icon }}</span>
            {{ item.label }}
          </RouterLink>
        </nav>

        <div class="sidebar__bottom">
          <div class="connection-card">
            <span class="connection-card__pulse" :class="{ offline: health.isError.value }" />
            <div>
              <strong>{{ health.isError.value ? '연결을 확인해 주세요' : '조용히 수집 중' }}</strong>
              <span>{{ health.isFetching.value ? '상태를 확인하고 있어요' : '음악 소식을 살피는 중' }}</span>
            </div>
          </div>
          <p>Asia/Seoul · JST 일정 보존</p>
        </div>
</template>
