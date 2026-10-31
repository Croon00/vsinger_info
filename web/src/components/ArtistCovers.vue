<script setup lang="ts">
import { computed, ref, watch, onScopeDispose } from 'vue'
import { ChevronDown } from '@lucide/vue'
import { api } from '@/api/client'
import type { Cover } from '@/api/types'
import { useResource } from '@/composables/useResource'
import { Button } from '@/components/ui/button'
import ResourceState from '@/components/ResourceState.vue'
import CoverCard from '@/components/CoverCard.vue'
const props = defineProps<{ artistId: number }>()
const extra = ref<Cover[]>([])
const moreLoading = ref(false)
const moreError = ref('')
let controller: AbortController | undefined
const { data, loading, error, reload } = useResource(
  (signal) => api.coverPage(props.artistId, 0, 12, signal),
  [() => props.artistId],
)
watch(data, () => {
  controller?.abort()
  extra.value = []
  moreLoading.value = false
  moreError.value = ''
})
onScopeDispose(() => controller?.abort())
const covers = computed(() => [...(data.value?.items ?? []), ...extra.value])
async function loadMore() {
  if (moreLoading.value) return
  const current = data.value
  const artist = props.artistId
  const request = new AbortController()
  controller = request
  moreLoading.value = true
  moreError.value = ''
  try {
    const page = await api.coverPage(artist, covers.value.length, 12, request.signal)
    if (!request.signal.aborted && data.value === current && props.artistId === artist)
      extra.value.push(...page.items)
  } catch (e) {
    if (!request.signal.aborted)
      moreError.value = e instanceof Error ? e.message : '커버 영상을 불러오지 못했어요.'
  } finally {
    if (controller === request) moreLoading.value = false
  }
}
</script>
<template>
  <section aria-label="커버 영상">
    <div class="section-heading">
      <h2 class="live-archive-title">
        커버 영상
        <span v-if="data">{{ data.total }}개</span>
      </h2>
      <span class="text-xs text-muted-foreground">최신순</span>
    </div>
    <ResourceState
      :loading="loading"
      :error="error"
      :empty="!covers.length"
      title="등록된 커버 영상이 없습니다"
      @retry="reload"
    >
      <div class="live-grid">
        <CoverCard v-for="cover in covers" :key="cover.id" :cover="cover" />
      </div>
      <Button
        v-if="(data?.total ?? 0) > covers.length"
        variant="outline"
        class="mx-auto mt-8 flex"
        :disabled="moreLoading"
        @click="loadMore"
      >
        더보기
        <ChevronDown data-icon="inline-end" />
      </Button>
      <p v-if="moreError" role="alert" class="text-sm text-destructive mt-3">{{ moreError }}</p>
    </ResourceState>
  </section>
</template>
