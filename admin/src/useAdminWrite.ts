import { ref } from 'vue'
import { ApiError, requestData } from '@papr/shared/api'
import type { CsrfToken } from '@papr/shared/contracts'

export function useAdminWrite(token: string) {
  const csrf = ref(token)
  return async function send<T>(path: string, body: object, method: 'POST' | 'PATCH' | 'PUT' = 'POST', lock?: number, idempotencyKey?: string): Promise<T> {
    const execute = () => requestData<T>(path, { body, method, csrf: csrf.value, idempotencyKey, ...(lock ? { ifMatch: `"${lock}"` } : {}) })
    try { return await execute() } catch (cause) {
      if (!(cause instanceof ApiError) || cause.code !== 'CSRF_INVALID') throw cause
      csrf.value = (await requestData<CsrfToken>('/admin/api/v1/session/csrf', { body: {} })).csrf_token
      return execute()
    }
  }
}
