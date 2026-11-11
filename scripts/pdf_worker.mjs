// Private worker protocol. Paths come from server configuration, never an HTTP request.
import { writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { renderPair } from './pdf_renderer.mjs'
try {
  const chunks = []
  let size = 0
  for await (const chunk of process.stdin) {
    size += chunk.length
    if (size > 1024 * 1024) throw new Error('INPUT_TOO_LARGE')
    chunks.push(chunk)
  }
  const input = JSON.parse(Buffer.concat(chunks).toString('utf8'))
  const directory = process.argv[4]
  process.env.PAPR_BROWSER_EXECUTABLE = process.argv[2]
  process.env.PAPR_BROWSER_PID_FILE = join(directory, 'browser.pid')
  const launcher = fileURLToPath(new URL('./chrome_worker_launcher.sh', import.meta.url))
  const result = await renderPair(input, { browserPath: launcher, fontPath: process.argv[3] })
  await writeFile(join(directory, 'student.pdf'), result.student, { flag: 'wx', mode: 0o600 })
  await writeFile(join(directory, 'solution.pdf'), result.solution, { flag: 'wx', mode: 0o600 })
  await writeFile(join(directory, 'metadata.json'), JSON.stringify(result.metadata), { flag: 'wx', mode: 0o600 })
} catch {
  process.stderr.write('PDF_RENDER_FAILED\n')
  process.exitCode = 1
}
