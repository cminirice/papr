/** Internal renderer: no server, remote URL, browser profile, cookie or arbitrary HTML input. */
import { chromium } from 'playwright-core'
import { version as vueVersion } from 'vue'
import { createRequire } from 'node:module'
import { readFile } from 'node:fs/promises'
import { createHash } from 'node:crypto'
import { isAbsolute, extname } from 'node:path'
import { formatBeijingTime } from '../frontend-shared/src/time.mjs'

const playwrightVersion = createRequire(import.meta.url)('playwright-core/package.json').version
const ROOT = new URL('../', import.meta.url)
const sha256 = value => createHash('sha256').update(value).digest('hex')
export const RENDERER_VERSION = 'papr-chromium-v1'

export function validateInput(input) {
  if (!input || input.schema_version !== 1 || typeof input.title !== 'string' || !input.title.trim()
      || input.title.length > 128 || !Array.isArray(input.questions) || input.questions.length < 1 || input.questions.length > 200
      || typeof input.generated_at !== 'string' || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}\+08:00$/.test(input.generated_at)) {
    throw new Error('PRINT_INPUT_INVALID')
  }
  formatBeijingTime(input.generated_at)
  const ids = new Set()
  for (const [index, q] of input.questions.entries()) {
    if (!q || q.schema_version !== 1 || !((q.question_type === 'answer' && q.render_mode === 'vertical') || (['fill', 'choice', 'judgment', 'application', 'answer'].includes(q.question_type) && q.render_mode === 'direct') || (q.question_type === 'choice' && q.render_mode === 'vertical' && q.render_spec?.incorrect_result && q.difficulty === 'challenge') || (q.question_type === 'fill' && q.render_mode === 'vertical' && q.render_spec?.missing_digit_index === 1 && q.difficulty === 'challenge'))
        || q.position !== index + 1 || typeof q.id !== 'string' || ids.has(q.id)
        || !q.render_spec || !q.answer || !Array.isArray(q.explanation_steps)
        || !q.layout || !Number.isFinite(q.layout.answer_space_mm) || q.layout.answer_space_mm < (q.render_spec?.kind === 'curriculum' ? 6 : 20) || q.layout.answer_space_mm > 100) {
      throw new Error('PRINT_INPUT_INVALID')
    }
    for (const field of ['questions_per_row', 'solutions_per_row']) {
      if (q.layout[field] !== undefined && ![1, 2, 3, 4, 5].includes(q.layout[field])) throw new Error('PRINT_INPUT_INVALID')
    }
    ids.add(q.id)
  }
}

export async function loadAssets(fontPath) {
  if (!isAbsolute(fontPath)) throw new Error('PRINT_FONT_PATH_INVALID')
  const extension = extname(fontPath).toLowerCase()
  const mime = { '.ttf': 'font/ttf', '.otf': 'font/otf', '.woff2': 'font/woff2' }[extension]
  if (!mime) throw new Error('PRINT_FONT_FORMAT_UNSUPPORTED')
  const [css, module, font] = await Promise.all([
    readFile(new URL('print/dist/style.css', ROOT), 'utf8'),
    readFile(new URL('print/dist/document.mjs', ROOT)),
    readFile(fontPath),
  ])
  if (font.length < 100 || font.length > 32 * 1024 * 1024) throw new Error('PRINT_FONT_INVALID')
  const { renderDocument } = await import(new URL('print/dist/document.mjs', ROOT))
  return { css, renderDocument, font, mime, fontHash: sha256(font), assetHash: sha256(Buffer.concat([module, Buffer.from(css)])) }
}

export async function buildHtml(input, solution, assets) {
  validateInput(input)
  const markup = await assets.renderDocument({ title: input.title, generatedAt: formatBeijingTime(input.generated_at), questions: input.questions, solution })
  // Vue escapes content. The only inline style is trusted build CSS plus an explicitly supplied local font.
  return '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
    + '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; font-src data:; img-src data:; script-src \'none\'">'
    + '<style>@font-face{font-family:PaprPrint;src:url(data:' + assets.mime + ';base64,' + assets.font.toString('base64') + ');font-weight:100 900;}'
    + assets.css + '</style></head><body>' + markup + '</body></html>'
}

export async function renderPair(input, { browserPath, fontPath, timeoutMs = 60000 }) {
  validateInput(input)
  if (!isAbsolute(browserPath)) throw new Error('PRINT_BROWSER_PATH_INVALID')
  const assets = await loadAssets(fontPath)
  const html = await Promise.all([buildHtml(input, false, assets), buildHtml(input, true, assets)])
  let browser
  let timer
  let timedOut = false
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(() => { timedOut = true; void browser?.close(); reject(new Error('PDF_TIMEOUT')) }, timeoutMs)
  })
  const operation = (async () => {
    browser = await chromium.launch({ executablePath: browserPath, headless: true, timeout: timeoutMs,
      chromiumSandbox: true, args: ['--disable-background-networking', '--no-first-run'] })
    if (timedOut) { await browser.close(); throw new Error('PDF_TIMEOUT') }
    const context = await browser.newContext({ offline: true, serviceWorkers: 'block' })
    await context.route('**/*', route => route.abort())
    const page = await context.newPage()
    await page.emulateMedia({ media: 'print' })
    const files = []
    for (const content of html) {
      await page.setContent(content, { waitUntil: 'load', timeout: timeoutMs })
      await page.evaluate(async () => {
        const text = document.body.innerText
        const loaded = await document.fonts.load('16px PaprPrint', text)
        await document.fonts.ready
        if (!loaded.length || !document.fonts.check('16px PaprPrint', text)) throw new Error('PRINT_FONT_LOAD_FAILED')
        // One question may not exceed A4's 267mm usable height. Never silently clip it.
        const maxHeight = 267 * 96 / 25.4
        if ([...document.querySelectorAll('.papr-question')].some(q => q.getBoundingClientRect().height > maxHeight)) {
          throw new Error('PRINT_QUESTION_TOO_TALL')
        }
        document.documentElement.dataset.renderReady = 'true'
      })
      await page.waitForFunction(() => document.documentElement.dataset.renderReady === 'true')
      const pdf = await page.pdf({ format: 'A4', preferCSSPageSize: true, printBackground: false,
        displayHeaderFooter: false, margin: { top: '15mm', right: '15mm', bottom: '15mm', left: '15mm' } })
      // Transport sanity only. Full PDF parser/page/font checks are required before production publication.
      if (pdf.length < 1000 || !pdf.subarray(0, 5).equals(Buffer.from('%PDF-')) || !pdf.subarray(-1024).includes(Buffer.from('%%EOF'))) {
        throw new Error('PDF_OUTPUT_INVALID')
      }
      files.push(pdf)
    }
    return { student: files[0], solution: files[1], metadata: {
      renderer_version: RENDERER_VERSION, playwright_version: playwrightVersion, vue_version: vueVersion, browser_version: browser.version(),
      input_sha256: sha256(JSON.stringify(input)),
      font_sha256: assets.fontHash, print_asset_sha256: assets.assetHash, content_schema_version: 1,
      student_sha256: sha256(files[0]), solution_sha256: sha256(files[1]), pdf_parser_checked: false,
    } }
  })()
  try { return await Promise.race([operation, timeout]) }
  finally { clearTimeout(timer); await browser?.close() }
}
