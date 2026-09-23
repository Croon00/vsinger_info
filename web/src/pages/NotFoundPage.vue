<script setup lang="ts">
import ResourceState from '@/components/ResourceState.vue'
import { Button } from '@/components/ui/button'
</script>
<template>
  <div class="page-container">
    <ResourceState
      empty
      title="페이지를 찾을 수 없어요"
      description="주소를 확인하거나 홈에서 다시 시작해 보세요."
    >
      <template #action>
        <Button as-child><RouterLink to="/">홈으로</RouterLink></Button>
      </template>
    </ResourceState>
  </div>
</template>
