<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { loadYouTube, type YouTubePlayer } from '@/lib/youtube'
import { Button } from '@/components/ui/button'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
const props = defineProps<{ videoId: string; audible: boolean }>()
const host = ref<HTMLElement>()
const error = ref('')
let player: YouTubePlayer | undefined
let generation = 0
let ready = false
let timeout: ReturnType<typeof setTimeout> | undefined
function dispose() {
  generation++
  ready = false
  clearTimeout(timeout)
  try {
    player?.destroy()
  } catch {
    /* Player already detached. */
  }
  player = undefined
}
function syncAudio() {
  if (!player || !ready) return
  if (props.audible) player.unMute()
  else player.mute()
}
async function setup() {
  dispose()
  error.value = ''
  const current = generation
  await nextTick()
  try {
    const yt = await loadYouTube()
    if (current !== generation || !host.value) return
    const target = document.createElement('div')
    host.value.replaceChildren(target)
    timeout = setTimeout(() => {
      if (current === generation) error.value = '플레이어 연결이 지연되고 있어요.'
    }, 15000)
    player = new yt.Player(target, {
      videoId: props.videoId,
      width: '100%',
      height: '100%',
      playerVars: { autoplay: 1, mute: 1, playsinline: 1, rel: 0, origin: window.location.origin },
      events: {
        onReady() {
          if (current !== generation) return
          clearTimeout(timeout)
          error.value = ''
          ready = true
          syncAudio()
        },
        onAutoplayBlocked() {
          if (current !== generation) return
          // Leave the native play control available for a user gesture.
          player?.mute()
        },
        onError() {
          if (current !== generation) return
          clearTimeout(timeout)
          error.value = '방송이 종료되었거나 외부 재생이 제한된 영상일 수 있어요.'
        },
      },
    })
  } catch (e) {
    if (current === generation) error.value = e instanceof Error ? e.message : '재생하지 못했어요.'
  }
}
onMounted(setup)
watch(() => props.videoId, setup)
watch(() => props.audible, syncAudio)
onBeforeUnmount(dispose)
</script>
<template>
  <div class="stream-player">
    <div ref="host" class="stream-player-host" />
    <Alert v-if="error" class="stream-player-error">
      <AlertTitle>영상을 확인해 주세요</AlertTitle>
      <AlertDescription>{{ error }}</AlertDescription>
      <div class="mt-3 flex flex-wrap gap-2">
        <Button size="sm" variant="outline" @click="setup">다시 시도</Button>
        <Button size="sm" as-child>
          <a
            :href="`https://www.youtube.com/watch?v=${videoId}`"
            target="_blank"
            rel="noopener noreferrer"
          >
            YouTube에서 열기
          </a>
        </Button>
      </div>
    </Alert>
  </div>
</template>
