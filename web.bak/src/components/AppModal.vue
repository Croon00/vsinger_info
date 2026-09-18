<script setup lang="ts">
defineProps<{ open: boolean; title: string; description?: string; contentClass?: string }>()
const emit = defineEmits<{ close: [] }>()
</script>

<template>
  <UModal
    :open="open"
    :title="title"
    :description="description"
    :ui="{ content: contentClass ? `modal ${contentClass}` : 'modal' }"
    @update:open="(value: boolean) => !value && emit('close')"
  >
    <template #body>
      <slot />
    </template>
  </UModal>
</template>
