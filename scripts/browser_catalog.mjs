import assert from 'node:assert/strict'
import { writeFile } from 'node:fs/promises'
import { chromium } from 'playwright-core'
const [executablePath, , admin, output] = process.argv.slice(2)
const browser = await chromium.launch({ executablePath, headless: true })
try {
  const page = await browser.newPage()
  const errors = []
  const responses = []
  page.on('response', response => {
    const path = new URL(response.url()).pathname
    if (/^\/admin\/api\/v1\/(catalogs|catalog-nodes|knowledge-revision-options)(\/|$)/.test(path)) {
      responses.push(response.json().then(body => ({ path, status: response.status(), body }))
        .catch(() => ({ path, status: response.status() })))
    }
  })
  page.on('pageerror', error => errors.push(error.message))
  await page.goto(admin)
  await page.getByLabel('用户名', { exact: true }).fill('owner')
  await page.getByLabel('密码', { exact: true }).fill('test-only-admin-password')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await page.getByRole('button', { name: '新建目录', exact: true }).click()
  const editor = page.getByRole('region', { name: '目录与节点维护', exact: true })
  await editor.getByLabel('变更理由', { exact: true }).fill('浏览器隔离数据目录维护验收')
  await editor.getByLabel('目录编码', { exact: true }).fill('BROWSER_CATALOG')
  await editor.getByLabel('目录名称', { exact: true }).fill('浏览器测试目录')
  await editor.getByRole('button', { name: '保存目录', exact: true }).click()
  await editor.getByText('目录已保存。新目录保持草稿，开放状态请到开放设置维护。', { exact: true }).waitFor()
  await editor.getByLabel('节点编码', { exact: true }).fill('ROOT')
  await editor.getByLabel('节点名称', { exact: true }).fill('根主题')
  await editor.getByRole('button', { name: '保存节点', exact: true }).click()
  await editor.getByText('节点已保存。新节点保持草稿。', { exact: true }).waitFor()
  // Capture the failing step without changing its locator or timing.
  await page.screenshot({ path: output + '/catalog-before-revision.png', fullPage: true })
  await writeFile(output + '/catalog-before-revision.html', await editor.innerHTML())
  await writeFile(output + '/catalog-before-revision-aria.txt', await editor.ariaSnapshot())
  const diagnostic = {
    responses: await Promise.all(responses),
    exact_label_matches: await editor.getByLabel('选择知识点修订', { exact: true }).count(),
    prefix_label_matches: await editor.getByLabel(/^选择知识点修订/).count(),
    selects: await editor.locator('select').evaluateAll(elements => elements.map(select => ({
      label: [...select.labels].map(label => label.textContent.trim()),
      visible: select.getClientRects().length > 0,
      disabled: select.matches(':disabled'),
      options: [...select.options].map(option => ({ value: option.value, text: option.text })),
    }))),
    page_errors: errors,
  }
  await writeFile(output + '/catalog-before-revision.json', JSON.stringify(diagnostic, null, 2))
  await editor.getByLabel('选择知识点修订', { exact: true }).selectOption({ index: 1 })
  await editor.getByRole('button', { name: '添加映射', exact: true }).click()
  await editor.getByRole('button', { name: '保存知识点映射', exact: true }).click()
  await editor.getByText('知识点映射已保存，公开能力已更新。草稿修订不会因此发布。', { exact: true }).waitFor()
  await editor.getByRole('button', { name: '新建节点', exact: true }).click()
  await editor.getByLabel('节点编码', { exact: true }).fill('CHILD')
  await editor.getByLabel('节点名称', { exact: true }).fill('子分组')
  await editor.getByLabel('节点类型', { exact: true }).selectOption('group')
  await editor.getByLabel('父节点', { exact: true }).selectOption({ label: '根主题' })
  await editor.getByRole('button', { name: '保存节点', exact: true }).click()
  await editor.getByText('节点已保存。新节点保持草稿。', { exact: true }).waitFor()
  await editor.getByRole('button', { name: '编辑根主题', exact: true }).click()
  await editor.getByRole('button', { name: '移除映射', exact: true }).waitFor()
  await editor.getByLabel('父节点', { exact: true }).selectOption({ label: '子分组' })
  const rejected = page.waitForResponse(r => r.request().method() === 'PATCH' && r.url().includes('/catalog-nodes/'))
  await editor.getByRole('button', { name: '保存节点', exact: true }).click()
  assert.equal((await rejected).status(), 409)
  await editor.getByRole('alert').filter({ hasText: '节点不能作为自己的祖先' }).waitFor()
  await editor.getByRole('button', { name: '重新加载目录（放弃未保存修改）', exact: true }).click()
  await editor.getByRole('button', { name: '编辑根主题', exact: true }).click()
  await editor.getByRole('button', { name: '移除映射', exact: true }).waitFor()
  assert.equal(await editor.getByLabel('父节点', { exact: true }).inputValue(), '')
  await editor.getByRole('button', { name: '移除映射', exact: true }).click()
  await editor.getByRole('button', { name: '保存知识点映射', exact: true }).click()
  await editor.getByText('知识点映射已保存，公开能力已更新。草稿修订不会因此发布。', { exact: true }).waitFor()
  assert.equal(await editor.getByRole('button', { name: '移除映射', exact: true }).count(), 0)
  await page.screenshot({ path: output + '/catalog-editor.png', fullPage: true })
  assert.deepEqual(errors, [])
  console.log(JSON.stringify({ status: 'catalog_editor_passed', cycle_rejected: true, mappings_saved: true }))
} finally {
  await browser.close()
}
