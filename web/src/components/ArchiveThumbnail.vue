<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ListMusic } from '@lucide/vue'
const props = defineProps<{ videoId: string }>()
const qualities = ['mqdefault', 'hqdefault']
const index = ref(0)
const source = computed(
  () => `https://i.ytimg.com/vi/${props.videoId}/${qualities[index.value]}.jpg`,
)
watch(
  () => props.videoId,
  () => {
    index.value = 0
  },
)
function loaded(event: Event) {
  if ((event.target as HTMLImageElement).naturalWidth <= 120) index.value++
}
</script>
<template>
  <div class="archive-thumbnail" aria-hidden="true">
    <img
      v-if="index < qualities.length"
      :src="source"
      alt=""
      width="320"
      height="180"
      loading="lazy"
      referrerpolicy="strict-origin-when-cross-origin"
      @load="loaded"
      @error="index++"
    />
    <ListMusic v-else class="size-6" />
  </div>
</template>
