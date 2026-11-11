import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { chromium } from 'playwright-core'
const [executablePath, web, admin, output] = process.argv.slice(2)
const kind = process.env.PAPR_TEST_PRODUCT_TYPE ?? 'fill'
const task = process.env.PAPR_TEST_PRODUCT_TASK ?? 'product'
const title = kind === 'choice' ? '选择题' : kind === 'answer' ? '解答题' : '填空题'
const browser = await chromium.launch({ executablePath, headless: true })
try {
  for (const difficulty of (task !== 'product' ? ['challenge'] : ['basic', 'standard'])) {
    const context = await browser.newContext({ acceptDownloads: true })
    const page = await context.newPage()
    const errors = []
    page.on('pageerror', e => errors.push(e.message))
    await page.goto(web)
    await page.getByLabel(/^目录/).selectOption({ index: 1 })
    await page.getByLabel(/^主题/).selectOption({ index: 1 })
    await page.getByRole('checkbox').first().check()
    await page.getByLabel(/^难度/).selectOption(difficulty)
    await page.getByRole('button', { name: '查看可用题量' }).click()
    await page.getByLabel(title, { exact: true }).selectOption('3')
    await page.getByRole('button', { name: '生成练习', exact: true }).click()
    await page.getByRole('button', { name: '打开练习', exact: true }).click({ timeout: 90000 })
    const preview = page.getByRole('region', { name: '试卷预览' })
    await preview.getByRole('heading', { name: '一、' + (kind === 'answer' ? '竖式计算' : title), exact: true }).waitFor()
    assert.equal(await preview.locator('.papr-question').count(), 3)
    assert.equal(await preview.locator('.vertical').count(), task !== 'product' ? 3 : 0)
    assert.equal(await preview.locator('ol').count(), 0)
    if (task === 'missing_digit') assert.match(await preview.locator('.question-heading').first().innerText(), /□/)
    else if (kind === 'fill') assert.match(await preview.locator('.question-heading').first().innerText(), /=（\s*）/)
    else if (kind === 'choice') assert.equal(await preview.locator('.choice-options li').count(), 12)
    await preview.getByLabel('显示答案与解析').check()
    assert.equal(await preview.locator('.vertical').count(), ['error_choice', 'correction'].includes(task) ? 6 : 3)
    assert.equal(await preview.locator('ol').count(), 3)
    if (task === 'missing_digit') assert.ok(!(await preview.locator('.question-heading').first().innerText()).includes('□'))
    else if (kind === 'fill') assert.match(await preview.locator('.question-heading').first().innerText(), /=（\d+）/)
    else if (kind === 'choice') assert.match(await preview.innerText(), /答案：[ABCD]，/)
    else assert.match(await preview.innerText(), /答案：\d+/)
    for (const [i, link] of (await preview.getByRole('link', { name: '下载PDF', exact: true }).all()).entries()) {
      const waiting = page.waitForEvent('download')
      await link.click()
      const download = await waiting
      const path = `${output}/${kind}-${difficulty}-${i}.pdf`
      await download.saveAs(path)
      assert.equal((await readFile(path)).subarray(0, 5).toString(), '%PDF-')
    }
    await preview.getByRole('button', { name: '沿用配置再练一份' }).click()
    await page.getByText('已沿用原目录、知识点、难度和题量，并检查当前可用性。确认后点击“生成练习”创建新题。', { exact: true }).waitFor()
    assert.equal(await page.getByLabel(title, { exact: true }).inputValue(), '3')
    await page.screenshot({ path: `${output}/${kind}-${difficulty}.png`, fullPage: true })
    assert.deepEqual(errors, [])
    await context.close()
  }
  console.log(JSON.stringify({ status: kind + '_browser_passed', task, difficulties: task !== 'product' ? ['challenge'] : ['basic', 'standard'], actual_pdf_pairs: task !== 'product' ? 1 : 2 }))
} finally { await browser.close() }
