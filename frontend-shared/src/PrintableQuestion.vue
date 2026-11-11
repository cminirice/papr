<script setup lang="ts">
import {computed} from 'vue'
import CurriculumDiagram from './CurriculumDiagram.vue'
import QuestionRenderer from './QuestionRenderer.vue'
import type {PrintableQuestion} from './printable'
import type {MultiplicationQuestion} from './api.generated'
const props=withDefaults(defineProps<{question:PrintableQuestion;showAnswers?:boolean}>(),{showAnswers:false})
const math=computed(()=>props.question.render_spec.kind==='integer_multiplication'?props.question as MultiplicationQuestion:null)
</script>
<template>
 <QuestionRenderer v-if="math" :question="math" :show-answers="showAnswers" />
 <article v-else class="papr-question reading-question">
  <p class="question-heading"><span>{{question.position}}.</span><span v-for="(block,i) in question.stem_blocks" :key="i">{{'text' in block?block.text:block.latex}}</span></p>
  <CurriculumDiagram v-if="question.render_spec.kind==='curriculum'&&question.render_spec.diagram" :diagram="question.render_spec.diagram" />
  <ol v-if="question.options?.length" type="A"><li v-for="option in question.options" :key="option.id">{{option.value}}</li></ol>
  <template v-if="showAnswers"><p>答案：{{question.answer.value}}</p><p v-for="(step,i) in question.explanation_steps" :key="i"><span v-for="(block,j) in step.blocks" :key="j">{{'text' in block?block.text:block.latex}}</span></p></template>
  <div v-else :style="{minHeight:`${question.layout.answer_space_mm}mm`}"></div>
 </article>
</template>
<style scoped>
.reading-question{break-inside:avoid;overflow-wrap:anywhere;color:#111}.question-heading{display:flex;gap:.75em}.question-heading>span:first-child{flex-shrink:0}ol{padding-left:6mm}
</style>
