<script setup lang="ts">
defineProps<{ closeOnNavigate?: boolean }>()
const emit = defineEmits<{ navigate: [] }>()

const navigation = [
  { to: '/profiles', label: 'Vsinger 소개', icon: '✦' },
  { to: '/music', label: 'Spotify 음악', icon: '♫' },
  { to: '/lyrics', label: '가사 등록', icon: '文' },
  { to: '/youtube-lives', label: 'YouTube 우타와꾸', icon: 'YT' },
  { to: '/youtube-covers', label: 'YouTube 커버곡', icon: '♪' },
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
</template>
