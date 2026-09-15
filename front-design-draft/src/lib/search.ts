export function normalize(value: string) {
  return value
    .normalize('NFKC')
    .toLocaleLowerCase()
    .replace(/[\s・·_-]/g, '')
}
