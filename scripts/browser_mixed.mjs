import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { chromium } from 'playwright-core'
const [executablePath,web,,output]=process.argv.slice(2)
const browser=await chromium.launch({executablePath,headless:true})
try {
  const context=await browser.newContext({acceptDownloads:true})
  const page=await context.newPage()
  const errors=[];page.on('pageerror',e=>errors.push(e.message))
  await page.goto(web)
  await page.getByLabel(/^目录/).selectOption({index:1})
  await page.getByLabel(/^主题/).selectOption({index:1})
  await page.getByRole('checkbox').nth(1).waitFor()
  assert.equal(await page.getByRole('checkbox').count(),2)
  for(const checkbox of await page.getByRole('checkbox').all()) await checkbox.check()
  await page.getByLabel(/^难度/).selectOption('standard')
  await page.getByRole('button',{name:'查看可用题量'}).click()
  for(const title of ['选择题','填空题','解答题']) await page.getByLabel(title,{exact:true}).selectOption('3')
  await page.getByText('整卷共 9 题。',{exact:true}).waitFor()
  await page.getByRole('button',{name:'生成练习',exact:true}).click()
  await page.getByRole('button',{name:'打开练习',exact:true}).click({timeout:90000})
  const preview=page.getByRole('region',{name:'试卷预览'})
  await preview.getByRole('heading',{name:'一、选择题',exact:true}).waitFor()
  assert.deepEqual(await preview.locator('.question-section-title').allTextContents(),['一、选择题','二、填空题','三、解答题'])
  assert.equal(await preview.locator('.papr-question').count(),9)
  assert.deepEqual(await preview.locator('.question-number').allTextContents(),['1.','2.','3.','1.','2.','3.','1.','2.','3.'])
  await preview.getByLabel('显示答案与解析').check()
  assert.equal(await preview.locator('ol').count(),9)
  for(const [i,link] of (await preview.getByRole('link',{name:'下载PDF',exact:true}).all()).entries()) {
    const pending=page.waitForEvent('download');await link.click();const download=await pending
    const path=`${output}/mixed-${i}.pdf`;await download.saveAs(path)
    assert.equal((await readFile(path)).subarray(0,5).toString(),'%PDF-')
  }
  await preview.getByRole('button',{name:'沿用配置再练一份'}).click()
  await page.getByText('已沿用原目录、知识点、难度和题量，并检查当前可用性。确认后点击“生成练习”创建新题。',{exact:true}).waitFor()
  for(const title of ['选择题','填空题','解答题']) assert.equal(await page.getByLabel(title,{exact:true}).inputValue(),'3')
  await page.screenshot({path:output+'/mixed.png',fullPage:true})
  assert.deepEqual(errors,[])
  console.log(JSON.stringify({status:'mixed_paper_passed',points:2,total:9,types:3,pdf_pair:true}))
} finally {await browser.close()}
