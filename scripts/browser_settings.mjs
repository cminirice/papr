import assert from 'node:assert/strict'
import {chromium} from 'playwright-core'
const [executablePath,,admin,output]=process.argv.slice(2)
const browser=await chromium.launch({executablePath,headless:true})
try{
 const page=await browser.newPage();await page.goto(admin)
 await page.getByLabel('用户名',{exact:true}).fill('owner');await page.getByLabel('密码',{exact:true}).fill('test-only-admin-password')
 await page.getByRole('button',{name:'登录',exact:true}).click();await page.getByRole('button',{name:'系统设置',exact:true}).click()
 await page.getByRole('button',{name:'生成限额',exact:true}).click()
 await page.getByLabel('全局处理中任务上限',{exact:true}).fill('4')
 await page.getByLabel('同IP每600秒受理上限',{exact:true}).fill('5')
 await page.getByLabel('设置修改理由',{exact:true}).fill('隔离浏览器设置验收')
 await page.getByRole('button',{name:'保存设置',exact:true}).click();await page.getByText('设置已保存',{exact:true}).waitFor()
 await page.getByRole('button',{name:'重新加载设置',exact:true}).click();await page.getByRole('button',{name:'生成限额',exact:true}).click()
 assert.equal(await page.getByLabel('全局处理中任务上限',{exact:true}).inputValue(),'4')
 await page.getByRole('button',{name:'题量档位',exact:true}).click();await page.getByLabel('选择题 12题',{exact:true}).uncheck()
 await page.getByLabel('设置修改理由',{exact:true}).fill('收紧选择题档位')
 await page.getByRole('button',{name:'保存设置',exact:true}).click();await page.getByText('设置已保存',{exact:true}).waitFor()
 await page.reload();await page.getByRole('button',{name:'系统设置',exact:true}).click();await page.getByRole('button',{name:'题量档位',exact:true}).click()
 assert.equal(await page.getByLabel('选择题 12题',{exact:true}).isChecked(),false)
 await page.screenshot({path:output+'/settings.png',fullPage:true});console.log(JSON.stringify({status:'settings_browser_passed'}))
}finally{await browser.close()}
