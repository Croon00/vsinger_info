/** 원어 이름 뒤에 한국어 이름을 괄호로 붙인다. 한국어가 없거나 원어와 같으면 원어만 반환한다. */
export function displayName(original: string, korean?: string | null): string {
  const base = original.trim()
  const ko = korean?.trim() ?? ''
  if (!ko || ko === base) return base
  if (!base) return ko
  return `${base} (${ko})`
}
