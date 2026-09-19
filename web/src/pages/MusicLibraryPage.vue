<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { api } from '@/api/client'
import type { SpotifyAlbum, SpotifyArtist, SpotifyArtistCandidate } from '@/api/types'
import AppModal from '@/components/AppModal.vue'
import PageHeader from '@/components/PageHeader.vue'
import StatusPill from '@/components/StatusPill.vue'

const queryClient = useQueryClient()
const router = useRouter()
const selectedArtistId = ref<number | null>(null)
const viewMode = ref<'grid' | 'list'>('grid')
const releaseFilter = ref<'all' | 'album' | 'single' | 'appears_on'>('all')
const selectedAlbumId = ref<string | null>(null)
const relationMode = ref(false)
const artistKind = ref<'vtuber' | 'singer' | null>(null)
const agencyFilter = ref<string>('all')
const candidateArtist = ref<SpotifyArtist | null>(null)
const candidateResults = ref<SpotifyArtistCandidate[]>([])
const agencyModal = ref(false)
const newAgencyName = ref('')

const artistsQuery = useQuery({ queryKey: ['spotify-artists'], queryFn: api.spotify.artists })
const agenciesQuery = useQuery({ queryKey: ['artist-agencies'], queryFn: api.artistAgencies.list })
const discographyQuery = useQuery({
  queryKey: ['spotify-discography', selectedArtistId],
  queryFn: () => api.spotify.discography(selectedArtistId.value as number),
  enabled: computed(() => selectedArtistId.value !== null),
})
const albumQuery = useQuery({
  queryKey: ['spotify-album', selectedAlbumId],
  queryFn: () => api.spotify.album(selectedAlbumId.value as string),
  enabled: computed(() => selectedAlbumId.value !== null),
})
const relationshipsQuery = useQuery({
  queryKey: ['spotify-relationships'],
  queryFn: api.spotify.relationships,
  enabled: relationMode,
  staleTime: 10 * 60_000,
})
const syncArtist = useMutation({
  mutationFn: ({ artistId, spotifyArtistId }: { artistId: number; spotifyArtistId: string }) =>
    api.spotify.syncArtist(artistId, spotifyArtistId),
  onSuccess: async (artist) => {
    candidateArtist.value = null
    candidateResults.value = []
    await queryClient.invalidateQueries({ queryKey: ['spotify-artists'] })
    selectArtist(artist)
  },
})
const searchCandidates = useMutation({
  mutationFn: api.spotify.artistCandidates,
  onSuccess: (candidates) => {
    candidateResults.value = candidates
  },
})
const createAgency = useMutation({
  mutationFn: api.artistAgencies.create,
  onSuccess: async (agency) => {
    await queryClient.invalidateQueries({ queryKey: ['artist-agencies'] })
    agencyFilter.value = agency.name
    newAgencyName.value = ''
    agencyModal.value = false
  },
})
const excludeArtist = useMutation({
  mutationFn: api.spotify.excludeArtist,
  onSuccess: async () => {
    selectedArtistId.value = null
    selectedAlbumId.value = null
    await queryClient.invalidateQueries({ queryKey: ['spotify-artists'] })
    await queryClient.invalidateQueries({ queryKey: ['spotify-relationships'] })
  },
})

const allArtists = computed(() => artistsQuery.data.value ?? [])
const artists = computed(() =>
  artistKind.value
    ? allArtists.value.filter((artist) =>
        artist.artist_kind === artistKind.value
        && (artistKind.value !== 'vtuber' || agencyFilter.value === 'all' || artist.agency === agencyFilter.value),
      )
    : [],
)
const selectedArtist = computed(() =>
  artists.value.find((artist) => artist.local_artist_id === selectedArtistId.value),
)
const filteredAlbums = computed(() => {
  const albums = discographyQuery.data.value ?? []
  if (releaseFilter.value === 'all') return albums
  if (releaseFilter.value === 'appears_on') {
    const ownId = selectedArtist.value?.spotify_artist_id
    return albums.filter((album) => ownId && !album.artist_ids.includes(ownId))
  }
  return albums.filter((album) => album.album_type === releaseFilter.value)
})
const albumCount = computed(() =>
  (discographyQuery.data.value ?? []).filter((album) => album.album_type === 'album').length,
)
const singleCount = computed(() =>
  (discographyQuery.data.value ?? []).filter((album) => album.album_type === 'single').length,
)
const artistById = computed(() =>
  new Map(artists.value.map((artist) => [artist.local_artist_id, artist])),
)

