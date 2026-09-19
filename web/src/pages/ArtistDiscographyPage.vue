<script setup lang="ts">
import { computed, ref } from 'vue'
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { useRoute, useRouter } from 'vue-router'
import { api } from '@/api/client'
import type { SongLyricsSummary, SpotifyAlbum, SpotifyTrack } from '@/api/types'
import AppModal from '@/components/AppModal.vue'
import PageHeader from '@/components/PageHeader.vue'
import StatusPill from '@/components/StatusPill.vue'

const route = useRoute()
const router = useRouter()
const queryClient = useQueryClient()
const artistId = computed(() => Number(route.params.artistId))
const selectedAlbumId = ref<string | null>(null)
const selectedYouTubeTrack = ref<SpotifyTrack | null>(null)
const youtubeUrl = ref('')
const selectedCredits = ref<SongLyricsSummary | null>(null)
const creditsForm = ref({ lyricist: '', composer: '', arranger: '' })
const releaseFilter = ref<'all' | 'album' | 'single' | 'appears_on'>('all')

const artistsQuery = useQuery({ queryKey: ['spotify-artists'], queryFn: api.spotify.artists })
const artist = computed(() =>
  (artistsQuery.data.value ?? []).find((item) => item.local_artist_id === artistId.value || item.related_artist_ids?.includes(artistId.value)),
)
const discographyQuery = useQuery({
  queryKey: ['spotify-discography', artistId],
  queryFn: () => api.spotify.discography(artist.value!.local_artist_id),
  enabled: computed(() => Boolean(artist.value?.matched)),
})
const artistProfileQuery = useQuery({
  queryKey: ['spotify-artist-profile', artistId],
  queryFn: () => api.spotify.artistProfile(artist.value!.local_artist_id),
  enabled: computed(() => Boolean(artist.value?.matched)),
  staleTime: 60 * 60_000,
})
const albumQuery = useQuery({
  queryKey: ['spotify-album', selectedAlbumId],
  queryFn: () => api.spotify.album(selectedAlbumId.value as string),
  enabled: computed(() => selectedAlbumId.value !== null),
})
const trackLyricsQuery = useQuery({
  queryKey: ['spotify-track-lyrics', selectedAlbumId],
  queryFn: () => api.songs.lyricsForSpotifyTracks(albumQuery.data.value?.tracks.map((track) => track.id) ?? []),
  enabled: computed(() => Boolean(albumQuery.data.value?.tracks.length)),
  staleTime: 60 * 60_000,
})
const lyricsByTrack = computed(() =>
  new Map((trackLyricsQuery.data.value ?? []).map((lyrics) => [lyrics.spotify_track_id, lyrics])),
)
const filteredAlbums = computed(() => {
  const albums = discographyQuery.data.value ?? []
  if (releaseFilter.value === 'all') return albums
  if (releaseFilter.value === 'appears_on') {
    return albums.filter((album) => artist.value?.spotify_artist_id && !album.artist_ids.includes(artist.value.spotify_artist_id))
  }
  return albums.filter((album) => album.album_type === releaseFilter.value)
})
const excludeArtist = useMutation({
  mutationFn: api.spotify.excludeArtist,
  onSuccess: async () => {
    await queryClient.invalidateQueries({ queryKey: ['spotify-artists'] })
    router.push('/music')
  },
})
const autoLinkYouTube = useMutation({
  mutationFn: api.spotify.autoLinkYouTube,
  onSuccess: async () => {
    await queryClient.invalidateQueries({ queryKey: ['spotify-track-lyrics'] })
  },
})
const linkYouTube = useMutation({
  mutationFn: api.songs.linkSpotifyTrackYouTube,
  onSuccess: async () => {
    selectedYouTubeTrack.value = null
    youtubeUrl.value = ''
    await queryClient.invalidateQueries({ queryKey: ['spotify-track-lyrics', selectedAlbumId] })
  },
})
const saveCredits = useMutation({
  mutationFn: ({ songId, payload }: { songId: number; payload: { lyricist: string | null; composer: string | null; arranger: string | null } }) =>
    api.songs.updateCredits(songId, payload),
  onSuccess: async () => {
    selectedCredits.value = null
    await queryClient.invalidateQueries({ queryKey: ['spotify-track-lyrics', selectedAlbumId] })
  },
})

function albumKind(album: SpotifyAlbum): string {
  if (album.album_type === 'single') return album.total_tracks > 1 ? 'EP / SINGLE' : 'SINGLE'
  if (album.album_type === 'compilation') return 'COMPILATION'
  return 'ALBUM'
}

function duration(milliseconds: number | null): string {
  if (!milliseconds) return '—'
  const minutes = Math.floor(milliseconds / 60_000)
  const seconds = Math.floor((milliseconds % 60_000) / 1000)
  return `${minutes}:${seconds.toString().padStart(2, '0')}`
}

function confirmExclusion(): void {
  if (!artist.value) return
  if (window.confirm(`${artist.value.local_name}의 Spotify 연결을 제거할까요? X 계정은 유지됩니다.`)) {
    excludeArtist.mutate(artist.value.local_artist_id)
  }
}

