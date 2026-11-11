import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { pathToFileURL } from 'node:url'
import { parse, compileScript } from '@vue/compiler-sfc'
import { createSSRApp } from 'vue'
import { renderToString } from 'vue/server-renderer'
import ts from 'typescript'

const require = createRequire(import.meta.url)
const source = await readFile(new URL('../src/QuestionRenderer.vue', import.meta.url), 'utf8')
const { descriptor } = parse(source)
const compiled = compileScript(descriptor, { id: 'question-test', inlineTemplate: true })
const javascript = ts.transpileModule(compiled.content, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext },
}).outputText.replace(/from ['"]vue['"]/g, `from ${JSON.stringify(pathToFileURL(require.resolve('vue')).href)}`)
const { default: Renderer } = await import('data:text/javascript;base64,' + Buffer.from(javascript).toString('base64'))
const report = JSON.parse(await readFile(new URL('../../content/reports/mul-vertical-v1.development.json', import.meta.url), 'utf8'))
const question = report.samples.find(item => item.render_spec.multiplicand === '308')

test('学生版隐藏部分积与答案，并保留答题留白', async () => {
  const html = await renderToString(createSSRApp(Renderer, { question }))
  assert.ok(html.includes('308') && html.includes('26'))
  assert.ok(!html.includes('8008') && !html.includes('1848') && !html.includes('6160'))
  assert.ok(html.includes('min-height:35mm'))
  assert.match(html.replace(/<!--.*?-->/g, ''), /class="question-number"[^>]*>\d+\.<\/span><span[^>]*>308 × 26<\/span>/)
})

test('解析版十位部分积不重复乘10，文本安全转义', async () => {
  const changed = structuredClone(question)
  changed.explanation_steps[0].blocks[0].text = '<img src=x onerror=alert(1)>'
  const html = await renderToString(createSSRApp(Renderer, { question: changed, showAnswers: true }))
  assert.ok(html.includes('1848') && html.includes('6160') && html.includes('8008'))
  assert.ok(!html.includes('61600') && !html.includes('<img'))
  assert.ok(html.includes('&lt;img'))
  assert.match(html, /class="line tens-partial"[^>]*><span[^>]*>616<\/span><span class="place-value-space"[^>]*>0<\/span>/)
  // Only the place-value zero is hidden: 100 × 10 must display 100 shifted, not 1.
  changed.render_spec.tens_partial = '1000'
  const withZeros = await renderToString(createSSRApp(Renderer, { question: changed, showAnswers: true }))
  assert.match(withZeros, /class="line tens-partial"[^>]*><span[^>]*>100<\/span>/)
})
