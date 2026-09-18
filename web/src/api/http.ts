export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message)
  }
}

export async function request<T>(path: string, signal?: AbortSignal): Promise<T> {
  let response: Response
  try {
    response = await fetch(path, { signal, headers: { Accept: 'application/json' } })
  } catch (error) {
    if (signal?.aborted) throw error
    throw new ApiError(0, 'API 서버에 연결하지 못했어요. 서버 실행과 연결 주소를 확인해 주세요.')
  }
  if (!response.ok) {
    const messages: Record<number, string> = {
      401: 'API 인증이 필요합니다. 서버 연결 설정을 확인해 주세요.',
      403: '이 콘텐츠를 조회할 권한이 없습니다.',
      404: '찾으시는 콘텐츠가 없어요.',
      409: '아직 Spotify 아티스트가 연결되지 않았습니다.',
      502: '서버 또는 외부 콘텐츠 서비스에 연결하지 못했어요.',
      503: '콘텐츠 서비스를 사용할 수 없어요. 잠시 후 다시 시도해 주세요.',
    }
    throw new ApiError(
      response.status,
      messages[response.status] ?? '데이터를 불러오지 못했어요. 다시 시도해 주세요.',
    )
  }
  if (!response.headers.get('content-type')?.includes('application/json'))
    throw new ApiError(502, 'API 응답 형식이 올바르지 않습니다. 서버 연결 주소를 확인해 주세요.')
  return response.json() as Promise<T>
}
