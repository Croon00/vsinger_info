<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useMediaQuery } from '@vueuse/core'
import { AudioLines, House, Compass, CalendarDays, Settings2, Heart } from '@lucide/vue'
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
} from '@/components/ui/sidebar'
import { Button } from '@/components/ui/button'
import { statusMessage } from '@/composables/preferences'
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
const activeIndex = computed(() => nav.findIndex((item) => item.href === active.value))
</script>
<template>
  <a href="#main-content" class="skip-link">본문으로 이동</a>
  <SidebarProvider :open="wide" style="--sidebar-width: 232px; --sidebar-width-icon: 80px">
    <Sidebar v-if="!mobile" collapsible="icon">
      <SidebarHeader class="px-5 pt-8 pb-10 group-data-[collapsible=icon]:px-3">
        <RouterLink
          to="/"
          class="brand group-data-[collapsible=icon]:justify-center"
          aria-label="schedule_music 홈"
        >
          <span class="brand-symbol"><AudioLines class="size-6" /></span>
          <span v-if="wide">
            schedule
            <span class="font-normal text-muted-foreground">_music</span>
          </span>
        </RouterLink>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup class="px-4 group-data-[collapsible=icon]:px-3">
          <SidebarGroupContent>
            <SidebarMenu class="gap-2" aria-label="주 메뉴">
              <SidebarMenuItem v-for="item in nav" :key="item.href">
                <SidebarMenuButton
                  as-child
                  :is-active="active === item.href"
                  :tooltip="item.title"
                  size="lg"
                  class="sidebar-nav-item group-data-[collapsible=icon]:size-14! group-data-[collapsible=icon]:justify-center"
                >
                  <RouterLink
                    :to="item.href"
                    :aria-label="item.title"
                    :aria-current="active === item.href ? 'page' : undefined"
                  >
                    <component :is="item.icon" />
                    <span v-if="wide">{{ item.title }}</span>
                  </RouterLink>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
    </Sidebar>
    <SidebarInset class="min-w-0">
      <header v-if="mobile" class="topbar">
        <RouterLink to="/" class="brand">
          <AudioLines class="size-6" />
          <span>schedule_music</span>
        </RouterLink>
      </header>
      <main id="main-content" tabindex="-1"><RouterView /></main>
    </SidebarInset>
    <nav
      v-if="mobile"
      class="mobile-dock"
      aria-label="주 메뉴"
      :style="{ '--dock-index': activeIndex }"
    >
      <span class="dock-indicator" aria-hidden="true" />
      <Button
        v-for="item in nav"
        :key="item.href"
        as-child
        variant="ghost"
        size="icon-lg"
        class="dock-item"
      >
        <RouterLink
          :to="item.href"
          :aria-label="item.title"
          :aria-current="active === item.href ? 'page' : undefined"
        >
          <component :is="item.icon" />
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
