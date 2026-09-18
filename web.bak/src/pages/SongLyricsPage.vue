<script setup lang="ts">
import { computed } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import { useRoute } from 'vue-router'
import { api } from '@/api/client'
import PageHeader from '@/components/PageHeader.vue'

const route = useRoute()
const songId = computed(() => Number(route.params.songId))
const lyricsQuery = useQuery({
  queryKey: ['song-lyrics', songId],
  queryFn: () => api.songs.lyrics(songId.value),
  enabled: computed(() => Number.isInteger(songId.value) && songId.value > 0),
})
</script>

<template>
  <div class="page song-lyrics-page">
    <PageHeader eyebrow="LYRICS LIBRARY" :title="lyricsQuery.data.value ? `${lyricsQuery.data.value.original_title}${lyricsQuery.data.value.title_ko ? ` (${lyricsQuery.data.value.title_ko})` : ''}` : '가사 불러오는 중'" :description="lyricsQuery.data.value ? `${lyricsQuery.data.value.artist_name}${lyricsQuery.data.value.album_name ? ` · ${lyricsQuery.data.value.album_name}` : ''}` : '원문 가사, 한국어 번역과 한글 발음을 불러옵니다.'">
      <RouterLink to="/music" class="button button--ghost">Spotify 목록</RouterLink>
    </PageHeader>

    <div v-if="lyricsQuery.isPending.value" class="skeleton-list"><i /><i /><i /></div>
    <div v-else-if="lyricsQuery.isError.value" class="alert alert--error">{{ lyricsQuery.error.value?.message || '가사를 불러오지 못했습니다.' }}</div>
    <template v-else-if="lyricsQuery.data.value">
      <div class="lyrics-source-line">
        <span :class="{ warning: lyricsQuery.data.value.needs_review }">{{ lyricsQuery.data.value.needs_review ? '검토 필요' : '검토 완료' }}</span>
        <a :href="lyricsQuery.data.value.youtube_url" target="_blank" rel="noreferrer">YouTube 원본 ↗</a>
      </div>
      <section class="lyrics-reading-grid">
        <article><p class="eyebrow">ORIGINAL</p><h2>원문 가사</h2><pre>{{ lyricsQuery.data.value.original_lyrics }}</pre></article>
        <article><p class="eyebrow">KOREAN TRANSLATION</p><h2>한국어 번역</h2><pre>{{ lyricsQuery.data.value.translation_ko }}</pre></article>
        <article><p class="eyebrow">KOREAN PRONUNCIATION</p><h2>한글 발음</h2><pre>{{ lyricsQuery.data.value.pronunciation_ko }}</pre></article>
      </section>
    </template>
  </div>
</template>
