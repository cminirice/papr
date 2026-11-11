<script setup lang="ts">
import { ref, watch } from 'vue'
import { recordUsage } from './events'
import { formatBeijingTime } from '@papr/shared/time'
import QuestionSections from '@papr/shared/questions'
import type { PaperDetail, PaperSelection } from '@papr/shared/contracts'
const props=defineProps<{ paper: PaperDetail; csrfToken: string }>()
watch(()=>props.paper.id, id=>recordUsage('preview',id,'student',props.csrfToken),{immediate:true})
const emit = defineEmits<{ reuse: [selection: PaperSelection]; close: [] }>()
const showAnswers = ref(false)
const names = { basic: '基础', standard: '提高', challenge: '挑战' }
</script>

<template>
  <section class="paper-preview" aria-label="试卷预览">
    <h3>{{ paper.title }} · {{ paper.total_count }}题</h3>
    <p class="muted">{{ names[paper.difficulty] }}</p>
    <p v-if="paper.status === 'withdrawn'" role="alert">此练习已撤下，不能下载或打印。请查看下方说明。</p>
    <p v-for="notice in paper.notices ?? []" :key="notice.id" role="note">{{ notice.severity === 'error' ? '勘误' : '说明' }}：{{ notice.message }}（{{ formatBeijingTime(notice.created_at) }}）</p>
    <div class="actions">
      <label><input v-model="showAnswers" type="checkbox">显示答案与解析</label>
      <button type="button" @click="emit('reuse', paper.selection)">沿用配置再练一份</button>
      <button type="button" @click="emit('close')">收起预览</button>
    </div>
    <p class="muted">预览和下载使用已保存内容，不会延长冷却。再练一份会先回填配置，确认后生成新题，仍需遵守十分钟冷却。</p>
    <p v-for="file in paper.files" :key="file.id">
      {{ file.kind === 'student_pdf' ? '学生版' : '解析版' }}（{{ file.pages }}页）
      <a :href="`/api/v1/files/${file.id}`">下载PDF</a>
      · <a :href="`/api/v1/files/${file.id}?disposition=inline`" target="_blank" rel="noopener" @click="recordUsage('print_intent',paper.id,file.kind==='student_pdf'?'student':'solution',csrfToken)">打开并打印</a>
    </p>
    <QuestionSections :questions="paper.questions" :show-answers="showAnswers" />
  </section>
</template>

<style scoped>
.paper-preview { margin-top: 20px; }
.actions { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; }
.actions label { display: flex; align-items: center; gap: 8px; }
.preview-questions { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 240px), 1fr)); gap: 20px; }
</style>
