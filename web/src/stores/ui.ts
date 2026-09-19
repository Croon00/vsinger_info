import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useUiStore = defineStore('ui', () => {
  const sidebarOpen = ref(false)

  const desktopSidebarCollapsed = ref(false)

  function setSidebarOpen(open: boolean): void {
    sidebarOpen.value = open
  }

  function toggleDesktopSidebar(): void {
    desktopSidebarCollapsed.value = !desktopSidebarCollapsed.value
  }

  function toggleSidebar(): void {
    sidebarOpen.value = !sidebarOpen.value
  }

  function closeSidebar(): void {
    sidebarOpen.value = false
  }

  return { sidebarOpen, desktopSidebarCollapsed, setSidebarOpen, toggleDesktopSidebar, toggleSidebar, closeSidebar }
})
