import type { Artist, CalendarEvent, Concert } from '@/api/types'

export const SEOUL = 'Asia/Seoul'
export function dateKey(date: Date): string {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: SEOUL,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(date)
}
export function todayKey() {
  return dateKey(new Date())
}
export function dayDate(key: string) {
  return new Date(`${key}T12:00:00+09:00`)
}
export function monthKey(input: unknown): string {
  const value = typeof input === 'string' ? input : ''
  if (/^\d{4}-(0[1-9]|1[0-2])-01$/.test(value) && Number(value.slice(0, 4)) > 0) return value
  return `${todayKey().slice(0, 7)}-01`
}
export function addDays(key: string, count: number) {
  return dateKey(new Date(dayDate(key).getTime() + count * 86400000))
}
export function changeMonth(key: string, amount: number) {
  const [year, month] = key.split('-').map(Number)
  const d = new Date(Date.UTC(year, month - 1 + amount, 1, 3))
  return dateKey(d)
}
export function calendarDays(month: string) {
  const day = dayDate(month).getUTCDay()
  const start = addDays(month, -((day + 6) % 7))
  return Array.from({ length: 42 }, (_, i) => addDays(start, i))
}
export function formatDate(value: string, options: Intl.DateTimeFormatOptions = {}) {
  return new Intl.DateTimeFormat('ko-KR', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    timeZone: SEOUL,
    ...options,
  }).format(value.length === 10 ? dayDate(value) : new Date(value))
}
export function formatTime(seconds: number) {
  const value = Math.max(0, Math.floor(seconds))
  const mins = Math.floor(value / 60)
  return `${mins >= 60 ? `${Math.floor(mins / 60)}:` : ''}${String(mins % 60).padStart(2, '0')}:${String(value % 60).padStart(2, '0')}`
}
export function calendarEvents(
  artists: Artist[],
  concerts: Concert[],
  year: number,
): CalendarEvent[] {
  const events: CalendarEvent[] = concerts
    .filter((c) => c.event_format !== 'online')
    .map((c) => ({
      id: `concert-${c.id}`,
      artist_id: c.artist_id,
      title: c.title,
      date: dateKey(new Date(c.starts_at)),
      kind: 'concert',
      concert: c,
    }))
  for (const artist of artists) {
    if (!artist.birthday) continue
    const date = `${year}-${artist.birthday}`
    if (dateKey(dayDate(date)) !== date) continue // February 29 only occurs in leap years.
    events.push({
      id: `birthday-${artist.id}`,
      artist_id: artist.id,
      title: `${artist.name} 생일`,
      date,
      kind: 'birthday',
    })
  }
  // Official member birthdays belong to the individual, not the whole group.
  const members = [
    { artist_id: 5, person: 'YOMI', date: '07-05' },
    { artist_id: 5, person: 'KASUKA', date: '09-09' },
    { artist_id: 11, person: 'LITA', date: '01-11' },
    { artist_id: 11, person: 'TINA', date: '11-07' },
    { artist_id: 11, person: 'NERO', date: '08-25' },
  ]
  for (const member of members) {
    if (!artists.some((a) => a.id === member.artist_id)) continue
    events.push({
      id: `birthday-${member.person}`,
      artist_id: member.artist_id,
      title: `${member.person} 생일`,
      date: `${year}-${member.date}`,
      kind: 'birthday',
      person: member.person,
    })
  }
  return events.sort((a, b) => a.date.localeCompare(b.date))
}
