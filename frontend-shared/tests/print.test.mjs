import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { renderDocument } from '../../print/dist/document.mjs'
import { buildHtml, validateInput, loadAssets } from '../../scripts/pdf_renderer.mjs'
const report = JSON.parse(await readFile(new URL('../../content/reports/mul-vertical-v1.development.json', import.meta.url), 'utf8'))
const questions = report.samples.map((q, i) => ({ ...q, position: i + 1 }))
const input = { schema_version: 1, title: '纸上练 <script>alert(1)</script>', generated_at: '2030-01-01T00:00:00.000000+08:00', questions }
const css = await readFile(new URL('../../print/dist/style.css', import.meta.url), 'utf8')
// Synthetic bytes test serialization only, not font loading, glyph coverage, browser layout or PDF output.
const assets = { renderDocument, css, font: Buffer.from('test-font-bytes'), mime: 'font/ttf' }

test('共享打印页学生版无解析，解析版复用原题并单独起页', async () => {
  const student = await buildHtml(input, false, assets)
  const solution = await buildHtml(input, true, assets)
  assert.equal((student.match(/<article/g) ?? []).length, questions.length)
  assert.equal((solution.match(/<article/g) ?? []).length, questions.length * 2)
  assert.ok(!student.includes('答案：') && solution.includes('答案：'))
  assert.ok(solution.includes('solution-section') && css.includes('break-before:page'))
  assert.ok(css.includes('size:A4') && css.includes('margin:15mm'))
  assert.ok(!student.includes('2030-01-01') && !student.includes('北京时间'))
  assert.ok(student.includes('min-height:35mm'))
  assert.equal((student.match(/一、竖式计算/g) ?? []).length, 1)
  assert.equal((solution.match(/一、竖式计算/g) ?? []).length, 2)
  assert.ok(!student.includes('用竖式计算：') && !solution.includes('用竖式计算：'))
})

test('打印内容转义且禁止页面远程资源与脚本', async () => {
  const html = await buildHtml(input, false, assets)
  assert.ok(!html.includes('<script>') && html.includes('&lt;script&gt;'))
  assert.ok(html.includes("default-src 'none'") && html.includes("script-src 'none'"))
  assert.ok(html.includes('data:font/ttf;base64,'))
  assert.ok(!html.includes('<script src=') && !html.includes('<link'))
})

test('打印入口拒绝空卷、错序、重复题目、无时区输入及超大留白', () => {
  validateInput(input)
  for (const changed of [
    { ...input, questions: [] }, { ...input, generated_at: '2030-01-01T00:00:00' },
    { ...input, questions: [questions[0], questions[0]] },
    { ...input, questions: [{ ...questions[0], position: 2 }] },
    { ...input, questions: [{ ...questions[0], layout: { answer_space_mm: 1000 } }] },
  ]) assert.throws(() => validateInput(changed), /PRINT_INPUT_INVALID/)
})

test('字体必须使用明确本地绝对路径和支持的嵌入格式', async () => {
  await assert.rejects(loadAssets('relative-font.ttf'), /PRINT_FONT_PATH_INVALID/)
  await assert.rejects(loadAssets('/tmp/font.ttc'), /PRINT_FONT_FORMAT_UNSUPPORTED/)
})

