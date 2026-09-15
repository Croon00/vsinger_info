import { onScopeDispose, ref, shallowRef, watch, type WatchSource } from 'vue'

export function useResource<T>(
  loader: (signal: AbortSignal) => Promise<T>,
  dependencies: WatchSource[] = [],
) {
  const data = shallowRef<T | null>(null)
  const loading = ref(true)
  const error = ref('')
  let controller: AbortController | undefined
  let generation = 0
  async function reload() {
    const current = ++generation
    controller?.abort()
    controller = new AbortController()
    loading.value = true
    error.value = ''
    try {
      const value = await loader(controller.signal)
      if (current === generation) data.value = value
    } catch (e) {
      if (current === generation && !controller.signal.aborted)
        error.value = e instanceof Error ? e.message : '데이터를 불러오지 못했어요.'
    } finally {
      if (current === generation) loading.value = false
    }
  }
  watch(dependencies, reload, { immediate: true })
  onScopeDispose(() => {
    generation++
    controller?.abort()
  })
  return { data, loading, error, reload }
}