function openYouTubeLink(track: SpotifyTrack): void {
  selectedYouTubeTrack.value = track
  youtubeUrl.value = ''
}

function saveYouTubeLink(): void {
  if (!selectedYouTubeTrack.value || !artist.value) return
  linkYouTube.mutate({
    spotify_track_id: selectedYouTubeTrack.value.id,
    title: selectedYouTubeTrack.value.name,
    artist_name: artist.value.local_name,
    album_name: albumQuery.data.value?.name,
    youtube_url: youtubeUrl.value,
  })
}

function openCredits(trackId: string): void {
  const song = lyricsByTrack.value.get(trackId)
  if (!song) return
  selectedCredits.value = song
  creditsForm.value = {
    lyricist: song.lyricist || '',
    composer: song.composer || '',
    arranger: song.arranger || '',
  }
}

function submitCredits(): void {
  if (!selectedCredits.value) return
  saveCredits.mutate({
    songId: selectedCredits.value.song_id,
    payload: {
      lyricist: creditsForm.value.lyricist.trim() || null,
      composer: creditsForm.value.composer.trim() || null,
      arranger: creditsForm.value.arranger.trim() || null,
    },
  })
}

function runYouTubeAutoLink(): void {
  if (!artist.value) return
  autoLinkYouTube.mutate(artist.value.local_artist_id)
}
</script>

