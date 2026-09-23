<script setup lang="ts">
import { ref, watch } from 'vue'
import { Disc3 } from '@lucide/vue'
const props = defineProps<{ src: string; title: string }>()
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
    :alt="`${title} 앨범 커버`"
    loading="lazy"
    @error="failed = true"
  />
  <div v-else class="album-cover-fallback" role="img" :aria-label="`${title}, 앨범 이미지 준비 중`">
    <Disc3 class="size-12" />
    <span>{{ title }}</span>
    <small>앨범 이미지 준비 중</small>
  </div>
</template>
