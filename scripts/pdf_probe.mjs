/** Development-only browser/PDF diagnosis. Never publishes database assets or enables admission. */
import { chromium } from 'playwright-core'
import { parseArgs } from 'node:util'
import { access, mkdir, readFile, writeFile } from 'node:fs/promises'
import { constants } from 'node:fs'
import { isAbsolute, join } from 'node:path'
import { renderPair } from './pdf_renderer.mjs'

const { values } = parseArgs({ options: {
  browser: { type: 'string' }, input: { type: 'string' }, font: { type: 'string' }, output: { type: 'string' },
} })
let stage = 'configuration'
let browser
try {
  if (!values.browser || !isAbsolute(values.browser)) throw new Error('Provide --browser with an absolute executable path')
  await access(values.browser, constants.X_OK)
  const rendering = Boolean(values.input || values.font || values.output)
  if (rendering && !(values.input && values.font && values.output && isAbsolute(values.font) && isAbsolute(values.output))) {
    throw new Error('Rendering requires --input, absolute --font and absolute --output (new directory)')
  }
  stage = 'browser_launch'
  browser = await chromium.launch({ executablePath: values.browser, headless: true, timeout: 15000, chromiumSandbox: true })
  const context = await browser.newContext({ offline: true, serviceWorkers: 'block' })
  await context.route('**/*', route => route.abort())
  const page = await context.newPage()
  await page.setContent('<!doctype html><p>papr browser probe</p>')
  if (await page.locator('p').innerText() !== 'papr browser probe') throw new Error('DOM_PROBE_FAILED')
  const browserVersion = browser.version()
  await browser.close(); browser = undefined
  if (!rendering) {
    console.log(JSON.stringify({ status: 'browser_ready', browser_version: browserVersion, pdf_checked: false, font_checked: false }))
  } else {
    stage = 'input'
    const stat = await readFile(values.input)
    if (stat.length > 1024 * 1024) throw new Error('PRINT_INPUT_TOO_LARGE')
    const input = JSON.parse(stat)
    stage = 'pdf_rendering'
    const result = await renderPair(input, { browserPath: values.browser, fontPath: values.font })
    stage = 'sample_output'
    // mkdir without recursive refuses an existing destination, including existing real outputs.
    await mkdir(values.output)
    await writeFile(join(values.output, 'student.pdf'), result.student, { flag: 'wx' })
    await writeFile(join(values.output, 'solution.pdf'), result.solution, { flag: 'wx' })
    const report = { status: 'development_sample_only', ...result.metadata, human_review: 'pending',
      a4_review: 'pending', production_ready: false }
    await writeFile(join(values.output, 'report.json'), JSON.stringify(report, null, 2) + '\n', { flag: 'wx' })
    console.log(JSON.stringify(report))
  }
} catch (error) {
  // Chrome diagnostics may contain local paths/environment; keep the default output small and sanitized.
  const code = stage === 'browser_launch' ? 'BROWSER_LAUNCH_FAILED' : stage === 'configuration' ? 'CONFIGURATION_INVALID' : 'PDF_PROBE_FAILED'
  console.error(JSON.stringify({ status: 'failed', stage, code, error_type: error?.name ?? 'Error', production_ready: false }))
  process.exitCode = 1
} finally { await browser?.close() }