function selectArtist(artist: SpotifyArtist): void {
  if (!artist.matched) {
    syncSelectedArtist(artist)
    return
  }
  relationMode.value = false
  router.push(`/music/artists/${artist.local_artist_id}`)
}

function syncSelectedArtist(artist: SpotifyArtist): void {
  candidateArtist.value = artist
  candidateResults.value = []
  searchCandidates.mutate(artist.local_artist_id)
}

function confirmCandidate(candidate: SpotifyArtistCandidate): void {
  if (!candidateArtist.value) return
  syncArtist.mutate({
    artistId: candidateArtist.value.local_artist_id,
    spotifyArtistId: candidate.spotify_artist_id,
  })
}

function submitAgency(): void {
  const name = newAgencyName.value.trim()
  if (name) createAgency.mutate(name)
}

function selectArtistKind(kind: 'vtuber' | 'singer'): void {
  artistKind.value = kind
  agencyFilter.value = 'all'
  selectedArtistId.value = null
  selectedAlbumId.value = null
  relationMode.value = false
}

function confirmSpotifyExclusion(artist: SpotifyArtist): void {
  const name = artist.local_name
  if (window.confirm(`${name}을 Spotify 목록과 이후 동기화 대상에서 제외할까요? X 계정은 유지됩니다.`)) {
    excludeArtist.mutate(artist.local_artist_id)
  }
}

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
</script>

