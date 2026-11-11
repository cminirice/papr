import test from 'node:test'
import assert from 'node:assert/strict'
import { formatBeijingTime } from '../src/time.mjs'

test('跨北京时间午夜，并忽略宿主时区', () => {
  const previous = process.env.TZ
  try {
    for (const zone of ['UTC', 'America/Los_Angeles', 'Asia/Tokyo']) {
      process.env.TZ = zone
      assert.equal(formatBeijingTime('2026-10-27T15:59:59Z'), '2026-10-27 23:59:59')
      assert.equal(formatBeijingTime('2026-10-27T16:00:00Z'), '2026-10-28 00:00:00')
      assert.equal(formatBeijingTime('2026-10-28T00:00:00.123456+08:00'), '2026-10-28 00:00:00')
    }
  } finally {
    if (previous === undefined) delete process.env.TZ
    else process.env.TZ = previous
  }
})
test('拒绝无时区或无效输入', () => {
  assert.throws(() => formatBeijingTime('2026-10-27T08:00:00'))
  assert.throws(() => formatBeijingTime('badTdateZ'))
})
