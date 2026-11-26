<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { ApiError } from '@/api/http'
import {
  loadLyricsForEdit,
  saveLyrics,
  type LyricsEditDraft,
  type SavedLyrics,
} from '@/api/lyrics-editor'
import type { ExploredSong } from '@/api/types'
import { useResource } from '@/composables/useResource'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Field, FieldDescription, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import ResourceState from './ResourceState.vue'

const props = defineProps<{ song: ExploredSong | null }>()
const emit = defineEmits<{ close: []; saved: [song: ExploredSong, lyrics: SavedLyrics] }>()
const readExisting = ref(false)
const editing = computed(() => Boolean(props.song?.lyrics_recording_id) || readExisting.value)
const recordingId = computed(() => props.song?.lyrics_recording_id ?? props.song?.recording_id)
const empty: Omit<LyricsEditDraft, 'lyrics_source_url'> & { lyrics_source_url: string } = {
  version: null,
  original_lyrics: '',
  translation_ko: '',
  pronunciation_ko: '',
  lyrics_source_url: '',
}
const draft = reactive({ ...empty })
const key = ref('')
const saving = ref(false)
const errorMessage = ref('')
const conflicting = ref(false)
const rejectedKey = ref(false)
const { data, error, loading, reload } = useResource(
  (signal) =>
    editing.value && recordingId.value
      ? loadLyricsForEdit(recordingId.value, signal)
      : Promise.resolve(null),
  [() => props.song, readExisting],
)

watch(
  () => props.song,
  () => {
    readExisting.value = false
    Object.assign(draft, empty)
    key.value = ''
    errorMessage.value = ''
    conflicting.value = false
    rejectedKey.value = false
  },
)
watch(data, (value) => {
  if (!value) return
  const { version, original_lyrics, translation_ko, pronunciation_ko, lyrics_source_url } = value
  Object.assign(draft, {
    version,
    original_lyrics,
    translation_ko,
    pronunciation_ko,
    lyrics_source_url: lyrics_source_url ?? '',
  })
})

function refreshLyrics() {
  conflicting.value = false
  errorMessage.value = ''
  if (editing.value) reload()
  else readExisting.value = true
}

async function submit() {
  const song = props.song
  const id = recordingId.value
  if (
    !song ||
    !id ||
    saving.value ||
    conflicting.value ||
    !draft.original_lyrics.trim() ||
    !key.value.trim() ||
    (editing.value && draft.version == null)
  )
    return
  saving.value = true
  errorMessage.value = ''
  rejectedKey.value = false
  try {
    const saved = await saveLyrics(id, { ...draft }, key.value.trim())
    if (props.song === song) emit('saved', song, saved)
  } catch (err) {
    if (props.song !== song) return
    conflicting.value = err instanceof ApiError && err.status === 409
    rejectedKey.value = err instanceof ApiError && err.status === 403
    errorMessage.value = err instanceof Error ? err.message : '가사를 저장하지 못했어요.'
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <Dialog
    :open="Boolean(song && recordingId)"
    @update:open="
      (open) => {
        if (!open && !saving) emit('close')
      }
    "
  >
    <DialogContent
      class="max-h-[min(92dvh,54rem)] grid-rows-[auto_minmax(0,1fr)] sm:max-w-2xl"
      :show-close-button="!saving"
    >
      <DialogHeader class="pr-8">
        <DialogTitle>{{ editing ? '가사 수정' : '가사 등록' }}</DialogTitle>
        <DialogDescription>
          {{ song?.title_ko || song?.title }} · {{ song?.artist_name }}
        </DialogDescription>
      </DialogHeader>
      <div class="overflow-y-auto px-1">
        <ResourceState
          v-if="editing && (loading || error)"
          :loading="loading"
          :error="error"
          @retry="reload"
        />
        <form v-else class="flex flex-col gap-5" @submit.prevent="submit">
          <FieldGroup>
            <Field>
              <FieldLabel for="original-lyrics-edit-text">원문 가사</FieldLabel>
              <Textarea
                id="original-lyrics-edit-text"
                v-model="draft.original_lyrics"
                required
                :maxlength="12000"
                rows="6"
                :disabled="saving"
              />
            </Field>
            <FieldDescription>발음과 번역은 원문과 같은 줄에 맞춰 입력해 주세요.</FieldDescription>
            <div class="grid gap-4 sm:grid-cols-2">
              <Field>
                <FieldLabel for="original-lyrics-edit-pronunciation">한글 발음</FieldLabel>
                <Textarea
                  id="original-lyrics-edit-pronunciation"
                  v-model="draft.pronunciation_ko"
                  :maxlength="12000"
                  rows="5"
                  :disabled="saving"
                />
              </Field>
              <Field>
                <FieldLabel for="original-lyrics-edit-translation">한국어 번역</FieldLabel>
                <Textarea
                  id="original-lyrics-edit-translation"
                  v-model="draft.translation_ko"
                  :maxlength="12000"
                  rows="5"
                  :disabled="saving"
                />
              </Field>
            </div>
            <Field>
              <FieldLabel for="original-lyrics-edit-source">출처 URL</FieldLabel>
              <Input
                id="original-lyrics-edit-source"
                v-model="draft.lyrics_source_url"
                type="url"
                :maxlength="2048"
                :disabled="saving"
              />
            </Field>
            <Field :data-invalid="rejectedKey || undefined">
              <FieldLabel for="original-lyrics-edit-key">가사 편집 키</FieldLabel>
              <Input
                id="original-lyrics-edit-key"
                v-model="key"
                type="password"
                autocomplete="off"
                required
                :aria-invalid="rejectedKey"
                :disabled="saving"
              />
            </Field>
          </FieldGroup>
          <p v-if="errorMessage" role="alert" class="text-sm text-destructive">
            {{ errorMessage }}
          </p>
          <DialogFooter>
            <Button type="button" variant="outline" :disabled="saving" @click="emit('close')">
              취소
            </Button>
            <Button v-if="conflicting" type="button" @click="refreshLyrics">
              최신 가사 불러오기
            </Button>
            <Button
              v-else
              type="submit"
              :disabled="
                saving ||
                !draft.original_lyrics.trim() ||
                !key.trim() ||
                (editing && draft.version == null)
              "
            >
              {{ saving ? '저장 중' : editing ? '수정 저장' : '가사 등록' }}
            </Button>
          </DialogFooter>
        </form>
      </div>
    </DialogContent>
  </Dialog>
</template>
