export interface YouTubePlayer {
  playVideo(): void
  mute(): void
  seekTo(seconds: number, allowSeekAhead: boolean): void
  getCurrentTime(): number
  getDuration(): number
  getPlayerState(): number
  destroy(): void
}
interface YouTubeAPI {
  Player: new (
    target: HTMLElement,
    options: {
      videoId: string
      width: string
      height: string
      playerVars: Record<string, string | number>
      events: {
        onReady: () => void
        onError: (event: { data: number }) => void
        onAutoplayBlocked?: () => void
      }
    },
  ) => YouTubePlayer
}
declare global {
  interface Window {
    YT?: YouTubeAPI
    onYouTubeIframeAPIReady?: () => void
  }
}
let pending: Promise<YouTubeAPI> | undefined
export function loadYouTube(): Promise<YouTubeAPI> {
  if (window.YT?.Player) return Promise.resolve(window.YT)
  if (pending) return pending
  pending = new Promise((resolve, reject) => {
    const prior = window.onYouTubeIframeAPIReady
    const timeout = window.setTimeout(() => {
      pending = undefined
      script.remove()
      reject(new Error('YouTube 로딩이 지연되고 있어요.'))
    }, 15000)
    window.onYouTubeIframeAPIReady = () => {
      clearTimeout(timeout)
      prior?.()
      if (window.YT) resolve(window.YT)
    }
    const script = document.createElement('script')
    script.src = 'https://www.youtube.com/iframe_api'
    script.onerror = () => {
      clearTimeout(timeout)
      pending = undefined
      script.remove()
      reject(new Error('YouTube에 연결하지 못했어요.'))
    }
    document.head.append(script)
  })
  return pending
}
export function clampTime(value: unknown, duration: number) {
  const time = Number(value)
  return Number.isFinite(time)
    ? Math.max(0, Math.min(Math.floor(time), Math.max(0, duration - 1)))
    : 0
}
