<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useMediaQuery } from '@vueuse/core'
import { AudioLines, House, Compass, CalendarDays, Settings2, Heart } from '@lucide/vue'
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
} from '@/components/ui/sidebar'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { favoriteIds, statusMessage } from '@/composables/preferences'
import { formatDate, todayKey } from '@/lib/dates'
import ContentOverlay from '@/components/ContentOverlay.vue'
const route = useRoute()
const wide = useMediaQuery('(min-width: 1024px)')
const mobile = useMediaQuery('(max-width: 768px)')
const nav = [
  { title: '홈', href: '/', icon: House },
  { title: '탐색', href: '/explore', icon: Compass },
  { title: '캘린더', href: '/calendar', icon: CalendarDays },
  { title: '설정', href: '/settings', icon: Settings2 },
]
const active = computed(() =>
  route.path === '/'
    ? '/'
    : ['/calendar', '/settings'].includes(route.path)
      ? route.path
      : '/explore',
)
</script>
<template>
  <a href="#main-content" class="skip-link">본문으로 이동</a>
  <SidebarProvider :open="wide" style="--sidebar-width: 232px; --sidebar-width-icon: 80px">
    <Sidebar v-if="!mobile" collapsible="icon">
      <SidebarHeader class="px-5 pt-8 pb-10">
        <RouterLink to="/" class="brand" aria-label="schedule_music 홈">
          <span class="brand-symbol"><AudioLines class="size-6" /></span>
          <span v-if="wide">
            schedule
            <span class="font-normal text-muted-foreground">_music</span>
          </span>
        </RouterLink>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup class="px-4">
          <SidebarGroupLabel v-if="wide">MY MUSIC SPACE</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu class="gap-2" aria-label="주 메뉴">
              <SidebarMenuItem v-for="item in nav" :key="item.href">
                <SidebarMenuButton
                  as-child
                  :is-active="active === item.href"
                  :tooltip="item.title"
                  class="h-12 px-4"
                >
                  <RouterLink
                    :to="item.href"
                    :aria-current="active === item.href ? 'page' : undefined"
                  >
                    <component :is="item.icon" />
                    <span>{{ item.title }}</span>
                  </RouterLink>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
        <div v-if="wide" class="sidebar-note">
          <AudioLines class="size-5" />
          <p>
            좋아하는 목소리를,
            <br />
            조금 더 가까이.
          </p>
        </div>
      </SidebarContent>
      <SidebarFooter class="p-5 pb-7">
        <Separator />
        <div class="flex items-center gap-3 pt-4">
          <span class="profile-initial">M</span>
          <div v-if="wide">
            <p class="text-sm font-medium">나의 음악 서재</p>
            <p class="mt-1 text-xs text-muted-foreground">
              즐겨찾는 아티스트 {{ favoriteIds.length }}명
            </p>
          </div>
        </div>
      </SidebarFooter>
    </Sidebar>
    <SidebarInset class="min-w-0">
      <header class="topbar">
        <RouterLink v-if="mobile" to="/" class="brand">
          <AudioLines class="size-6" />
          <span>schedule_music</span>
        </RouterLink>
        <span v-else class="topbar-location">YOUR DAILY SOUNDTRACK</span>
        <span class="today-label">
          {{
            formatDate(todayKey(), {
              year: undefined,
              month: 'long',
              day: 'numeric',
              weekday: 'long',
            })
          }}
        </span>
      </header>
      <main id="main-content" tabindex="-1"><RouterView /></main>
      <footer class="site-footer">
        <span>좋아하는 음악으로 채우는 하루.</span>
        <span>
          schedule_music
          <span class="footer-dot">·</span>
          디자인 프리뷰
        </span>
      </footer>
    </SidebarInset>
    <nav v-if="mobile" class="mobile-dock" aria-label="주 메뉴">
      <Button
        v-for="item in nav"
        :key="item.href"
        as-child
        :variant="active === item.href ? 'default' : 'ghost'"
        class="dock-item"
      >
        <RouterLink :to="item.href" :aria-current="active === item.href ? 'page' : undefined">
          <component :is="item.icon" />
          <span>{{ item.title }}</span>
        </RouterLink>
      </Button>
    </nav>
    <div class="sr-only" :data-visible="!!statusMessage" role="status" aria-live="polite">
      <Heart class="size-4" />
      <span>{{ statusMessage }}</span>
    </div>
    <ContentOverlay />
  </SidebarProvider>
</template>
