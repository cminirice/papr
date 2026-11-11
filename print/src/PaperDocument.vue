<script setup lang="ts">
import QuestionSections from '../../frontend-shared/src/QuestionSections.vue'
import type { PrintableQuestion as MultiplicationQuestion } from '../../frontend-shared/src/printable'
defineProps<{ title: string; generatedAt: string; questions: MultiplicationQuestion[]; solution: boolean }>()
</script>
<template>
  <main>
    <section class="student-section">
      <header><h1>{{ title }}</h1><p>姓名：________________　日期：________________</p>
        <p class="paper-meta">共 {{ questions.length }} 题</p></header>
      <QuestionSections :questions="questions" />
    </section>
    <section v-if="solution" class="solution-section">
      <header><h1>{{ title }} · 答案与解析</h1></header>
      <QuestionSections :questions="questions" show-answers />
    </section>
  </main>
</template>
<style>
@page { size: A4; margin: 15mm; }
html, body { margin: 0; padding: 0; background: white; color: black; }
body { font-family: 'PaprPrint', sans-serif; font-size: 11pt; line-height: 1.5; }
h1 { font-size: 18pt; margin: 0 0 5mm; }
header { break-inside: avoid; }
.paper-meta { font-size: 9pt; }
.question-section-title { font-size: 13pt; margin: 4mm 0 2mm; break-after: avoid; page-break-after: avoid; }
.question-row {
  display: grid;
  column-gap: 10mm;
  margin-bottom: 4mm;
  break-inside: avoid;
  page-break-inside: avoid;
}
.question-row .papr-question { margin: 0; min-width: 0; }
.solution-section { break-before: page; }
.papr-question { break-inside: avoid; page-break-inside: avoid; }
.papr-question .vertical { font-family: 'PaprPrint', monospace; }
</style>
