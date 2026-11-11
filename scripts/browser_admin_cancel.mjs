import assert from 'node:assert/strict'
import {chromium} from 'playwright-core'
const [executablePath,,admin,output]=process.argv.slice(2)
const browser=await chromium.launch({executablePath,headless:true})
try {
 const page=await browser.newPage();await page.goto(admin)
 await page.getByLabel('用户名',{exact:true}).fill('owner');await page.getByLabel('密码',{exact:true}).fill('test-only-admin-password')
 await page.getByRole('button',{name:'登录',exact:true}).click()
 await page.getByRole('button',{name:'生成记录与统计',exact:true}).click()
 await page.getByRole('button',{name:'查看任务',exact:true}).first().click()
 await page.getByLabel('取消任务理由',{exact:true}).fill('浏览器取消排队任务')
 const response=page.waitForResponse(r=>r.url().endsWith('/cancel')&&r.request().method()==='POST')
 await page.getByRole('button',{name:'取消排队任务',exact:true}).click()
 assert.equal((await response).status(),204)
 await page.getByRole('region',{name:'任务详情',exact:true}).getByText(/已取消/).waitFor()
 assert.equal(await page.getByRole('button',{name:'取消排队任务',exact:true}).count(),0)
 await page.screenshot({path:output+'/admin-cancel.png',fullPage:true})
 console.log(JSON.stringify({status:'admin_cancel_browser_passed'}))
} finally {await browser.close()}
