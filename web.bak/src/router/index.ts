import { createRouter, createWebHistory } from 'vue-router'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'dashboard', component: () => import('@/pages/DashboardPage.vue') },
    { path: '/artists', name: 'artists', component: () => import('@/pages/ArtistsPage.vue') },
    { path: '/profiles', name: 'artist-profiles', component: () => import('@/pages/ArtistProfilesPage.vue') },
    { path: '/profiles/:artistId', name: 'artist-profile', component: () => import('@/pages/ArtistProfilePage.vue') },
    { path: '/profiles/:artistId/lives/:eventId', name: 'artist-live-detail', component: () => import('@/pages/ArtistLiveDetailPage.vue') },
    { path: '/events', name: 'events', component: () => import('@/pages/EventsPage.vue') },
    { path: '/music', name: 'music', component: () => import('@/pages/MusicLibraryPage.vue') },
    { path: '/music/artists/:artistId', name: 'music-artist', component: () => import('@/pages/ArtistDiscographyPage.vue') },
    { path: '/youtube-lives', name: 'youtube-lives', component: () => import('@/pages/YouTubeLivesPage.vue') },
    { path: '/youtube-covers', name: 'youtube-covers', component: () => import('@/pages/YouTubeCoversPage.vue') },
    { path: '/youtube-covers/artists/:artistId', name: 'youtube-cover-artist', component: () => import('@/pages/YouTubeCoversPage.vue') },
    { path: '/youtube-lives/artists/:artistId', name: 'youtube-live-artist', component: () => import('@/pages/YouTubeLivesPage.vue') },
    { path: '/lyrics', name: 'lyrics', component: () => import('@/pages/LyricsRegistrationPage.vue') },
    { path: '/lyrics/songs/:songId', name: 'lyrics-song', component: () => import('@/pages/SongLyricsPage.vue') },
    { path: '/settings', name: 'settings', component: () => import('@/pages/SettingsPage.vue') },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
  scrollBehavior: () => ({ top: 0 }),
})