<template>
  <div class="page music-page artist-detail-page">
    <PageHeader eyebrow="ARTIST CATALOG" title="아티스트 디스코그래피" description="아티스트 프로필과 Spotify 공식 발매작을 확인합니다.">
      <RouterLink to="/music" class="button button--ghost">← 아티스트 목록</RouterLink>
    </PageHeader>

    <div v-if="artistsQuery.isPending.value" class="skeleton-list"><i /><i /><i /></div>
    <div v-else-if="!artist" class="empty-state"><strong>아티스트를 찾을 수 없습니다</strong><RouterLink to="/music">목록으로 돌아가기</RouterLink></div>
    <template v-else>
      <section class="artist-profile-hero">
        <img v-if="artist.image_url" :src="artist.image_url" :alt="artist.local_name" />
        <div v-else class="artist-profile-hero__fallback">{{ artist.local_name.slice(0, 1) }}</div>
        <div class="artist-profile-hero__info">
          <p class="eyebrow">{{ artist.agency || (artist.artist_kind === 'vtuber' ? 'VTUBER' : 'SINGER') }}</p>
          <h1>{{ artist.local_name }}</h1>
          <span>{{ artist.artist_kind === 'vtuber' ? 'Virtual Artist' : 'Music Artist' }}</span>
          <a v-if="artist.spotify_url" :href="artist.spotify_url" target="_blank" rel="noreferrer" class="spotify-attribution">Spotify에서 확인 ↗</a>
          <div v-if="artistProfileQuery.data.value?.genres.length" class="artist-genre-list" aria-label="Spotify 장르 태그">
            <div v-for="genre in artistProfileQuery.data.value.genres" :key="genre" class="artist-genre">
              <strong>{{ genre }}</strong>
            </div>
          </div>
          <p v-else-if="artistProfileQuery.isSuccess.value" class="artist-genre-empty">Spotify에 등록된 장르 태그가 없습니다.</p>
          <p v-if="autoLinkYouTube.data.value" class="youtube-auto-link-result">{{ autoLinkYouTube.data.value.youtube_auto_link_enabled === false ? 'YouTube 자동 연결에는 YOUTUBE_API_KEY 설정이 필요합니다.' : `YouTube 자동 연결: ${autoLinkYouTube.data.value.youtube_auto_linked || 0}개 연결 · ${autoLinkYouTube.data.value.youtube_auto_unmatched || 0}개는 확인 필요` }}</p>
        </div>
        <div class="artist-profile-hero__actions">
          <UButton class="button button--ghost" :disabled="autoLinkYouTube.isPending.value" @click="runYouTubeAutoLink">{{ autoLinkYouTube.isPending.value ? 'YouTube 자동 연결 중…' : 'YouTube 자동 연결' }}</UButton>
          <UButton class="button button--danger" :disabled="excludeArtist.isPending.value" @click="confirmExclusion">Spotify 연결 제거</UButton>
        </div>
      </section>

      <section class="catalog-toolbar">
        <div class="filter-tabs">
          <UButton :class="{ active: releaseFilter === 'all' }" @click="releaseFilter = 'all'">전체</UButton>
          <UButton :class="{ active: releaseFilter === 'album' }" @click="releaseFilter = 'album'">앨범</UButton>
          <UButton :class="{ active: releaseFilter === 'single' }" @click="releaseFilter = 'single'">싱글 · EP</UButton>
          <UButton :class="{ active: releaseFilter === 'appears_on' }" @click="releaseFilter = 'appears_on'">참여작</UButton>
        </div>
        <span class="count-label">{{ filteredAlbums.length }} RELEASES</span>
      </section>

      <div v-if="discographyQuery.isPending.value" class="release-grid"><div v-for="n in 8" :key="n" class="release-card release-card--loading" /></div>
      <div v-else-if="discographyQuery.isError.value" class="alert alert--error">{{ discographyQuery.error.value?.message || '디스코그래피 조회에 실패했습니다.' }}</div>
      <div v-else-if="filteredAlbums.length" class="release-grid">
        <UButton v-for="album in filteredAlbums" :key="album.id" class="release-card" @click="selectedAlbumId = album.id">
          <div class="release-card__cover"><img v-if="album.image_url" :src="album.image_url" :alt="album.name" /><span v-else>♫</span><StatusPill :label="albumKind(album)" tone="green" /></div>
          <div class="release-card__body"><time>{{ album.release_date || '발매일 미상' }}</time><strong>{{ album.name }}</strong><p>{{ album.artists.join(', ') }}</p><span>{{ album.total_tracks }}곡</span></div>
        </UButton>
      </div>
      <div v-else class="empty-state"><strong>표시할 발매작이 없습니다</strong></div>
    </template>

    <AppModal :open="Boolean(selectedAlbumId)" :title="albumQuery.data.value?.name || '앨범 불러오는 중'" :description="albumQuery.data.value ? `${albumQuery.data.value.artists.join(', ')} · ${albumQuery.data.value.release_date || ''}` : 'Spotify에서 수록곡을 가져오고 있습니다.'" @close="selectedAlbumId = null">
      <div v-if="albumQuery.isPending.value" class="skeleton-list"><i /><i /><i /></div>
      <div v-else-if="albumQuery.data.value" class="album-detail">
        <div class="album-detail__hero"><img v-if="albumQuery.data.value.image_url" :src="albumQuery.data.value.image_url" :alt="albumQuery.data.value.name" /><strong>{{ albumQuery.data.value.total_tracks }}곡</strong></div>
        <ol class="track-list">
          <li v-for="track in albumQuery.data.value.tracks" :key="track.id">
            <span>{{ track.track_number.toString().padStart(2, '0') }}</span>
            <div><strong>{{ track.name }} <small v-if="track.name_ko">({{ track.name_ko }})</small></strong><em>{{ track.artists.join(', ') }}</em></div>
            <b v-if="track.explicit">E</b>
            <time>{{ duration(track.duration_ms) }}</time>
            <div class="track-list__actions">
              <a v-if="track.spotify_url" :href="track.spotify_url" target="_blank" rel="noreferrer" aria-label="Spotify에서 열기">↗</a>
              <a v-if="lyricsByTrack.get(track.id)" :href="lyricsByTrack.get(track.id)?.youtube_url" target="_blank" rel="noreferrer" class="track-list__youtube" aria-label="YouTube에서 열기">↗</a>
              <UButton v-else class="track-list__youtube-add" @click="openYouTubeLink(track)">YouTube</UButton>
              <RouterLink v-if="lyricsByTrack.get(track.id)?.has_lyrics" :to="`/lyrics/songs/${lyricsByTrack.get(track.id)?.song_id}`" class="track-list__lyrics">가사</RouterLink>
              <UButton v-if="lyricsByTrack.get(track.id)" class="track-list__credits" @click="openCredits(track.id)">크레딧</UButton>
            </div>
          </li>
        </ol>
      </div>
    </AppModal>

    <AppModal :open="Boolean(selectedYouTubeTrack)" title="YouTube 영상 연결" :description="selectedYouTubeTrack ? `${selectedYouTubeTrack.name}의 공식 영상 URL을 입력하세요.` : ''" @close="selectedYouTubeTrack = null">
      <form class="youtube-link-form" @submit.prevent="saveYouTubeLink">
        <label>YouTube 영상 URL<UInput v-model="youtubeUrl" type="url" required placeholder="https://www.youtube.com/watch?v=..." /></label>
        <p v-if="linkYouTube.error.value" class="form-error">{{ linkYouTube.error.value.message }}</p>
        <div class="form-actions"><UButton class="button button--primary" :disabled="linkYouTube.isPending.value">{{ linkYouTube.isPending.value ? '연결 중…' : 'YouTube 연결' }}</UButton></div>
      </form>
    </AppModal>

    <AppModal :open="Boolean(selectedCredits)" title="곡 크레딧" :description="selectedCredits ? 'YouTube 설명란에서 가져온 값입니다. 없는 항목은 직접 입력할 수 있습니다.' : ''" @close="selectedCredits = null">
      <form class="credits-form" @submit.prevent="submitCredits">
        <label>작사<UInput v-model="creditsForm.lyricist" placeholder="정보 없음" /></label>
        <label>작곡<UInput v-model="creditsForm.composer" placeholder="정보 없음" /></label>
        <label>편곡<UInput v-model="creditsForm.arranger" placeholder="정보 없음" /></label>
        <p v-if="saveCredits.error.value" class="form-error">{{ saveCredits.error.value.message }}</p>
        <div class="form-actions"><UButton class="button button--primary" :disabled="saveCredits.isPending.value">{{ saveCredits.isPending.value ? '저장 중…' : '크레딧 저장' }}</UButton></div>
      </form>
    </AppModal>
  </div>
</template>
