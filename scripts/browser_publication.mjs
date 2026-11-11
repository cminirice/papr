// All mutations target the temporary draft-only fixture in test_browser_flow.py.
// Automated review confirmations exercise UI/API rules, not real human approval.
import assert from 'node:assert/strict'
import { chromium } from 'playwright-core'

const [executablePath, , admin, output] = process.argv.slice(2)
const browser = await chromium.launch({ executablePath, headless: true })
const errors = []
try {
  const context = await browser.newContext({ timezoneId: 'America/Los_Angeles' })
  const page = await context.newPage()
  page.on('pageerror', error => errors.push(error.message))
  const clickRequest = async (name, suffix, status = 200) => {
    const pending = page.waitForResponse(r => r.url().endsWith(suffix) && r.request().method() === 'POST')
    await page.getByRole('button', { name, exact: true }).click()
    const response = await pending
    assert.equal(response.status(), status, await response.text())
    return status === 204 ? null : (await response.json()).data
  }
  const openReport = async () => {
    const result = page.locator('.validation-result').filter({ has: page.getByRole('heading', { name: /^通过 ·/ }) })
    await result.getByRole('button', { name: '查看样题与发布' }).first().click({ timeout: 90000 })
    await page.getByText('当前内容最近审题：', { exact: false }).waitFor()
  }
  const reason = async () => page.getByLabel('发布或状态变更理由', { exact: true }).fill('临时测试库的浏览器流程验证，不代表正式审题')
  const approve = async () => {
    const checks = page.getByRole('checkbox', { name: /^已检查样题/ })
    for (let i = 0; i < await checks.count(); i++) await checks.nth(i).check()
    await page.getByRole('checkbox', { name: '已实际检查两种样张的打印排版和答题留白', exact: true }).check()
    await page.getByLabel(/^审题结论/).selectOption('approved')
    await page.getByLabel('审题意见', { exact: true }).fill('测试模拟人工确认：仅验证发布约束，不是正式内容审核。')
    await clickRequest('记录审题结论', '/reviews')
    await page.getByText('当前内容最近审题：通过', { exact: true }).waitFor()
  }
  const validate = async () => {
    await clickRequest('验证已保存草稿', '/validation-jobs', 202)
    await openReport()
  }
  const published = async () => {
    await page.getByText('此版本当前不可编辑。', { exact: true }).waitFor()
    await openReport()
    await reason()
  }
  const current = async (version) => (await (await context.request.get(admin + `/admin/api/v1/template-versions/${version}/release-context`)).json()).data

  await page.goto(admin)
  await page.getByLabel('用户名', { exact: true }).fill('owner')
  await page.getByLabel('密码', { exact: true }).fill('test-only-admin-password')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await page.getByRole('button', { name: '查看配置', exact: true }).first().click()
  const versionSelect = page.getByLabel(/^版本/)
  await versionSelect.waitFor()
  const v1 = await versionSelect.inputValue()
  await validate()
  await reason()
  await page.getByRole('button', { name: '发布当前模板版本' }).click()
  await page.getByRole('alert').filter({ hasText: '须使用此报告对应的最新人工通过记录' }).waitFor()
  assert.equal((await current(v1)).current_published_version_id, null)
  // Incomplete confirmation is rejected by the actual server.
  await page.getByLabel(/^审题结论/).selectOption('approved')
  await page.getByLabel('审题意见', { exact: true }).fill('测试不完整确认应被拒绝')
  await clickRequest('记录审题结论', '/reviews', 422)
  await page.getByLabel(/^审题结论/).selectOption('rejected')
  await page.getByRole('checkbox', { name: /^已检查样题/ }).first().check()
  await page.getByLabel('审题意见', { exact: true }).fill('测试退回：需要重新检查样题')
  await clickRequest('记录审题结论', '/reviews')
  await page.getByText('当前内容最近审题：不通过', { exact: true }).waitFor()
  await page.getByRole('button', { name: '发布当前模板版本' }).click()
  await page.getByRole('alert').filter({ hasText: '须使用此报告对应的最新人工通过记录' }).waitFor()
  await approve()
  // Sample display toggles between student and solution using the shared renderer.
  assert.ok(await page.locator('.review-print ol').count() > 0)
  await page.getByRole('checkbox', { name: '展示解析版样题' }).uncheck()
  assert.equal(await page.locator('.review-print ol').count(), 0)
  assert.match(await page.locator('.review-print .question-row').first().getAttribute('style'), /repeat\(2,/)
  await page.emulateMedia({media:'print'})
  assert.match(await page.locator('.review-print .question-row').first().getAttribute('style'), /repeat\(2,/)
  await page.emulateMedia({media:'screen'})
  await page.getByRole('checkbox', { name: '展示解析版样题' }).check()
  assert.ok(await page.locator('.review-print ol').count() > 0)
  await clickRequest('发布当前模板版本', '/publish', 409) // Prerequisite revisions still drafts.
  let before = await current(v1)
  for (const dependency of before.dependencies.filter(d => d.status === 'draft')) {
    const count = await page.getByRole('button', { name: '确认并发布此修订' }).count()
    const pending = page.waitForResponse(r => r.url().endsWith(`/${dependency.id}/publish`) && r.request().method() === 'POST')
    const article = page.locator('article').filter({ has: page.getByRole('heading', { name: dependency.name + ' · 草稿', exact: true }) })
    await article.getByRole('button', { name: '确认并发布此修订' }).click()
    assert.equal((await pending).status(), 204)
    await page.waitForFunction(n => [...document.querySelectorAll('button')].filter(b => b.textContent.trim() === '确认并发布此修订').length < n, count)
  }
  await clickRequest('发布当前模板版本', '/publish')
  await published()
  assert.equal((await current(v1)).current_published_version_id, v1)
  await clickRequest('停用模板', '/disable')
  await published()
  assert.equal((await current(v1)).template_status, 'disabled')
  await clickRequest('重新启用模板', '/enable')
  await published()
  assert.equal((await current(v1)).template_status, 'active')
  await clickRequest('复制为新草稿', '/versions')
  await page.getByText('已复制为新草稿，需要重新验证和审题。', { exact: true }).waitFor()
  const v2 = await versionSelect.inputValue()
  assert.notEqual(v1, v2)
  await page.getByLabel(/^题目每行题数/).first().selectOption('3')
  await page.getByRole('button', { name: '保存草稿', exact: true }).click()
  await page.getByText('草稿已保存。已有有效题量已清空，后续须重新验证和审题。', { exact: true }).waitFor()
  await validate()
  await reason()
  await approve()
  await clickRequest('发布当前模板版本', '/publish')
  await published()
  assert.equal((await current(v2)).current_published_version_id, v2)
  await versionSelect.selectOption(v1)
  await published()
  await clickRequest('回退到此历史版本', '/rollback')
  await published()
  assert.equal((await current(v1)).current_published_version_id, v1)
  assert.equal(await page.getByLabel(/^题目每行题数/).first().inputValue(), '2')
  await page.screenshot({ path: output + '/publication-rollback.png', fullPage: true })
  await page.getByRole('button', { name: '生成记录与统计', exact: true }).click()
  await page.getByText('此条件下暂无任务。', { exact: true }).waitFor()
  await page.getByLabel(/^任务类型/).selectOption('template_validate')
  await page.getByRole('button', { name: '查询记录与统计', exact: true }).click()
  await page.getByRole('button', { name: '查看任务', exact: true }).first().waitFor()
  assert.equal(await page.getByRole('button', { name: '查看任务', exact: true }).count(), 2)
  await page.getByRole('button', { name: '查看任务', exact: true }).first().click()
  await page.getByRole('heading', { name: '验证结论：通过', exact: true }).waitFor()
  await page.getByRole('button', { name: '查看来源模板版本', exact: true }).click()
  await versionSelect.waitFor()
  assert.ok([v1, v2].includes(await versionSelect.inputValue()))
  assert.deepEqual(errors, [])
  console.log(JSON.stringify({ status: 'publication_flow_passed', versions: 2, validation_worker: 'real_subprocess',
    incomplete_review_rejected: true, rejected_review_blocks_publish: true, prerequisite_required: true,
    published: true, disabled: true, enabled: true, rolled_back: true, validation_records: 2, page_errors: errors }))
} catch (error) {
  console.error(error)
  process.exitCode = 1
} finally {
  await browser.close()
}
