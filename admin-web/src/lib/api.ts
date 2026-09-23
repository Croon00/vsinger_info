export type Data = Record<string, any>
export type Resource = {
  name: string
  title: string
  fields: FieldSpec[]
  versioned: boolean
  archivable: boolean
}
export type FieldSpec = {
  name: string
  type: string
  nullable: boolean
  description: string
  example?: string
  default?: any
  options?: string[]
  reference?: string
}
let csrf = ''
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message)
  }
}
export async function initSession() {
  const response = await fetch('/api/admin/session', {
    credentials: 'same-origin',
  })
  if (!response.ok) throw new Error('관리자 API를 연결할 수 없습니다.')
  csrf = (await response.json()).csrf
}
export async function api<T = Data>(
  path: string,
  method = 'GET',
  body?: unknown,
): Promise<T> {
  const response = await fetch('/api/admin' + path, {
    method,
    credentials: 'same-origin',
    headers: {
      'Content-Type': 'application/json',
      ...(method === 'GET' ? {} : { 'X-CSRF-Token': csrf }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const result = await response
    .json()
    .catch(() => ({
      detail: '응답을 읽지 못했습니다. 결과 확인 후 같은 작업을 재시도하세요.',
    }))
  if (!response.ok)
    throw new ApiError(
      typeof result.detail === 'string'
        ? result.detail
        : '입력 형식을 확인하세요.',
      response.status,
    )
  return result as T
}
export async function download(path: string, filename: string) {
  const response = await fetch('/api/admin' + path, {
    credentials: 'same-origin',
  })
  if (!response.ok) {
    const r = await response.json()
    throw new Error(r.detail)
  }
  const url = URL.createObjectURL(await response.blob())
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
export function titleOf(row: Data): string {
  const d = row.current_payload || row
  return (
    d._label ||
    d.name_native ||
    d.title_native ||
    d.title ||
    d.alias ||
    d.label ||
    d.handle ||
    d.raw_title ||
    d.url ||
    row.client_ref ||
    '#' + row.id
  )
}
export const statuses: Record<string, string> = {
  pending: '검수 대기',
  editing: '수정 중',
  approved: '승인',
  held: '보류',
  excluded: '제외',
  blocked: '오류',
  published: '반영 완료',
  reviewing: '검수 중',
  frozen: '반영 준비',
  ready: '반영 준비',
  publishing: '결과 확인 필요',
  committed: '반영 완료',
  invalidated: '계획 만료',
}
export const families = [
  {
    title: '아티스트',
    name: 'artists',
    types: [
      'artists',
      'artist_aliases',
      'agencies',
      'artist_group_members',
      'external_accounts',
      'artist_external_accounts',
    ],
  },
  {
    title: '곡',
    name: 'songs',
    types: ['songs', 'song_artists', 'karaoke_numbers'],
  },
  {
    title: '라이브 · 세트리스트',
    name: 'live_archives',
    types: [
      'live_archives',
      'videos',
      'archive_artists',
      'performances',
      'performance_artists',
      'source_documents',
      'archive_sources',
    ],
  },
  {
    title: '공연',
    name: 'concerts',
    types: ['concerts', 'concert_artists', 'concert_ticket_windows'],
  },
  {
    title: '앨범 · 음원',
    name: 'albums',
    types: [
      'albums',
      'album_artists',
      'recordings',
      'recording_artists',
      'recording_external_ids',
      'album_tracks',
      'recording_lyrics',
    ],
  },
  { title: '커버', name: 'covers', types: ['covers', 'cover_artists'] },
]
export const labels: Record<string, string> = {
  slug: '주소용 이름',
  name_native: '원어 이름',
  name_ko: '한국어 이름',
  name_latin: '영문 이름',
  entity_kind: '활동 형태',
  is_virtual: '버추얼 아티스트',
  agency_id: '소속사',
  birthday_month: '생일 · 월',
  birthday_day: '생일 · 일',
  debut_date: '데뷔일',
  bio: '소개',
  theme_color: '상징색',
  avatar_url: '프로필 이미지 주소',
  show_in_catalog: '탐색에 표시',
  artist_id: '아티스트',
  alias: '검색용 다른 이름',
  website_url: '공식 사이트',
  group_id: '그룹',
  member_id: '멤버',
  joined_on: '가입일',
  left_on: '탈퇴일',
  platform: '플랫폼',
  platform_id: '플랫폼 고유 ID',
  handle: '계정 이름',
  url: '주소',
  collection_enabled: '수집 대상',
  account_id: '외부 계정',
  relationship: '계정 관계',
  is_primary: '대표 계정',
  label: '표시 이름',
  position: '표시 순서',
  title_native: '원어 제목',
  title_ko: '한국어 제목',
  title_latin: '로마자 제목',
  language_code: '언어 코드',
  song_id: '곡',
  provider: '노래방 업체',
  number: '노래방 번호',
  source_url: '출처 주소',
  platform_video_id: 'YouTube 영상 ID',
  source_account_id: '업로드 계정',
  title: '제목',
  published_at: '업로드 시각',
  duration_seconds: '영상 길이 · 초',
  availability: '공개 상태',
  video_id: '영상',
  primary_artist_id: '대표 아티스트',
  broadcast_at: '방송 시각',
  setlist_state: '세트리스트 상태',
  archive_id: '라이브 아카이브',
  role: '역할',
  source_kind: '출처 종류',
  external_id: '외부 고유 ID',
  captured_at: '원문 확인 시각',
  content_text: '원문',
  source_metadata: '출처 메타데이터',
  document_id: '출처 문서',
  ordinal: '세트리스트 순번',
  start_seconds: '시작 시점 · 초',
  end_seconds: '종료 시점 · 초',
  raw_title: '원문 곡명',
  raw_artist: '원문 아티스트',
  raw_timestamp: '원문 타임스탬프',
  source_document_id: '근거 문서',
  performance_id: '가창 기록',
  event_format: '공연 형태',
  event_date: '공연 날짜',
  starts_at: '시작 시각',
  ends_at: '종료 시각',
  timezone_name: '현지 시간대',
  time_precision: '날짜 확정 수준',
  city: '도시',
  venue: '공연장',
  status: '공연 상태',
  concert_id: '공연',
  opens_at: '예매 시작',
  closes_at: '예매 종료',
  price_text: '가격 안내',
  album_type: '앨범 종류',
  release_year: '발매 연도',
  release_month: '발매 월',
  release_day: '발매 일',
  cover_image_url: '앨범 이미지 주소',
  spotify_album_id: 'Spotify 앨범 ID',
  album_id: '앨범',
  version_label: '버전 이름',
  duration_ms: '음원 길이 · 밀리초',
  official_video_id: '공식 영상',
  recording_id: '음원',
  disc_number: '디스크 번호',
  track_number: '트랙 번호',
  original_lyrics: '원문 가사',
  translation_ko: '한국어 번역',
  pronunciation_ko: '한국어 독음',
  cover_id: '커버 영상',
}
export const optionLabels: Record<string, string> = {
  owner: '본인 계정',
  member: '그룹 멤버',
  host: '주 출연',
  primary: '주 가창',
  featured: '피처링',
  vocal: '가창',
  compilation: '컴필레이션',
  other: '기타',
  solo: '개인',
  group: '그룹',
  onsite: '오프라인',
  online: '온라인',
  hybrid: '온·오프라인',
  unknown: '미정',
  date: '날짜만 확정',
  datetime: '시각까지 확정',
  scheduled: '예정',
  cancelled: '취소',
  postponed: '연기',
  completed: '완료',
  lead: '주 가창',
  guest: '게스트',
  unprocessed: '미정리',
  partial: '일부 정리',
  complete: '정리 완료',
  unavailable: '확보 불가',
  public: '공개',
  private: '비공개',
  deleted: '삭제',
  unlisted: '일부 공개',
  website: '공식 사이트',
  fanclub: '팬클럽',
  single: '싱글',
  ep: 'EP',
  album: '정규 앨범',
  manual_note: '직접 기록',
  youtube_comment: 'YouTube 댓글',
  video_description: '영상 설명',
  announcement: '공지',
  official_page: '공식 페이지',
  setlist_evidence: '세트리스트 근거',
  metadata_evidence: '방송 정보 근거',
  owned: '본인 계정',
  shared: '공동 계정',
  associated: '관련 계정',
}
