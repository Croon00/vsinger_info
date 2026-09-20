<script setup lang="ts">
import { computed, ref, watch, onBeforeUnmount } from 'vue'
import { ImageOff, UserRound } from '@lucide/vue'
const props = defineProps<{ url?: string; name?: string }>()
const source = ref('')
const status = ref<'empty' | 'loading' | 'ready' | 'error'>('empty')
let timer: ReturnType<typeof setTimeout> | undefined
const validUrl = computed(() => {
  try { const u = new URL(props.url || ''); return ['https:', 'http:'].includes(u.protocol) ? u.href : '' }
  catch { return '' }
})
watch(() => props.url, () => {
  clearTimeout(timer)
  source.value = ''
  status.value = props.url ? (validUrl.value ? 'loading' : 'error') : 'empty'
  if (validUrl.value) timer = setTimeout(() => { source.value = validUrl.value }, 300)
}, { immediate: true })
onBeforeUnmount(() => clearTimeout(timer))
</script>
<template>
  <div class="flex flex-col items-start gap-2" aria-label="프로필 이미지 미리보기">
    <div class="relative flex aspect-square w-50 max-w-full shrink-0 items-center justify-center overflow-hidden rounded-xl border bg-muted text-muted-foreground">
      <img v-if="source" :key="source" :src="source" :alt="(name || '아티스트') + ' 프로필 미리보기'" referrerpolicy="no-referrer" class="size-full object-cover" :class="{ invisible: status !== 'ready' }" @load="status = 'ready'" @error="status = 'error'" />
      <ImageOff v-if="status === 'error'" class="absolute size-5" aria-hidden="true" />
      <UserRound v-else-if="status !== 'ready'" class="absolute size-5" aria-hidden="true" />
    </div>
    <p v-if="status !== 'ready'" class="text-xs text-muted-foreground" role="status">{{ status === 'empty' ? '이미지 주소를 입력하면 표시됩니다.' : status === 'loading' ? '이미지를 불러오는 중입니다.' : status === 'error' ? '이미지를 불러올 수 없습니다. 주소를 확인하세요.' : '' }}</p>
  </div>
</template>
