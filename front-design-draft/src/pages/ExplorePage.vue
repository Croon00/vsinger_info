<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Search, X } from '@lucide/vue'
import { InputGroup, InputGroupInput, InputGroupAddon } from '@/components/ui/input-group'
import { Button } from '@/components/ui/button'
import { FieldGroup, Field, FieldLabel } from '@/components/ui/field'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { api } from '@/api/client'
import { useResource } from '@/composables/useResource'
import { normalize } from '@/lib/search'
import ArtistTile from '@/components/ArtistTile.vue'
import ResourceState from '@/components/ResourceState.vue'
const route = useRoute()
const router = useRouter()
const query = ref(String(route.query.q ?? ''))
const agency = ref('all')
const { data, loading, error, reload } = useResource(api.artists)
watch(query, (q) => router.replace({ query: { ...route.query, q: q || undefined } }))
watch(
  () => route.query.q,
  (q) => {
    query.value = String(q ?? '')
  },
)
const filtered = computed(() =>
  (data.value ?? []).filter(
    (a) =>
      (agency.value === 'all' || a.agency === agency.value) &&
      [a.name, a.display_name, a.roman].some((s) => normalize(s).includes(normalize(query.value))),
  ),
)
</script>
<template>
  <div class="page-container page-enter">
    <div class="page-heading">
      <h1>아티스트 탐색</h1>
    </div>
    <div class="explore-toolbar">
      <ToggleGroup
        type="single"
        :model-value="agency"
        @update:model-value="(v) => (agency = String(v || 'all'))"
        variant="outline"
        aria-label="소속사 필터"
      >
        <ToggleGroupItem value="all">전체</ToggleGroupItem>
        <ToggleGroupItem value="RK Music">RK Music</ToggleGroupItem>
        <ToggleGroupItem value="KAMITSUBAKI STUDIO">KAMITSUBAKI</ToggleGroupItem>
      </ToggleGroup>
      <form role="search" aria-label="아티스트 검색" class="explore-search" @submit.prevent>
        <FieldGroup>
          <Field>
            <FieldLabel for="artist-search" class="sr-only">아티스트 이름</FieldLabel>
            <InputGroup class="h-11">
              <InputGroupAddon><Search /></InputGroupAddon>
              <InputGroupInput
                id="artist-search"
                v-model="query"
                placeholder="아티스트 이름으로 찾기"
              />
              <InputGroupAddon v-if="query" align="inline-end">
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  aria-label="검색어 지우기"
                  @click="query = ''"
                >
                  <X />
                </Button>
              </InputGroupAddon>
            </InputGroup>
          </Field>
        </FieldGroup>
      </form>
    </div>
    <p class="result-count" aria-live="polite">{{ filtered.length }}명의 아티스트</p>
    <ResourceState
      :loading="loading"
      :error="error"
      :empty="filtered.length === 0"
      title="아티스트를 찾지 못했어요"
      description="다른 이름으로 검색하거나 소속사 필터를 바꿔보세요."
      @retry="reload"
    >
      <div class="artist-grid">
        <ArtistTile v-for="artist in filtered" :key="artist.id" :artist="artist" />
      </div>
    </ResourceState>
  </div>
</template>
