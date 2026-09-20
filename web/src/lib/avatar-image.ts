// Choose a real stored variant for the rendered box and device pixel density.
export function avatarImageSource(
  original: string,
  variants: Record<string, string> | undefined,
  cssSize: number,
  pixelRatio: number,
) {
  const sizes = Object.keys(variants ?? {})
    .map(Number)
    .filter((s) => Number.isFinite(s) && s > 0 && variants?.[String(s)])
    .sort((a, b) => a - b)
  if (!sizes.length) return original
  const target = Math.max(1, cssSize) * Math.max(1, pixelRatio)
  const size = sizes.find((s) => s >= target) ?? sizes[sizes.length - 1]!
  return variants![String(size)]!
}
