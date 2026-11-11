import type { ErrorResponse } from './api.generated'

export class ApiError extends Error {
  constructor(public readonly status: number, public readonly code: string, message: string) {
    super(message)
  }
}

export async function requestData<T>(path: string, options: { body?: object; csrf?: string; method?: 'POST' | 'PATCH' | 'PUT'; ifMatch?: string; idempotencyKey?: string } = {}): Promise<T> {
  const response = await fetch(path, {
    method: options.method ?? (options.body === undefined ? 'GET' : 'POST'),
    credentials: 'same-origin',
    cache: 'no-store',
    headers: {
      ...(options.body === undefined ? {} : { 'Content-Type': 'application/json' }),
      ...(options.csrf ? { 'X-CSRF-Token': options.csrf } : {}),
      ...(options.ifMatch ? { 'If-Match': options.ifMatch } : {}),
      ...(options.idempotencyKey ? { 'Idempotency-Key': options.idempotencyKey } : {}),
    },
    ...(options.body === undefined ? {} : { body: JSON.stringify(options.body) }),
  })
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as ErrorResponse | null
    throw new ApiError(response.status, payload?.error?.code ?? 'INTERNAL_ERROR', payload?.error?.message ?? '服务暂时不可用，请稍后重试')
  }
  if (response.status === 204) return undefined as T
  const payload = await response.json() as { data: T }
  return payload.data
}
