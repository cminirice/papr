import assert from 'node:assert/strict'
import {chromium} from 'playwright-core'
const [executablePath,web,admin,output]=process.argv.slice(2)
const browser=await chromium.launch({executablePath,headless:true})
try{
 const context=await browser.newContext(),page=await context.newPage();await page.goto(web)
 await page.getByLabel(/^目录/).selectOption({index:1});await page.getByLabel(/^主题/).selectOption({index:1})
 await page.getByRole('checkbox').first().check();await page.getByRole('button',{name:'查看可用题量'}).click()
 await page.getByRole('button',{name:'生成练习',exact:true}).click()
 const eventResponse=()=>page.waitForResponse(r=>r.url().endsWith('/api/v1/events')&&r.request().method()==='POST')
 let response=eventResponse();await page.getByRole('button',{name:'打开练习',exact:true}).click({timeout:90000})
 assert.equal((await response).status(),200)
 const preview=page.getByRole('region',{name:'试卷预览',exact:true})
 response=eventResponse();const popup=context.waitForEvent('page');await preview.getByRole('link',{name:'打开并打印',exact:true}).first().click()
 const pdf=await popup;assert.equal((await response).status(),200);await pdf.close()
 // Drop the first response AFTER committing it, to exercise same-ID retry deduplication.
 let intercepted=0
 await page.route('**/api/v1/events',async route=>{intercepted++;if(intercepted===1){await route.fetch();await route.abort()}else await route.continue()})
 await page.getByRole('button',{name:'收起预览',exact:true}).click();response=eventResponse();await page.getByRole('button',{name:'打开练习',exact:true}).click()
 assert.equal((await(await response).json()).data.duplicate_ids.length,1)
 await page.unroute('**/api/v1/events')
 // Permanent event transport failure must not block preview or the PDF link.
 await page.route('**/api/v1/events',route=>route.abort())
 await page.getByRole('button',{name:'收起预览',exact:true}).click();await page.getByRole('button',{name:'打开练习',exact:true}).click()
 await preview.waitFor();const link=await preview.getByRole('link',{name:'下载PDF',exact:true}).first().getAttribute('href')
 assert.equal((await context.request.get(web+link)).status(),200)
 const manager=await context.newPage();await manager.goto(admin)
 await manager.getByLabel('用户名',{exact:true}).fill('owner');await manager.getByLabel('密码',{exact:true}).fill('test-only-admin-password')
 await manager.getByRole('button',{name:'登录',exact:true}).click();await manager.getByRole('button',{name:'生成记录与统计',exact:true}).click()
 await manager.getByText('预览次数：2；打印意向次数：1。',{exact:true}).waitFor()
 await manager.screenshot({path:output+'/usage-counts.png',fullPage:true});console.log(JSON.stringify({status:'events_browser_passed',retry_deduplicated:true,transport_failure_nonblocking:true}))
}finally{await browser.close()}