test('题目和解析独立读取快照列数，配置切换时另起一行', async () => {
  const configured = structuredClone(input)
  configured.questions = questions.map((q, i) => ({ ...q, layout: { ...q.layout,
    questions_per_row: i === 2 ? 1 : 2, solutions_per_row: 2,
  } }))
  const html = await buildHtml(configured, true, assets)
  const [student, solution] = html.split('class="solution-section"')
  assert.equal((student.match(/style="grid-template-columns:repeat\(2,/g) ?? []).length, 2)
  assert.equal((student.match(/style="grid-template-columns:repeat\(1,/g) ?? []).length, 1)
  assert.equal((solution.match(/style="grid-template-columns:repeat\(2,/g) ?? []).length, Math.ceil(questions.length / 2))
  assert.equal((solution.match(/<article/g) ?? []).length, questions.length)
  for (const columns of [3, 4, 5]) {
    const expanded = structuredClone(configured)
    for (const q of expanded.questions) q.layout.questions_per_row = q.layout.solutions_per_row = columns
    const rendered = await buildHtml(expanded, true, assets)
    assert.equal(rendered.split(`style="grid-template-columns:repeat(${columns},`).length - 1, Math.ceil(questions.length / columns) * 2)
    assert.equal((rendered.match(/<article/g) ?? []).length, questions.length * 2)
  }
  const single = structuredClone(configured)
  for (const q of single.questions) q.layout.questions_per_row = q.layout.solutions_per_row = 1
  const allSingle = await buildHtml(single, true, assets)
  assert.equal((allSingle.match(/style="grid-template-columns:repeat\(1,/g) ?? []).length, questions.length * 2)
})

test('打印入口拒绝快照中非法列数，旧快照仍使用题目2解析1', async () => {
  for (const field of ['questions_per_row', 'solutions_per_row']) {
    for (const invalid of [0, 6, true, '2', null]) {
      const changed = structuredClone(input)
      changed.questions[0].layout[field] = invalid
      assert.throws(() => validateInput(changed), /PRINT_INPUT_INVALID/)
    }
  }
  const html = await buildHtml(input, true, assets)
  const [student, solution] = html.split('class="solution-section"')
  assert.equal((student.match(/style="grid-template-columns:repeat\(2,/g) ?? []).length, Math.ceil(questions.length / 2))
  assert.equal((solution.match(/style="grid-template-columns:repeat\(1,/g) ?? []).length, questions.length)
})

test('乘积填空学生版保留空格且不泄露答案，解析版显示乘积与过程', async () => {
  const fill = { ...input, questions: questions.map(q => ({ ...q, question_type: 'fill', render_mode: 'direct' })) }
  const student = await buildHtml(fill, false, assets)
  const solution = await buildHtml(fill, true, assets)
  assert.ok(student.includes('一、填空题') && !student.includes('一、竖式计算'))
  assert.equal((student.match(/class="vertical"/g) ?? []).length, 0)
  assert.ok(!student.includes('答案：'))
  for (const q of questions) assert.ok(!student.includes(q.answer.value))
  assert.equal((solution.match(/class="vertical"/g) ?? []).length, questions.length)
  assert.ok(solution.includes('答案：'))
  for (const q of questions) assert.ok(solution.includes(q.answer.value))
  assert.throws(() => validateInput({ ...fill, questions: [{ ...fill.questions[0], render_mode: 'vertical' }] }), /PRINT_INPUT_INVALID/)
})

test('选择题按快照顺序显示四项，解析字母与稳定正确选项一致', async () => {
  const q = questions[0]
  const choice = { ...q, position: 1, question_type: 'choice', render_mode: 'direct',
    options: [{ id: 'wrong-1', value: '1' }, { id: 'correct', value: q.answer.value }, { id: 'wrong-2', value: '2' }, { id: 'wrong-3', value: '3' }],
    answer: { kind: 'single_choice', value: q.answer.value, correct_option_id: 'correct' } }
  const student = await buildHtml({ ...input, questions: [choice] }, false, assets)
  const solution = await buildHtml({ ...input, questions: [choice] }, true, assets)
  assert.ok(student.includes('一、选择题') && student.includes('A. 1') && student.includes(`B. ${q.answer.value}`))
  assert.ok(student.includes('D. 3') && !student.includes('答案：') && !student.includes('class="vertical"'))
  assert.ok(solution.replace(/<!--.*?-->/g, '').includes(`B，${q.answer.value}`))
})

test('缺数填空学生版遮住十位且保留乘积，解析版恢复数字', async () => {
  const q = questions[0]
  const missing = { ...q, position: 1, difficulty: 'challenge', question_type: 'fill', render_mode: 'vertical',
    render_spec: { ...q.render_spec, missing_digit_index: 1 }, answer: { kind: 'numeric', value: q.render_spec.multiplicand[1] } }
  const student = await buildHtml({ ...input, questions: [missing] }, false, assets)
  const solution = await buildHtml({ ...input, questions: [missing] }, true, assets)
  assert.ok(student.includes(q.render_spec.multiplicand[0] + '□' + q.render_spec.multiplicand[2]))
  assert.ok(student.includes(q.render_spec.result) && !student.includes('答案：'))
  assert.ok(!student.includes(`<div>${q.render_spec.multiplicand}</div>`))
  assert.ok(solution.includes('答案：') && solution.includes(q.render_spec.multiplicand))
})

test('辨错选择保留给定错误过程，正确竖式只出现在解析版', async () => {
  const q = questions[0]
  const wrongTens = String(Number(q.render_spec.tens_partial) / 10)
  const wrongResult = String(Number(q.render_spec.ones_partial) + Number(wrongTens))
  const reason = { ...q, position: 1, difficulty: 'challenge', question_type: 'choice', render_mode: 'vertical',
    render_spec: { ...q.render_spec, incorrect_tens_partial: wrongTens, incorrect_result: wrongResult },
    options: ['十位部分积没有按十位对齐','个位乘法算错了','乘数的十位数字看错了','两个部分积相加算错了'].map((value,i) => ({id:String(i),value})),
    answer: {kind:'single_choice',value:'十位部分积没有按十位对齐',correct_option_id:'0'} }
  const student = await buildHtml({...input,questions:[reason]},false,assets)
  const solution = await buildHtml({...input,questions:[reason]},true,assets)
  assert.ok(student.includes('给出的错误过程：') && student.includes(wrongResult))
  assert.ok(!student.includes('答案：') && !student.includes('正确过程：'))
  assert.ok(solution.includes('正确过程：') && solution.includes(q.render_spec.result))
})

test('纠错解答学生版要求说明并改正，解析版含正确结果', async () => {
  const q=questions[0]
  const wrongTens=String(Number(q.render_spec.tens_partial)/10)
  const correction={...q,position:1,difficulty:'challenge',render_spec:{...q.render_spec,
    incorrect_tens_partial:wrongTens,incorrect_result:String(Number(q.render_spec.ones_partial)+Number(wrongTens))}}
  const student=await buildHtml({...input,questions:[correction]},false,assets)
  const solution=await buildHtml({...input,questions:[correction]},true,assets)
  assert.ok(student.includes('说明原因并写出正确的竖式'))
  assert.ok(!student.includes('答案：') && !student.includes('正确过程：'))
  assert.ok(solution.includes('正确过程：') && solution.includes(q.render_spec.result))
})

test('混合题型按选择填空解答分大题，小题编号各自从1开始', async () => {
  const q=questions[0]
  const mixed=[{...q,position:1}, {...q,id:'mixed-choice',position:2,question_type:'choice',render_mode:'direct',
    options:[{id:'correct',value:q.answer.value},{id:'x',value:'1'},{id:'y',value:'2'},{id:'z',value:'3'}],
    answer:{kind:'single_choice',value:q.answer.value,correct_option_id:'correct'}},
    {...q,id:'mixed-fill',position:3,question_type:'fill',render_mode:'direct'}]
  const student=await buildHtml({...input,questions:mixed},false,assets)
  assert.ok(student.indexOf('一、选择题')<student.indexOf('二、填空题') && student.indexOf('二、填空题')<student.indexOf('三、解答题'))
  assert.equal((student.match(/class="question-number"[^>]*>1\./g)??[]).length,3)
  const solution=await buildHtml({...input,questions:mixed},true,assets)
  assert.equal((solution.match(/三、解答题/g)??[]).length,2)
})
