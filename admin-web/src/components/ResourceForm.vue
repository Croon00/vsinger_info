<script setup lang="ts">
import { computed, useId } from 'vue'
import type { Resource, Data, FieldSpec } from '@/lib/api'
import { labels, optionLabels } from '@/lib/api'
import {
  FieldGroup,
  Field,
  FieldLabel,
  FieldDescription,
} from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Switch } from '@/components/ui/switch'
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectGroup,
  SelectItem,
} from '@/components/ui/select'
import RelationPicker from './RelationPicker.vue'
const props = defineProps<{
  resource: Resource
  modelValue: Data
  batchId?: string
  disabled?: boolean
}>()
const emit = defineEmits<{ 'update:modelValue': [data: Data] }>()
const uid = useId()
const groups = computed(() => [
  {
    label: '기본 정보',
    fields: props.resource.fields.filter(
      (f) =>
        !f.nullable ||
        [
          'name_ko',
          'title_ko',
          'song_id',
          'primary_artist_id',
          'show_in_catalog',
        ].includes(f.name),
    ),
  },
  {
    label: '추가 정보',
    fields: props.resource.fields.filter(
      (f) =>
        f.nullable &&
        ![
          'name_ko',
          'title_ko',
          'song_id',
          'primary_artist_id',
          'show_in_catalog',
        ].includes(f.name),
    ),
  },
])
function set(f: FieldSpec, value: any) {
  let next = value
  if (value === '__empty') next = null
  if (f.type === 'BOOLEAN' && f.nullable && value !== '__empty')
    next = value === 'true'
  if (value === '' && f.nullable) next = null
  if (['INTEGER', 'SMALLINT'].includes(f.type) && !f.reference && value !== '')
    next = Number(value)
  if (f.type === 'JSONB' && typeof value === 'string') {
    try {
      next = JSON.parse(value)
    } catch {
      next = value
    }
  }
  emit('update:modelValue', { ...props.modelValue, [f.name]: next })
}
const multiline = (f: FieldSpec) =>
  f.type === 'JSONB' ||
  [
    'bio',
    'content_text',
    'original_lyrics',
    'translation_ko',
    'pronunciation_ko',
  ].includes(f.name)
const displayed = (f: FieldSpec) =>
  f.type === 'JSONB' &&
  typeof props.modelValue[f.name] === 'object' &&
  props.modelValue[f.name] !== null
    ? JSON.stringify(props.modelValue[f.name], null, 2)
    : (props.modelValue[f.name] ?? '')
function help(f: FieldSpec) {
  if (f.name === 'slug') return '주소에 사용할 고유한 이름입니다. 예: hachi'
  if (f.type === 'TIMESTAMPTZ')
    return '시간대를 포함해 입력하세요. 예: 2026-09-20T19:00:00+09:00'
  if (f.name === 'timezone_name') return '예: Asia/Tokyo, Asia/Seoul'
  if (f.name === 'language_code') return '예: ja, ko, en · 모르면 비워 두세요.'
  if (f.name === 'song_id') return '확인되지 않은 곡은 연결하지 않아도 됩니다.'
  if (f.name === 'platform_video_id') return 'YouTube 주소의 11자리 영상 ID'
  return ''
}
</script>
<template>
  <div class="space-y-7">
    <section
      v-for="group in groups.filter((g) => g.fields.length)"
      :key="group.label"
    >
      <h3 class="mb-4 text-sm font-semibold">{{ group.label }}</h3>
      <FieldGroup class="grid grid-cols-1 gap-x-6 gap-y-5 sm:grid-cols-2">
        <Field
          v-for="f in group.fields"
          :key="f.name"
          :class="multiline(f) ? 'sm:col-span-2' : ''"
        >
          <FieldLabel :for="uid + f.name"
            >{{ labels[f.name] || f.name }}
            <span
              v-if="!f.nullable && f.default === undefined"
              class="text-muted-foreground"
              aria-label="필수"
              >*</span
            ></FieldLabel
          >
          <RelationPicker
            v-if="f.reference"
            :id="uid + f.name"
            :model-value="modelValue[f.name]"
            :target="f.reference"
            :label="labels[f.name] || f.name"
            :batch-id="batchId"
            :disabled="disabled"
            @update:model-value="set(f, $event)"
          />
          <Switch
            v-else-if="f.type === 'BOOLEAN' && !f.nullable"
            :id="uid + f.name"
            :model-value="Boolean(modelValue[f.name])"
            :disabled="disabled"
            @update:model-value="set(f, $event)"
          />
          <Select
            v-else-if="f.type === 'BOOLEAN'"
            :model-value="
              modelValue[f.name] == null
                ? '__empty'
                : String(modelValue[f.name])
            "
            :disabled="disabled"
            @update:model-value="set(f, $event)"
          >
            <SelectTrigger :id="uid + f.name" class="w-full"
              ><SelectValue
            /></SelectTrigger>
            <SelectContent
              ><SelectGroup
                ><SelectItem value="__empty">아직 확인 안 됨</SelectItem
                ><SelectItem value="true">예</SelectItem
                ><SelectItem value="false">아니요</SelectItem></SelectGroup
              ></SelectContent
            >
          </Select>
          <Select
            v-else-if="f.options"
            :model-value="modelValue[f.name] ?? '__empty'"
            :disabled="disabled"
            @update:model-value="set(f, $event)"
          >
            <SelectTrigger :id="uid + f.name" class="w-full"
              ><SelectValue
            /></SelectTrigger>
            <SelectContent
              ><SelectGroup
                ><SelectItem value="__empty">선택 안 함</SelectItem
                ><SelectItem
                  v-for="option in f.options"
                  :key="option"
                  :value="option"
                  >{{ optionLabels[option] || option }}</SelectItem
                ></SelectGroup
              ></SelectContent
            >
          </Select>
          <Textarea
            v-else-if="multiline(f)"
            :id="uid + f.name"
            :model-value="displayed(f)"
            :disabled="disabled"
            :rows="f.type === 'JSONB' ? 4 : 6"
            @update:model-value="set(f, $event)"
          />
          <Input
            v-else
            :id="uid + f.name"
            :model-value="displayed(f)"
            :disabled="disabled"
            :type="
              f.type === 'DATE'
                ? 'date'
                : ['INTEGER', 'SMALLINT'].includes(f.type)
                  ? 'number'
                  : 'text'
            "
            :inputmode="
              ['INTEGER', 'SMALLINT'].includes(f.type) ? 'numeric' : undefined
            "
            autocomplete="off"
            @update:model-value="set(f, $event)"
          />
          <FieldDescription v-if="help(f)">{{ help(f) }}</FieldDescription>
        </Field>
      </FieldGroup>
    </section>
  </div>
</template>
