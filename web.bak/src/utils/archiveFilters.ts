export function inMonthRange(date: string | null, start: string, end: string): boolean {
  if (!start && !end) return true
  if (!date || (start && end && start > end)) return false
  const value = new Date(date)
  if (Number.isNaN(value.getTime())) return false
  const parts = new Intl.DateTimeFormat('en-US', { timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit' }).formatToParts(value)
  const month = `${parts.find(p => p.type === 'year')?.value}-${parts.find(p => p.type === 'month')?.value}`
  return (!start || month >= start) && (!end || month <= end)
}

export function searchKey(value: string): string {
  return value.normalize('NFKC').toLocaleLowerCase().replace(/[\p{P}\p{S}\p{Z}\p{Cf}]/gu, '')
}
