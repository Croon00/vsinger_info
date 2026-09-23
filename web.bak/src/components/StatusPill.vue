<script setup lang="ts">
defineProps<{
  label: string
  tone?: 'cyan' | 'violet' | 'green' | 'amber' | 'muted'
}>()
</script>

<template>
  <span class="status-pill" :class="`status-pill--${tone || 'muted'}`">
    <span class="status-pill__dot" />
    {{ label }}
  </span>
</template>
