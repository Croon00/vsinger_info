// Spotify's artist-level genre names; only common market names get a Korean label.
const LABELS: Record<string, string> = {
  'j-pop': 'J-Pop',
  'j-rock': 'J-Rock',
  'j-rap': 'J-Rap',
  'j-r&b': 'J-R&B',
  'k-pop': 'K-Pop',
  anime: '애니송',
  anison: '애니송',
  vocaloid: '보카로',
  'utaite': '우타이테',
  vtuber: 'VTuber',
  'japanese vtuber': 'VTuber',
  'japanese indie': '재패니즈 인디',
  'city pop': '시티팝',
}

/** Display labels in Spotify order; duplicates after labelling (anime/anison) are dropped. */
export function spotifyGenreLabels(genres?: string[] | null): string[] {
  const labels = (genres ?? []).map((genre) => {
    const key = genre.trim().toLowerCase()
    return LABELS[key] ?? key.replace(/(^|[\s-])([a-z])/g, (_, gap: string, c: string) => gap + c.toUpperCase())
  })
  return [...new Set(labels.filter(Boolean))]
}
