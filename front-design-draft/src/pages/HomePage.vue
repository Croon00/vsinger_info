<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowRight, AudioLines } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { api } from '@/api/client'
import { useResource } from '@/composables/useResource'
import { favoriteIds } from '@/composables/preferences'
import ArtistTile from '@/components/ArtistTile.vue'
import SearchForm from '@/components/SearchForm.vue'
import ResourceState from '@/components/ResourceState.vue'
const router = useRouter()
const { data, loading, error, reload } = useResource(api.artists)
const favorites = computed(() => (data.value ?? []).filter((a) => favoriteIds.value.includes(a.id)))
function search(q: string) {
  if (q) router.push({ path: '/search', query: { q } })
}
</script>
<template>
  <div class="home-page page-enter">
    <section class="home-search" aria-labelledby="home-heading">
      <div class="home-title" aria-label="schedule_music">
        <AudioLines class="size-5" aria-hidden="true" />
        <span>schedule_music</span>
      </div>
      <h1 id="home-heading" class="sr-only">통합검색</h1>
      <SearchForm large placeholder="아티스트 또는 원곡 검색" @search="search" />
      <p class="search-help">아티스트 이름, 원곡명, 원곡 아티스트로 검색</p>
    </section>
    <section class="favorites-section" aria-labelledby="favorites-heading">
      <div class="section-heading">
        <div>
          <h2 id="favorites-heading">
            즐겨찾기
            <span>{{ favorites.length }}</span>
          </h2>
        </div>
        <Button variant="ghost" as-child>
          <RouterLink to="/explore">
            아티스트 찾기
            <ArrowRight data-icon="inline-end" />
          </RouterLink>
        </Button>
      </div>
      <ResourceState
        :loading="loading"
        :error="error"
        :empty="favorites.length === 0"
        title="즐겨찾기한 아티스트가 없습니다"
        description="아티스트의 하트 버튼을 눌러 추가하세요."
        @retry="reload"
      >
        <template #action>
          <Button as-child><RouterLink to="/explore">아티스트 탐색</RouterLink></Button>
        </template>
        <div class="favorite-grid">
          <ArtistTile v-for="artist in favorites" :key="artist.id" :artist="artist" compact />
        </div>
      </ResourceState>
    </section>
  </div>
</template>
