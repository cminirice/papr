import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import ts from 'typescript'

const source = await readFile(new URL('../src/api.ts', import.meta.url), 'utf8')
const compiled = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText
const { requestData, ApiError } = await import('data:text/javascript;base64,' + Buffer.from(compiled).toString('base64'))

test('写请求携带同源Cookie和CSRF，204不解析JSON', async t => {
  let called
  t.mock.method(globalThis, 'fetch', async (path, options) => {
    called = { path, options }
    return new Response(null, { status: 204 })
  })
  await requestData('/admin/api/v1/session/logout', { body: {}, csrf: 'test-token' })
  assert.equal(called.options.method, 'POST')
  assert.equal(called.options.credentials, 'same-origin')
  assert.equal(called.options.cache, 'no-store')
  assert.equal(called.options.headers['X-CSRF-Token'], 'test-token')
  assert.equal(called.options.headers['Content-Type'], 'application/json')
  assert.equal(called.options.body, '{}')
})

test('只读会话请求不发送body或CSRF，返回data', async t => {
  t.mock.method(globalThis, 'fetch', async (_, options) => {
    assert.equal(options.method, 'GET')
    assert.equal(options.body, undefined)
    assert.equal(options.headers['X-CSRF-Token'], undefined)
    return Response.json({ data: { user_id: 'example' }, request_id: 'request' })
  })
  assert.deepEqual(await requestData('/api/v1/session'), { user_id: 'example' })
})

test('错误码供单次CSRF重试使用，非JSON异常使用通用提示', async t => {
  let count = 0
  t.mock.method(globalThis, 'fetch', async () => {
    count += 1
    return count === 1
      ? Response.json({ error: { code: 'CSRF_INVALID', message: '请刷新' } }, { status: 403 })
      : new Response('upstream internal details', { status: 503 })
  })
  await assert.rejects(requestData('/api/v1/session'), error => error instanceof ApiError && error.code === 'CSRF_INVALID' && error.status === 403)
  await assert.rejects(requestData('/api/v1/session'), error => error.code === 'INTERNAL_ERROR' && !error.message.includes('upstream'))
  assert.equal(count, 2)
})

test('草稿PATCH保留If-Match，冲突不自动重试', async t => {
  let count = 0
  t.mock.method(globalThis, 'fetch', async (_, options) => {
    count++
    assert.equal(options.method, 'PATCH')
    assert.equal(options.headers['If-Match'], '"7"')
    assert.equal(options.headers['X-CSRF-Token'], 'csrf')
    return Response.json({ error: { code: 'EDIT_CONFLICT', message: '请重新加载' } }, { status: 409 })
  })
  await assert.rejects(requestData('/admin/api/v1/template-versions/example', {
    method: 'PATCH', ifMatch: '"7"', csrf: 'csrf', body: { profiles: [] },
  }), error => error instanceof ApiError && error.code === 'EDIT_CONFLICT')
  assert.equal(count, 1)
})

test('验证请求携带调用者持有的幂等key', async t => {
  t.mock.method(globalThis, 'fetch', async (_, options) => {
    assert.equal(options.headers['Idempotency-Key'], 'stable-request-key')
    assert.equal(options.method, 'POST')
    return Response.json({ data: { status: 'queued' } }, { status: 202 })
  })
  assert.deepEqual(await requestData('/admin/api/v1/template-versions/example/validation-jobs', {
    body: { lock_version: 1 }, csrf: 'csrf', idempotencyKey: 'stable-request-key',
  }), { status: 'queued' })
})
