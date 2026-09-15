<script setup lang="ts">
import { AudioLines, RotateCcw, SearchX } from '@lucide/vue'
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from '@/components/ui/empty'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
defineProps<{
  loading?: boolean
  error?: string
  empty?: boolean
  title?: string
  description?: string
}>()
defineEmits<{ retry: [] }>()
</script>
<template>
  <div v-if="loading" class="loading-grid" role="status" aria-label="불러오는 중">
    <div v-for="n in 6" :key="n" class="flex flex-col gap-4">
      <Skeleton class="aspect-square w-full" />
      <Skeleton class="h-4 w-2/3" />
      <Skeleton class="h-3 w-1/3" />
    </div>
  </div>
  <Empty v-else-if="error || empty">
    <EmptyHeader>
      <EmptyMedia variant="icon">
        <AudioLines v-if="error" />
        <SearchX v-else />
      </EmptyMedia>
      <EmptyTitle>{{ error ? '불러오지 못했어요' : title || '아직 콘텐츠가 없어요' }}</EmptyTitle>
      <EmptyDescription v-if="error || description">
        {{ error || description }}
      </EmptyDescription>
    </EmptyHeader>
    <EmptyContent v-if="error">
      <Button variant="outline" @click="$emit('retry')">
        <RotateCcw data-icon="inline-start" />
        다시 시도
      </Button>
    </EmptyContent>
    <EmptyContent v-else><slot name="action" /></EmptyContent>
  </Empty>
  <slot v-else />
</template>
