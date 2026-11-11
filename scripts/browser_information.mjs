// Static public information remains readable when session requests fail.
import assert from 'node:assert/strict'
import { chromium } from 'playwright-core'
const [executablePath, web, , output] = process.argv.slice(2)
const browser = await chromium.launch({ executablePath, headless: true })
try {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } })
  const page = await context.newPage()
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  await page.route('**/api/v1/**', route => route.abort())
  await page.goto(web + '/#/help')
  const help = page.getByRole('region', { name: '使用说明', exact: true })
  await help.waitFor()
  assert.match(await help.innerText(), /600秒/)
  assert.match(await help.innerText(), /实际纸面排版以PDF为准/)
  await help.getByRole('link', { name: '隐私说明', exact: true }).click()
  const privacy = page.getByRole('region', { name: '隐私说明', exact: true })
  await privacy.waitFor()
  assert.match(await privacy.innerText(), /清除浏览器Cookie不会删除服务端/)
  assert.match(await privacy.innerText(), /正式历史保留期限尚未确定/)
  await page.reload()
  await privacy.waitFor()
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true)
  await page.screenshot({ path: output + '/privacy-mobile.png', fullPage: true })
  await page.goBack()
  await help.waitFor()
  await page.getByRole('navigation', { name: '主导航' }).getByRole('link', { name: '开始练习' }).click()
  await page.getByRole('alert').waitFor()
  await page.getByRole('navigation', { name: '主导航' }).getByRole('link', { name: '使用说明' }).click()
  await help.waitFor()
  assert.deepEqual(errors, [])
  console.log(JSON.stringify({ status: 'information_pages_passed', session_unavailable: true, mobile: true }))
} finally {
  await browser.close()
}
