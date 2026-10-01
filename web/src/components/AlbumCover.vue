<script setup lang="ts">
import { ref, watch } from 'vue'
import { Disc3 } from '@lucide/vue'
// decorative: the release title is already visible next to the cover, so the image
// is hidden from assistive technology instead of repeating the title.
const props = defineProps<{ src: string; title: string; decorative?: boolean }>()
const failed = ref(false)
watch(
  () => props.src,
  () => {
    failed.value = false
  },
)
</script>
<template>
  <img
    v-if="src && !failed"
    :src="src"
    :alt="decorative ? '' : `${title} 앨범 커버`"
    loading="lazy"
    decoding="async"
    @error="failed = true"
  />
  <div v-else-if="decorative" class="album-cover-fallback" aria-hidden="true">
    <Disc3 class="size-10" />
  </div>
  <div v-else class="album-cover-fallback" role="img" :aria-label="`${title}, 앨범 이미지 준비 중`">
    <Disc3 class="size-12" />
    <span>{{ title }}</span>
    <small>앨범 이미지 준비 중</small>
  </div>
</template>
