import { ref, watch } from 'vue'

const prefix = 'schedule-music-draft:'
function read<T>(key: string, fallback: T, validate: (v: unknown) => boolean): T {
  try {
    const value = JSON.parse(localStorage.getItem(prefix + key) ?? 'null')
    return validate(value) ? (value as T) : fallback
  } catch {
    return fallback
  }
}
export const favoriteIds = ref(
  read<number[]>(
    'favorites',
    [1, 2, 3, 4, 5, 6],
    (v) => Array.isArray(v) && v.every(Number.isInteger),
  ),
)
export type Theme = 'system' | 'light' | 'dark'
export const theme = ref(
  read<Theme>('theme', 'system', (v) => ['system', 'light', 'dark'].includes(v as string)),
)
export const calendarScope = ref(
  read<'favorites' | 'all'>('calendar-scope', 'favorites', (v) => v === 'favorites' || v === 'all'),
)
export const statusMessage = ref('')
let announceTimer: ReturnType<typeof setTimeout>
export function announce(message: string) {
  statusMessage.value = message
  clearTimeout(announceTimer)
  announceTimer = setTimeout(() => {
    statusMessage.value = ''
  }, 3000)
}
export function toggleFavorite(id: number, name: string) {
  const exists = favoriteIds.value.includes(id)
  favoriteIds.value = exists
    ? favoriteIds.value.filter((v) => v !== id)
    : [...favoriteIds.value, id]
  announce(`${name} ${exists ? '즐겨찾기를 해제했어요' : '즐겨찾기에 추가했어요'}`)
}
function save(key: string, value: unknown) {
  try {
    localStorage.setItem(prefix + key, JSON.stringify(value))
  } catch {
    announce('저장 공간을 사용할 수 없어 이번 방문 동안만 유지해요.')
  }
}
watch(favoriteIds, (v) => save('favorites', v), { deep: true })
watch(calendarScope, (v) => save('calendar-scope', v))
const media = window.matchMedia('(prefers-color-scheme: dark)')
function applyTheme() {
  const dark = theme.value === 'dark' || (theme.value === 'system' && media.matches)
  document.documentElement.classList.toggle('dark', dark)
  document.documentElement.style.colorScheme = dark ? 'dark' : 'light'
}
watch(theme, (value) => {
  save('theme', value)
  applyTheme()
})
media.addEventListener('change', applyTheme)
applyTheme()
