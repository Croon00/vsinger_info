<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import AppSidebarContent from '@/components/AppSidebarContent.vue'
import { useUiStore } from '@/stores/ui'

const ui = useUiStore()
const route = useRoute()
const mobile = ref(false)
let media: MediaQueryList | undefined

function syncViewport(): void {
  mobile.value = media?.matches ?? false
  ui.closeSidebar()
}
onMounted(() => {
  media = window.matchMedia('(max-width: 1024px)')
  syncViewport()
  media.addEventListener('change', syncViewport)
})
onUnmounted(() => media?.removeEventListener('change', syncViewport))
watch(() => route.fullPath, () => ui.closeSidebar())
</script>

<template>
  <UApp>
    <div class="app-shell" :class="{ 'app-shell--collapsed': ui.desktopSidebarCollapsed }">
      <aside v-if="!mobile && !ui.desktopSidebarCollapsed" id="desktop-sidebar" class="sidebar">
        <AppSidebarContent />
      </aside>
      <main class="main-content">
        <header class="app-topbar">
          <USlideover
            v-if="mobile"
            :open="ui.sidebarOpen"
            side="left"
            title="주요 메뉴"
            description="Schedule Music 페이지 탐색"
            :close="{ 'aria-label': '메뉴 닫기' }"
            :ui="{ overlay: 'mobile-sidebar-overlay', content: 'mobile-sidebar', body: 'mobile-sidebar__body' }"
            @update:open="ui.setSidebarOpen"
          >
            <UButton class="menu-toggle" aria-label="메뉴 열기" color="neutral" variant="ghost">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h16" /></svg>
            </UButton>
            <template #body>
              <AppSidebarContent close-on-navigate @navigate="ui.closeSidebar" />
            </template>
            <template #close>
              <UButton class="mobile-sidebar__close menu-toggle" aria-label="메뉴 닫기" color="neutral" variant="ghost">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="m6 6 12 12M6 18 18 6" /></svg>
              </UButton>
            </template>
          </USlideover>
          <UButton
            v-else
            class="menu-toggle"
            :aria-label="ui.desktopSidebarCollapsed ? '사이드바 열기' : '사이드바 접기'"
            :aria-expanded="!ui.desktopSidebarCollapsed"
            aria-controls="desktop-sidebar"
            color="neutral"
            variant="ghost"
            @click="ui.toggleDesktopSidebar"
          >
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h16" /></svg>
          </UButton>
          <RouterLink to="/" class="app-topbar__brand">SCHEDULE MUSIC</RouterLink>
        </header>
        <RouterView />
      </main>
    </div>
  </UApp>
</template>
