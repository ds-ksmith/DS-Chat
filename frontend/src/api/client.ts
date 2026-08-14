export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

// Thrown when fetch() itself fails (e.g. offline with no cache entry for this
// request) -- distinct from ApiError, which means the server was reachable
// and responded with an error status. Callers use this to show a quiet
// "not available offline" state instead of a real-error message.
export class NetworkError extends Error {
  constructor() {
    super('Network unreachable')
  }
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(path, {
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      ...init,
    })
  } catch {
    throw new NetworkError()
  }

  if (!response.ok) {
    let detail = response.statusText
    try {
      const body = await response.json()
      detail = body.detail ?? detail
    } catch {
      // response had no JSON body
    }
    throw new ApiError(response.status, detail)
  }

  if (response.status === 204) {
    return undefined as T
  }

  return (await response.json()) as T
}
