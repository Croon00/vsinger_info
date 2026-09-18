import { createRouter, createWebHistory } from 'vue-router'
import HomePage from '@/pages/HomePage.vue'
const positions = new Map<string, number>()
const key = (path: string) => path.replace(/([?&])(event|lyrics)=\d+/g, '').replace(/[?&]$/, '')
export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: HomePage },
    { path: '/explore', component: () => import('@/pages/ExplorePage.vue') },
    { path: '/artists/:artistId', component: () => import('@/pages/ArtistPage.vue') },
    { path: '/lives/:archiveId', component: () => import('@/pages/LivePage.vue') },
    { path: '/calendar', component: () => import('@/pages/CalendarPage.vue') },
    { path: '/settings', component: () => import('@/pages/SettingsPage.vue') },
    { path: '/search', component: () => import('@/pages/SearchPage.vue') },
    { path: '/:pathMatch(.*)*', component: () => import('@/pages/NotFoundPage.vue') },
  ],
  scrollBehavior(to, from, saved) {
    if (to.path === from.path) return false
    return saved ?? { top: positions.get(key(to.fullPath)) ?? 0 }
  },
})
router.beforeEach((to, from) => {
  if (to.path !== from.path) positions.set(key(from.fullPath), window.scrollY)
})
router.afterEach((to) => {
  document.title = `${to.path === '/' ? '홈' : to.path.startsWith('/calendar') ? '캘린더' : to.path.startsWith('/settings') ? '설정' : to.path.startsWith('/search') ? '검색' : '탐색'} · schedule_music`
})