<template>
  <div class="page music-page">
    <PageHeader
      eyebrow="SPOTIFY CATALOG / 04"
      title="아티스트 디스코그래피"
      description="목록에서 원하는 아티스트만 선택해 Spotify 카탈로그를 등록하고 탐색합니다."
    />

    <div v-if="artistsQuery.isError.value || syncArtist.isError.value || searchCandidates.isError.value" class="alert alert--error">
      {{ syncArtist.error.value?.message || searchCandidates.error.value?.message || 'Spotify 아티스트 정보를 불러오지 못했습니다.' }}
    </div>

    <section class="artist-kind-picker" aria-label="아티스트 유형 선택">
      <UButton :class="{ active: artistKind === 'vtuber' }" @click="selectArtistKind('vtuber')">
        <span>VIRTUAL ARTIST</span>
        <strong>VTuber</strong>
        <em>{{ allArtists.filter((artist) => artist.artist_kind === 'vtuber').length }}명</em>
      </UButton>
      <UButton :class="{ active: artistKind === 'singer' }" @click="selectArtistKind('singer')">
        <span>MUSIC ARTIST</span>
        <strong>가수</strong>
        <em>{{ allArtists.filter((artist) => artist.artist_kind === 'singer').length }}명</em>
      </UButton>
    </section>

    <div v-if="artistKind === 'vtuber'" class="agency-filter" aria-label="VTuber 소속 선택">
      <UButton :class="{ active: agencyFilter === 'all' }" @click="agencyFilter = 'all'">전체</UButton>
      <UButton
        v-for="agency in agenciesQuery.data.value || []"
        :key="agency.id"
        :class="{ active: agencyFilter === agency.name }"
        @click="agencyFilter = agency.name"
      >
        {{ agency.name === 'KAMITSUBAKI STUDIO' ? 'KAMITSUBAKI' : agency.name }}
      </UButton>
      <UButton class="agency-filter__add" @click="agencyModal = true">+ 소속 추가</UButton>
    </div>

    <section v-if="artistKind" class="artist-rail-section">
      <div class="section-heading">
        <div><p class="eyebrow">SELECT ARTIST</p><h2>아티스트 선택</h2></div>
        <span class="count-label">{{ artists.length }} ARTISTS</span>
      </div>
      <div v-if="artistsQuery.isPending.value" class="artist-card-grid">
        <div v-for="index in 5" :key="index" class="artist-card artist-card--loading" />
      </div>
      <div v-else class="artist-card-grid">
        <UButton
          v-for="artist in artists"
          :key="artist.local_artist_id"
          class="artist-card"
          :class="{ selected: artist.local_artist_id === selectedArtistId && !relationMode, unmatched: !artist.matched }"
          :disabled="syncArtist.isPending.value"
          @click="selectArtist(artist)"
        >
          <img v-if="artist.image_url" :src="artist.image_url" :alt="artist.local_name" />
          <div v-else class="artist-card__fallback">{{ artist.local_name.slice(0, 1) }}</div>
          <div class="artist-card__shade" />
          <div class="artist-card__content">
            <span>{{ artist.matched ? 'SPOTIFY ARTIST' : 'MATCH NEEDED' }}</span>
            <strong>{{ artist.local_name }}</strong>
            <em>{{ artist.matched ? '카탈로그 보기 →' : (searchCandidates.isPending.value && searchCandidates.variables.value === artist.local_artist_id ? '후보 검색 중…' : '클릭하여 후보 선택') }}</em>
          </div>
        </UButton>
      </div>
    </section>
    <section v-else class="empty-state artist-kind-empty">
      <strong>먼저 아티스트 유형을 선택해 주세요</strong>
      <p>VTuber와 일반 가수의 카탈로그를 나누어 탐색할 수 있습니다.</p>
    </section>

    <section v-if="relationMode" class="relationship-panel">
      <div class="relationship-panel__intro">
        <p class="eyebrow">COLLABORATION MAP</p>
        <h2>등록 아티스트 연관도</h2>
        <p>공동 명의로 발매된 앨범과 싱글을 기준으로 연결 강도를 계산합니다.</p>
      </div>
      <div v-if="relationshipsQuery.isPending.value" class="relation-loading">
        Spotify 공동 크레딧을 분석하고 있습니다…
      </div>
      <div v-else-if="relationshipsQuery.data.value?.length" class="relation-grid">
        <article
          v-for="relation in relationshipsQuery.data.value"
          :key="`${relation.source_artist_id}-${relation.target_artist_id}`"
          class="relation-card"
        >
          <div class="relation-card__artists">
            <div>
              <img v-if="artistById.get(relation.source_artist_id)?.image_url" :src="artistById.get(relation.source_artist_id)?.image_url || ''" alt="" />
              <span>{{ artistById.get(relation.source_artist_id)?.spotify_name }}</span>
            </div>
            <div class="relation-card__line">
              <i v-for="index in Math.min(relation.strength, 5)" :key="index" />
              <b>{{ relation.strength }}</b>
            </div>
            <div>
              <img v-if="artistById.get(relation.target_artist_id)?.image_url" :src="artistById.get(relation.target_artist_id)?.image_url || ''" alt="" />
              <span>{{ artistById.get(relation.target_artist_id)?.spotify_name }}</span>
            </div>
          </div>
          <p>{{ relation.shared_releases.slice(0, 3).join(' · ') }}</p>
        </article>
      </div>
      <div v-else class="empty-state">
        <span>⌘</span><strong>공동 발매 연결을 찾지 못했습니다</strong>
        <p>Spotify의 Related Artists API 대신 공식 공동 크레딧만 사용하므로 결과가 없을 수 있습니다.</p>
      </div>
    </section>

    <template v-else-if="selectedArtist">
      <section v-if="selectedArtist" class="artist-catalog-header">
        <div>
          <p class="eyebrow">DISCOGRAPHY</p>
          <h2>{{ selectedArtist.local_name }}</h2>
          <div class="catalog-stats">
            <span><b>{{ albumCount }}</b> Albums</span>
            <span><b>{{ singleCount }}</b> Singles / EPs</span>
            <span><b>{{ discographyQuery.data.value?.length || 0 }}</b> Releases</span>
          </div>
        </div>
        <div class="catalog-actions">
          <a v-if="selectedArtist.spotify_url" :href="selectedArtist.spotify_url" target="_blank" rel="noreferrer" class="spotify-attribution">
            Spotify에서 보기 ↗
          </a>
          <UButton
            class="button button--danger"
            :disabled="excludeArtist.isPending.value"
            @click="confirmSpotifyExclusion(selectedArtist)"
          >
            {{ excludeArtist.isPending.value ? '제외 중…' : 'Spotify 동기화 제외' }}
          </UButton>
        </div>
      </section>

      <section class="catalog-toolbar">
        <div class="filter-tabs">
          <UButton :class="{ active: releaseFilter === 'all' }" @click="releaseFilter = 'all'">전체</UButton>
          <UButton :class="{ active: releaseFilter === 'album' }" @click="releaseFilter = 'album'">앨범</UButton>
          <UButton :class="{ active: releaseFilter === 'single' }" @click="releaseFilter = 'single'">싱글 · EP</UButton>
          <UButton :class="{ active: releaseFilter === 'appears_on' }" @click="releaseFilter = 'appears_on'">참여작</UButton>
        </div>
        <div class="view-toggle" aria-label="보기 방식">
          <UButton :class="{ active: viewMode === 'grid' }" aria-label="이미지 보기" @click="viewMode = 'grid'">▦</UButton>
          <UButton :class="{ active: viewMode === 'list' }" aria-label="목록 보기" @click="viewMode = 'list'">☷</UButton>
        </div>
      </section>

      <div v-if="discographyQuery.isPending.value" class="release-grid">
        <div v-for="index in 8" :key="index" class="release-card release-card--loading" />
      </div>
      <div v-else-if="discographyQuery.isError.value" class="alert alert--error">
        {{ discographyQuery.error.value?.message || '디스코그래피 조회에 실패했습니다.' }}
      </div>
      <div v-else-if="filteredAlbums.length" :class="viewMode === 'grid' ? 'release-grid' : 'release-list'">
        <UButton
          v-for="album in filteredAlbums"
          :key="album.id"
          :class="viewMode === 'grid' ? 'release-card' : 'release-row'"
          @click="selectedAlbumId = album.id"
        >
          <div class="release-cover">
            <img v-if="album.image_url" :src="album.image_url" :alt="album.name" />
            <div v-else class="release-cover__fallback">♫</div>
            <div class="release-cover__action">수록곡 보기</div>
          </div>
          <div class="release-meta">
            <span>{{ albumKind(album) }} · {{ album.release_date || '날짜 미정' }}</span>
            <strong>{{ album.name }}</strong>
            <p>{{ album.artists.join(', ') }}</p>
            <em>{{ album.total_tracks }} TRACKS</em>
          </div>
        </UButton>
      </div>
      <div v-else class="empty-state">
        <span>♫</span><strong>표시할 발매작이 없습니다</strong><p>다른 필터를 선택하거나 Spotify 동기화를 다시 실행해 주세요.</p>
      </div>
    </template>

    <AppModal
      :open="agencyModal"
      title="VTuber 소속 추가"
      description="기업, 레이블 또는 프로젝트 이름을 등록하면 소속 필터에 바로 추가됩니다."
      @close="agencyModal = false"
    >
      <form class="form-grid" @submit.prevent="submitAgency">
        <label class="form-grid__wide">소속 이름<UInput v-model="newAgencyName" required maxlength="120" placeholder="예: hololive production" /></label>
        <p v-if="createAgency.error.value" class="form-error">{{ createAgency.error.value.message }}</p>
        <div class="form-actions">
          <UButton type="button" class="button button--ghost" @click="agencyModal = false">취소</UButton>
          <UButton class="button button--primary" :disabled="createAgency.isPending.value">{{ createAgency.isPending.value ? '추가 중…' : '소속 추가' }}</UButton>
        </div>
      </form>
    </AppModal>

    <AppModal
      :open="Boolean(candidateArtist)"
      :title="`${candidateArtist?.local_name || ''} Spotify 후보 선택`"
      description="프로필 이미지, 이름과 장르를 확인한 뒤 정확한 공식 아티스트를 선택해 주세요."
      @close="candidateArtist = null"
    >
      <div v-if="searchCandidates.isPending.value" class="skeleton-list"><i /><i /><i /></div>
      <div v-else-if="candidateResults.length" class="spotify-candidate-list">
        <article v-for="candidate in candidateResults" :key="candidate.spotify_artist_id" class="spotify-candidate">
          <img v-if="candidate.image_url" :src="candidate.image_url" :alt="candidate.name" />
          <div v-else class="spotify-candidate__fallback">{{ candidate.name.slice(0, 1) }}</div>
          <div>
            <strong>{{ candidate.name }}</strong>
            <p>{{ candidate.genres.length ? candidate.genres.join(' · ') : '장르 정보 없음' }}</p>
            <a v-if="candidate.spotify_url" :href="candidate.spotify_url" target="_blank" rel="noreferrer">Spotify에서 확인 ↗</a>
          </div>
          <UButton class="button button--spotify" :disabled="syncArtist.isPending.value" @click="confirmCandidate(candidate)">
            {{ syncArtist.isPending.value ? '등록 중…' : '이 아티스트로 등록' }}
          </UButton>
        </article>
      </div>
      <div v-else class="empty-state"><strong>Spotify 검색 후보가 없습니다</strong><p>등록된 아티스트 이름을 확인해 주세요.</p></div>
    </AppModal>

    <AppModal
      :open="Boolean(selectedAlbumId)"
      :title="albumQuery.data.value?.name || '앨범 불러오는 중'"
      :description="albumQuery.data.value ? `${albumQuery.data.value.artists.join(', ')} · ${albumQuery.data.value.release_date || ''}` : 'Spotify에서 수록곡을 가져오고 있습니다.'"
      @close="selectedAlbumId = null"
    >
      <div v-if="albumQuery.isPending.value" class="skeleton-list"><i /><i /><i /><i /></div>
      <div v-else-if="albumQuery.isError.value" class="alert alert--error">{{ albumQuery.error.value?.message || '앨범 조회에 실패했습니다.' }}</div>
      <div v-else-if="albumQuery.data.value" class="album-detail">
        <div class="album-detail__hero">
          <img v-if="albumQuery.data.value.image_url" :src="albumQuery.data.value.image_url" :alt="albumQuery.data.value.name" />
          <div><StatusPill :label="albumKind(albumQuery.data.value)" tone="green" /><strong>{{ albumQuery.data.value.total_tracks }}곡</strong></div>
        </div>
        <ol class="track-list">
          <li v-for="track in albumQuery.data.value.tracks" :key="track.id">
            <span>{{ track.track_number.toString().padStart(2, '0') }}</span>
            <div><strong>{{ track.name }}</strong><em>{{ track.artists.join(', ') }}</em></div>
            <b v-if="track.explicit">E</b>
            <time>{{ duration(track.duration_ms) }}</time>
            <a v-if="track.spotify_url" :href="track.spotify_url" target="_blank" rel="noreferrer" @click.stop>↗</a>
          </li>
        </ol>
        <a v-if="albumQuery.data.value.spotify_url" :href="albumQuery.data.value.spotify_url" target="_blank" rel="noreferrer" class="button button--spotify album-detail__link">Spotify에서 전체 보기 ↗</a>
      </div>
    </AppModal>
  </div>
</template>
