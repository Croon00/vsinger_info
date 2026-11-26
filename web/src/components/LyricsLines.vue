<script setup lang="ts">
import { computed, ref } from 'vue'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import type { Lyrics } from '@/api/types'

// Original lyrics line by line, with translation and pronunciation when they exist.
const props = defineProps<{ lyrics: Lyrics }>()
const visible = ref<string[]>(['original', 'pronunciation', 'translation'])
const lines = computed(() => props.lyrics.original_lyrics.split('\n'))
const translation = computed(() => props.lyrics.translation_ko.split('\n'))
const pronunciation = computed(() => props.lyrics.pronunciation_ko.split('\n'))
const hasTranslation = computed(() => !!props.lyrics.translation_ko.trim())
const hasPronunciation = computed(() => !!props.lyrics.pronunciation_ko.trim())
const shows = (kind: string) =>
  kind === 'original'
    ? visible.value.includes('original') || !(hasTranslation.value || hasPronunciation.value)
    : visible.value.includes(kind)
</script>

<template>
  <div v-if="hasTranslation || hasPronunciation" class="lyrics-toolbar">
    <ToggleGroup type="multiple" v-model="visible" variant="outline" aria-label="가사 표시 언어">
      <ToggleGroupItem value="original">원문</ToggleGroupItem>
      <ToggleGroupItem v-if="hasTranslation" value="translation">번역</ToggleGroupItem>
      <ToggleGroupItem v-if="hasPronunciation" value="pronunciation">발음</ToggleGroupItem>
    </ToggleGroup>
  </div>
  <div
    class="lyric-stanzas"
    :class="{ 'lyric-stanzas-annotated': hasTranslation || hasPronunciation }"
  >
    <div
      v-for="(line, i) in lines"
      :key="i"
      class="lyric-line"
      :class="{ 'lyric-gap': !line.trim() }"
    >
      <p v-if="shows('original')" lang="ja">{{ line }}</p>
      <p v-if="hasPronunciation && shows('pronunciation')" class="lyric-pronunciation">
        {{ pronunciation[i]?.trim() ? `(${pronunciation[i]!.trim()})` : '' }}
      </p>
      <p v-if="hasTranslation && shows('translation')" class="lyric-translation">
        {{ translation[i] }}
      </p>
    </div>
    <p v-if="(hasTranslation || hasPronunciation) && !visible.length" class="text-muted-foreground">
      표시할 언어를 선택해 주세요.
    </p>
  </div>
</template>
