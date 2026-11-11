<script setup lang="ts">
import QuestionRenderer from '../../frontend-shared/src/QuestionRenderer.vue'
import type { MultiplicationQuestion } from '@papr/shared/contracts'
import type { ReadingSample } from './template-samples'
defineProps<{block:{title?:string; questions?:{position:number; math:MultiplicationQuestion|null;reading:ReadingSample|null}[]};columns:number;showAnswers:boolean}>()
</script>
<template>
 <div class="sample-block">
  <h2 v-if="block.title">{{block.title}}</h2>
  <div v-else class="sample-row" :style="{gridTemplateColumns:`repeat(${columns},minmax(0,1fr))`}">
   <article v-for="sample in block.questions" :key="sample.position" class="sample-question">
    <QuestionRenderer v-if="sample.math" :question="sample.math" :show-answers="showAnswers" />
    <template v-else-if="sample.reading">
     <p class="reading-heading"><span>{{sample.position}}.</span><span>{{sample.reading.stem}}</span></p>
     <ol v-if="sample.reading.options.length" type="A"><li v-for="option in sample.reading.options" :key="option">{{option}}</li></ol>
     <div v-if="showAnswers" class="reading-answer"><p>答案：{{sample.reading.answer}}</p><p>解析：{{sample.reading.explanation}}</p></div><div v-else class="reading-space"></div>
    </template>
   </article>
  </div>
 </div>
</template>
<style scoped>
.sample-block{display:flow-root;padding-bottom:4mm;break-inside:avoid}.sample-block h2{font-size:13pt;line-height:1.5;margin:0 0 2mm}.sample-row{display:grid;column-gap:10mm}.sample-question{min-width:0;overflow-wrap:anywhere}.sample-question :deep(.papr-question){margin:0}.reading-heading{display:flex;gap:.75em;margin:0}.reading-heading>span:first-child{flex-shrink:0}.reading-space{min-height:15mm}.reading-answer p{margin:2mm 0}.sample-question ol{padding-left:6mm}
</style>
