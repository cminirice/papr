import { createSSRApp } from 'vue'
import { renderToString } from 'vue/server-renderer'
import PaperDocument from './PaperDocument.vue'
import type { PrintableQuestion as MultiplicationQuestion } from '../../frontend-shared/src/printable'

export async function renderDocument(props: {
  title: string; generatedAt: string; questions: MultiplicationQuestion[]; solution: boolean
}): Promise<string> {
  return renderToString(createSSRApp(PaperDocument, props))
}
