<script setup lang="ts">
import { computed } from 'vue'
import QuestionRenderer from './PrintableQuestion.vue'
import type { PrintableQuestion as MultiplicationQuestion } from './printable'
const props = withDefaults(defineProps<{ questions: MultiplicationQuestion[]; showAnswers?: boolean }>(), { showAnswers: false })
const sections = computed(() => {
  const kinds = ['choice', 'fill', 'judgment', 'answer', 'application'] as const
  const groups = kinds.map(kind => ({kind, questions: props.questions.filter(q => q.question_type === kind)})).filter(g => g.questions.length)
  return groups.map((group, index) => {
    const name = group.kind === 'judgment' ? '判断题' : group.kind === 'application' ? '应用题' : group.kind === 'choice' ? '选择题' : group.kind === 'fill' ? '填空题' : groups.length===1&&group.questions.every(q=>q.render_spec.kind==='integer_multiplication'&&!q.render_spec.incorrect_result)?'竖式计算':'解答题'
    const rows: { columns: number; questions: MultiplicationQuestion[] }[] = []
    for (const [position, question] of group.questions.entries()) {
      const columns = props.showAnswers ? question.layout.solutions_per_row ?? 1 : question.layout.questions_per_row ?? 2
      const display = { ...question, position: position + 1 }
      const last = rows[rows.length - 1]
      if (last && last.columns === columns && last.questions.length < columns) last.questions.push(display)
      else rows.push({ columns, questions: [display] })
    }
    return { kind: group.kind, title: ['一', '二', '三', '四', '五'][index] + '、' + name, rows }
  })
})
</script>
<template>
  <section v-for="section in sections" :key="section.kind" class="question-section">
    <h2 class="question-section-title">{{ section.title }}</h2>
    <div v-for="row in section.rows" :key="row.questions[0].id" class="question-row" :style="{ gridTemplateColumns: `repeat(${row.columns}, minmax(0, 1fr))` }">
      <QuestionRenderer v-for="question in row.questions" :key="question.id" :question="question" :show-answers="showAnswers" />
    </div>
  </section>
</template>
<style scoped>
.question-section-title { font-size: 1.15em; break-after: avoid; page-break-after: avoid; }
.question-row { display: grid; column-gap: 10mm; margin-bottom: 4mm; break-inside: avoid; page-break-inside: avoid; }
.question-row .papr-question { margin: 0; min-width: 0; }
</style>
