<script setup lang="ts">
import type { MultiplicationQuestion } from './api.generated'
withDefaults(defineProps<{ question: MultiplicationQuestion; showAnswers?: boolean }>(), { showAnswers: false })
const optionLetter = (index: number) => 'ABCD'[index]
const mathText = (value: string) => value.replace(/\\times\s*/g, '×')
</script>

<template>
  <article class="papr-question">
    <p class="question-heading"><span class="question-number">{{ question.position }}.</span><span>{{ question.render_spec.missing_digit_index === 1 && !showAnswers ? question.render_spec.multiplicand[0] + '□' + question.render_spec.multiplicand[2] : question.render_spec.multiplicand }} × {{ question.render_spec.multiplier }}<template v-if="question.question_type === 'fill' && question.render_mode === 'direct'"> =（{{ showAnswers ? question.answer.value : '　　　' }}）</template><template v-if="question.render_spec.missing_digit_index === 1"> = {{ question.render_spec.result }}</template></span></p>
    <p v-if="question.render_spec.incorrect_result">{{ question.question_type === 'choice' ? '下面竖式哪里出错了？选择正确的原因。' : '指出下面竖式的错误，说明原因并写出正确的竖式。' }}</p>
    <div v-if="question.render_spec.incorrect_result" class="incorrect-work">
      <p>给出的错误过程：</p><div class="vertical">
        <div>{{ question.render_spec.multiplicand }}</div>
        <div class="line"><span class="operator">×</span>{{ question.render_spec.multiplier }}</div>
        <div>{{ question.render_spec.ones_partial }}</div>
        <div class="line">{{ question.render_spec.incorrect_tens_partial }}</div>
        <div>{{ question.render_spec.incorrect_result }}</div>
      </div>
    </div>
    <ul v-if="question.question_type === 'choice'" class="choice-options" :class="{ 'reason-options': !!question.render_spec.incorrect_result }">
      <li v-for="(option, index) in question.options" :key="option.id">{{ optionLetter(index) }}. {{ option.value }}</li>
    </ul>
    <p v-if="question.render_spec.incorrect_result && showAnswers">正确过程：</p>
    <div v-if="(question.render_mode === 'vertical' && !question.render_spec.incorrect_result) || showAnswers"
      class="vertical-work" :style="!showAnswers && question.question_type === 'answer' ? { minHeight: `${question.layout.answer_space_mm ?? 35}mm` } : undefined">
    <div class="vertical">
      <div>{{ question.render_spec.missing_digit_index === 1 && !showAnswers ? question.render_spec.multiplicand[0] + '□' + question.render_spec.multiplicand[2] : question.render_spec.multiplicand }}</div>
      <div class="line"><span class="operator">×</span>{{ question.render_spec.multiplier }}</div>
      <div v-if="question.render_spec.missing_digit_index === 1 && !showAnswers">{{ question.render_spec.result }}</div>
      <template v-if="showAnswers">
        <div>{{ question.render_spec.ones_partial }}</div>
        <div class="line tens-partial"><span>{{ question.render_spec.tens_partial.slice(0, -1) }}</span><span class="place-value-space" aria-hidden="true">0</span></div>
        <div>{{ question.render_spec.result }}</div>
      </template>
    </div>
    </div>
    <div v-if="!showAnswers && !(question.render_mode === 'vertical' && question.question_type === 'answer' && !question.render_spec.incorrect_result)" :style="{ minHeight: `${question.layout.answer_space_mm ?? 35}mm` }"></div>
    <template v-if="showAnswers">
      <p>答案：<template v-if="question.answer.kind === 'single_choice'">{{ optionLetter((question.options ?? []).findIndex(o => question.answer.kind === 'single_choice' && o.id === question.answer.correct_option_id)) }}，</template>{{ question.answer.value }}</p>
      <ol><li v-for="(step, index) in question.explanation_steps" :key="index">
        <span v-for="(block, blockIndex) in step.blocks" :key="blockIndex">{{ 'text' in block ? block.text : mathText(block.latex) }} </span>
      </li></ol>
    </template>
  </article>
</template>

<style scoped>
.papr-question { break-inside: avoid; margin: 16px 0; color: #111; }
.question-heading { display: flex; align-items: baseline; column-gap: .75em; }
.question-number { flex-shrink: 0; }
.choice-options { list-style: none; padding: 0; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 4px 12px; }
.reason-options { grid-template-columns: 1fr; }
.vertical { font: 20px/1.5 monospace; font-variant-numeric: tabular-nums; width: 7ch; text-align: right; margin: 12px 0; }
.vertical-work { display: flow-root; }
/* Keep the digit-width spacer invisible even in the admin print visibility override. */
.place-value-space { visibility: hidden !important; }
.line { border-bottom: 1px solid #111; }
.operator { float: left; }
@media print { .papr-question { margin: 8mm 0; } }
</style>
