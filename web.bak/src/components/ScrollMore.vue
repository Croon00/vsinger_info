<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch, nextTick } from 'vue'

const props = defineProps<{ shown: number; total: number }>()
const emit = defineEmits<{ more: [] }>()
const sentinel = ref<HTMLElement | null>(null)
let observer: IntersectionObserver | undefined
onMounted(() => {
  if (!('IntersectionObserver' in window)) return
  observer = new IntersectionObserver(([entry]) => {
    if (entry?.isIntersecting && props.shown < props.total) emit('more')
  }, { rootMargin: '240px' })
  if (sentinel.value) observer.observe(sentinel.value)
})
watch(() => [props.shown, props.total], async () => {
  await nextTick()
  if (sentinel.value) {
    observer?.unobserve(sentinel.value)
    observer?.observe(sentinel.value)
  }
})
onBeforeUnmount(() => observer?.disconnect())
</script>

<template>
  <div ref="sentinel" class="scroll-more" aria-live="polite">
    <span>{{ Math.min(shown, total) }} / {{ total }}개 표시</span>
    <UButton v-if="shown < total" variant="outline" @click="emit('more')">더 보기</UButton>
    <span v-else-if="total">전체 기록을 표시했습니다</span>
  </div>
</template>

<style scoped>
.scroll-more { display:flex; justify-content:center; align-items:center; gap:16px; padding:24px; color:var(--muted); font-size:12px; }
</style>
