<script setup lang="ts">
import { ref, watch } from 'vue'
import { ArrowRight, Search, X } from '@lucide/vue'
import { InputGroup, InputGroupAddon, InputGroupInput } from '@/components/ui/input-group'
import { Button } from '@/components/ui/button'
import { Field, FieldGroup, FieldLabel } from '@/components/ui/field'
import { cn } from '@/lib/utils'
const props = withDefaults(
  defineProps<{ initial?: string; large?: boolean; label?: string; placeholder?: string }>(),
  { initial: '', label: '통합검색', placeholder: '아티스트, 원곡, 원곡 아티스트를 검색하세요' },
)
const emit = defineEmits<{ search: [value: string] }>()
function clearSearch() {
  query.value = ''
  emit('search', '')
}
const query = ref(props.initial)
const composing = ref(false)
watch(
  () => props.initial,
  (v) => {
    query.value = v
  },
)
</script>
<template>
  <form
    role="search"
    :aria-label="label"
    :class="cn('search-form', large && 'large')"
    @submit.prevent="!composing && emit('search', query.trim())"
  >
    <FieldGroup>
      <Field>
        <FieldLabel class="sr-only" :for="`search-${label}`">{{ label }}</FieldLabel>
        <InputGroup :class="cn(large ? 'h-16 px-3' : 'h-11 px-2')">
          <InputGroupAddon><Search aria-hidden="true" /></InputGroupAddon>
          <InputGroupInput
            :id="`search-${label}`"
            v-model="query"
            :placeholder="placeholder"
            autocomplete="off"
            @compositionstart="composing = true"
            @compositionend="composing = false"
          />
          <InputGroupAddon align="inline-end">
            <Button
              v-if="query"
              type="button"
              variant="ghost"
              size="icon-sm"
              aria-label="검색어 지우기"
              @click="clearSearch"
            >
              <X />
            </Button>
            <Button type="submit" :size="large ? 'icon-lg' : 'icon'" aria-label="검색">
              <ArrowRight data-icon="inline-start" />
            </Button>
          </InputGroupAddon>
        </InputGroup>
      </Field>
    </FieldGroup>
  </form>
</template>
