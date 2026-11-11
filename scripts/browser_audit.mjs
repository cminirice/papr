import assert from 'node:assert/strict'
import {chromium} from 'playwright-core'
const [executablePath,,admin,output]=process.argv.slice(2)
const browser=await chromium.launch({executablePath,headless:true})
try{
 const page=await browser.newPage();await page.goto(admin)
 await page.getByLabel('用户名',{exact:true}).fill('owner');await page.getByLabel('密码',{exact:true}).fill('test-only-admin-password')
 await page.getByRole('button',{name:'登录',exact:true}).click();await page.getByRole('button',{name:'操作记录',exact:true}).click()
 const panel=page.getByRole('region',{name:'操作记录',exact:true})
 await panel.locator('article').nth(19).waitFor();assert.equal(await panel.locator('article').count(),20)
 await panel.getByRole('button',{name:'加载更多操作记录',exact:true}).click();await panel.locator('article').nth(21).waitFor()
 await panel.getByLabel('对象类型',{exact:true}).fill('app_setting');await panel.getByLabel('操作名称',{exact:true}).fill('missing_action')
 await panel.getByRole('button',{name:'查询操作记录',exact:true}).click();await panel.getByText('没有符合条件的操作记录。',{exact:true}).waitFor()
 await panel.getByLabel('操作名称',{exact:true}).fill('update_setting');await panel.getByRole('button',{name:'查询操作记录',exact:true}).click()
 await panel.locator('article').first().waitFor();await panel.getByText('查看变更详情',{exact:true}).first().click()
 assert.match(await panel.locator('article').first().innerText(),/queue_limit/)
 await page.screenshot({path:output+'/audit.png',fullPage:true});console.log(JSON.stringify({status:'audit_browser_passed'}))
}finally{await browser.close()}
