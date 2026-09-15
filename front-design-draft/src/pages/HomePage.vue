<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowUpRight, Music2 } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
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
    <section class="home-hero">
      <p class="eyebrow hero-eyebrow">
        <span class="tiny-wave">
          <i />
          <i />
          <i />
          <i />
        </span>
        A SPACE FOR YOUR FAVORITE VOICES
      </p>
      <h1>
        좋아하는 목소리가
        <br />
        <span>모이는 곳.</span>
      </h1>
      <p class="hero-description">마음에 남은 노래부터, 다시 듣고 싶은 라이브까지.</p>
      <SearchForm large @search="search" />
      <div class="search-suggestions">
        <span>이렇게 찾아보세요</span>
        <Button variant="ghost" size="sm" @click="search('HACHI')">
          HACHI
          <ArrowUpRight data-icon="inline-end" />
        </Button>
        <Button variant="ghost" size="sm" @click="search('요루시카')">
          요루시카
          <ArrowUpRight data-icon="inline-end" />
        </Button>
        <Button variant="ghost" size="sm" @click="search('晴る')">
          晴る
          <ArrowUpRight data-icon="inline-end" />
        </Button>
      </div>
    </section>
    <section class="favorites-section" aria-labelledby="favorites-heading">
      <div class="section-heading">
        <div>
          <p class="eyebrow">ALWAYS CLOSE TO YOU</p>
          <h2 id="favorites-heading">
            나의 아티스트
            <span>{{ favorites.length.toString().padStart(2, '0') }}</span>
          </h2>
        </div>
        <Button variant="ghost" as-child>
          <RouterLink to="/explore">
            아티스트 찾아보기
            <ArrowUpRight data-icon="inline-end" />
          </RouterLink>
        </Button>
      </div>
      <ResourceState
        :loading="loading"
        :error="error"
        :empty="favorites.length === 0"
        title="어떤 목소리를 좋아하시나요?"
        description="아티스트의 하트를 누르면 이곳에서 바로 만날 수 있어요."
        @retry="reload"
      >
        <template #action>
          <Button as-child><RouterLink to="/explore">아티스트 둘러보기</RouterLink></Button>
        </template>
        <div class="favorite-grid">
          <ArtistTile v-for="artist in favorites" :key="artist.id" :artist="artist" compact />
        </div>
      </ResourceState>
    </section>
    <Separator />
    <RouterLink to="/explore" class="home-discover">
      <span class="discover-icon"><Music2 class="size-5" /></span>
      <div>
        <h3>아직 만나지 못한, 취향의 발견</h3>
        <p>새로운 아티스트의 음악 세계를 둘러보세요.</p>
      </div>
      <ArrowUpRight class="size-5 ml-auto" />
    </RouterLink>
  </div>
</template>
