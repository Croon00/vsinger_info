<script setup lang="ts">
import { computed } from 'vue'
import { CalendarDays } from '@lucide/vue'
const props = defineProps<{ color?: string; name?: string }>()
const valid = computed(() => /^#[0-9a-f]{6}$/i.test(props.color || ''))
const colorStyle = computed(() => ({ '--artist-color': valid.value ? props.color : '#808080' }))
</script>
<template>
  <div class="artist-color-preview" :style="colorStyle">
    <figure v-for="mode in ['light', 'dark']" :key="mode" :class="['color-day', mode]" :aria-label="mode === 'light' ? '라이트 일정 미리보기' : '다크 일정 미리보기'">
      <figcaption>{{ mode === 'light' ? '라이트' : '다크' }}</figcaption>
      <div class="preview-day-number">20</div>
      <div class="preview-event"><CalendarDays aria-hidden="true" /><span>{{ name || '아티스트' }} 공연</span></div>
    </figure>
  </div>
</template>
<style scoped>
.artist-color-preview { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
.color-day { min-width: 0; margin: 0; padding: 8px; border: 1px solid; border-radius: var(--radius-lg); }
.color-day.light { background: #fff; color: #171717; border-color: #e5e5e5; --event-ink: #171717; --event-base: #fff; }
.color-day.dark { background: #171717; color: #fafafa; border-color: #404040; --event-ink: #fafafa; --event-base: #171717; }
figcaption { font-size: 11px; opacity: .6; }
.preview-day-number { font-size: 12px; line-height: 16px; margin: 8px 0 4px; opacity: .65; }
.preview-event { display: flex; align-items: center; gap: 4px; min-height: 22px; padding: 2px 6px; border-radius: var(--radius); background: color-mix(in srgb, var(--artist-color) 25%, var(--event-base)); color: var(--event-ink); font-size: 11px; font-weight: 500; }
.preview-event svg { width: 12px; height: 12px; flex-shrink: 0; }
.preview-event span { overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
</style>
