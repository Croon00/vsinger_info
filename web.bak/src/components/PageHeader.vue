<script setup lang="ts">
defineProps<{
  eyebrow: string
  title: string
  description: string
}>()
</script>

<template>
  <header class="page-header">
    <div>
      <p class="eyebrow">{{ eyebrow }}</p>
      <h1>{{ title }}</h1>
      <p class="page-description">{{ description }}</p>
    </div>
    <div class="page-header__actions">
      <slot />
    </div>
  </header>
</template>
