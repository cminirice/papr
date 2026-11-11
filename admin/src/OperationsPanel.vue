<script setup lang="ts">
import { onMounted, ref, useId } from 'vue'
import { ApiError, requestData } from '@papr/shared/api'
import { formatBeijingTime } from '@papr/shared/time'
import QuestionRenderer from '@papr/shared/question'
import QuestionSections from '@papr/shared/questions'
import type { AdminJobList, AdminJobDetail, AdminJobSummary } from '@papr/shared/contracts'

import { useAdminWrite } from './useAdminWrite'
const props = defineProps<{ csrfToken: string }>()
const uid=useId(), send=useAdminWrite(props.csrfToken), cancelReason=ref('')
async function cancelSelected(){
  if(!selected.value||busy.value||!cancelReason.value.trim())return
  busy.value=true;error.value=''
  try{await send<void>('/admin/api/v1/jobs/'+selected.value.job.id+'/cancel',{reason:cancelReason.value});selected.value=await requestData<AdminJobDetail>('/admin/api/v1/jobs/'+selected.value.job.id);cancelReason.value=''}catch(e){error.value=message(e)}finally{busy.value=false}
}
const emit = defineEmits<{ openTemplate: [templateId: string, versionId: string] }>()
const dateFrom = ref('')
const dateTo = ref('')
const kind = ref('paper_generate')
const status = ref('')
const busy = ref(false)
const error = ref('')
const records = ref<AdminJobList | null>(null)
const selected = ref<AdminJobDetail | null>(null)
let applied = ''
const statusNames = { queued: '排队中', running: '执行中', succeeded: '已完成', failed: '失败', cancelled: '已取消' }
const kindNames = { paper_generate: '用户出卷', template_validate: '模板验证', template_preview: '模板预览' }
const validationNames = { queued: '排队中', running: '验证中', passed: '通过', failed: '不通过', stale: '已过期' }
const difficultyNames = { basic: '基础', standard: '提高', challenge: '挑战' }
const phaseNames = { queued: '排队', generating: '生成或验证', rendering: 'PDF排版', saving: '保存', done: '结束' }
function message(cause: unknown) { return cause instanceof ApiError ? cause.message : '记录加载失败，请重试。' }
async function search() {
  if (busy.value) return
  busy.value = true; error.value = ''; selected.value = null; records.value = null
  const dates = new URLSearchParams()
  if (dateFrom.value) dates.set('date_from', dateFrom.value)
  if (dateTo.value) dates.set('date_to', dateTo.value)
  const filters = new URLSearchParams(dates)
  if (kind.value) filters.set('kind', kind.value)
  if (status.value) filters.set('status', status.value)
  try {
    const jobs = await requestData<AdminJobList>('/admin/api/v1/jobs?' + filters)
    records.value = jobs
    dateFrom.value = jobs.date_from; dateTo.value = jobs.date_to
    filters.set('date_from', jobs.date_from); filters.set('date_to', jobs.date_to)
    applied = filters.toString()
  } catch (cause) { error.value = message(cause) }
  finally { busy.value = false }
}
async function more() {
  if (busy.value || !records.value?.next_cursor) return
  busy.value = true; error.value = ''
  const query = new URLSearchParams(applied)
  query.set('cursor', records.value.next_cursor)
  try {
    const next = await requestData<AdminJobList>('/admin/api/v1/jobs?' + query)
    records.value = { ...next, items: [...records.value.items, ...next.items.filter(row => !records.value!.items.some(old => old.id === row.id))] }
  } catch (cause) { error.value = message(cause) }
  finally { busy.value = false }
}
async function detail(id: string) {
  if (busy.value) return
  busy.value = true; error.value = ''; selected.value = null
  try { selected.value = await requestData<AdminJobDetail>('/admin/api/v1/jobs/' + id) }
  catch (cause) { error.value = message(cause) }
  finally { busy.value = false }
}
function openTemplate(job: AdminJobSummary) {
  if (job.template_id && job.template_version_id) emit('openTemplate', job.template_id, job.template_version_id)
}
onMounted(search)
</script>

<template>
  <section class="card" aria-labelledby="operations-heading">
    <h2 id="operations-heading">生成记录</h2>
    <p class="muted">默认最近7天，单次最多93天。修改条件后点击查询。</p>
    <form @submit.prevent="search">
      <fieldset :disabled="busy" class="filters">
        <label>开始日期 <input v-model="dateFrom" type="date"></label>
        <label>结束日期 <input v-model="dateTo" type="date"></label>
        <label>任务类型 <select v-model="kind"><option value="">全部任务</option><option value="paper_generate">用户出卷</option><option value="template_validate">模板验证</option><option value="template_preview">模板预览</option></select></label>
        <label>任务状态 <select v-model="status"><option value="">全部状态</option><option v-for="(name, value) in statusNames" :key="value" :value="value">{{ name }}</option></select></label>
        <button type="submit">{{ busy ? '查询中……' : '查询记录' }}</button>
      </fieldset>
    </form>
    <p v-if="error" role="alert">{{ error }}</p>
    <template v-if="records">
      <h3>任务记录</h3>
      <p class="muted">按提交时间倒序。验证任务“已完成”表示执行结束，是否通过以验证结论为准。</p>
      <p v-if="!records.items.length">此条件下暂无任务。</p>
      <div v-else class="table-scroll"><table>
        <caption>生成与验证任务</caption>
        <thead><tr><th>提交时间</th><th>类型／状态</th><th>模板／题量</th><th>尝试</th><th>操作</th></tr></thead>
        <tbody><tr v-for="job in records.items" :key="job.id">
          <td>{{ formatBeijingTime(job.created_at) }}</td>
          <td>{{ kindNames[job.kind] }} · {{ statusNames[job.status] }}<p v-if="job.validation_status">验证：{{ validationNames[job.validation_status] }}</p><p v-if="job.error_message">{{ job.error_message }}</p></td>
          <td>{{ job.template_name ?? '暂无模板关联' }}<span v-if="job.version_no"> · 第{{ job.version_no }}版</span><p v-if="job.total_count !== null">{{ job.difficulty ? difficultyNames[job.difficulty] : '' }} · {{ job.total_count }}题</p></td>
          <td>{{ job.attempt }} / {{ job.max_attempts }}</td>
          <td><button :disabled="busy" @click="detail(job.id)">查看任务</button></td>
        </tr></tbody>
      </table></div>
      <button v-if="records.has_more" :disabled="busy" @click="more">加载更多记录</button>
    </template>
  </section>
  <section v-if="selected" class="card" aria-labelledby="job-detail-heading">
    <h2 id="job-detail-heading">任务详情</h2>
    <div v-if="selected.job.status === 'queued'"><label :for="uid+'-cancel'">取消任务理由</label><input :id="uid+'-cancel'" v-model="cancelReason" maxlength="2000"><button :disabled="busy||!cancelReason.trim()" @click="cancelSelected">取消排队任务</button></div>
    <p class="identifier">任务编号：{{ selected.job.id }}</p>
    <p>{{ kindNames[selected.job.kind] }} · {{ statusNames[selected.job.status] }} · {{ phaseNames[selected.job.phase] }}</p>
    <p>开始时间：{{ selected.job.started_at ? formatBeijingTime(selected.job.started_at) : '尚未开始' }}；结束时间：{{ selected.job.finished_at ? formatBeijingTime(selected.job.finished_at) : '尚未结束' }}</p>
    <p v-if="selected.job.error_code">{{ selected.job.error_code }}：{{ selected.job.error_message }}</p>
    <p v-if="selected.job.paper_id" class="identifier">试卷编号：{{ selected.job.paper_id }} · {{ selected.job.paper_status === 'active' ? '可用' : '已撤下' }}</p>
    <p v-if="selected.job.theme_name">主题：{{ selected.job.theme_name }}</p>
    <button v-if="selected.job.template_id" @click="openTemplate(selected.job)">查看来源模板版本</button>
    <template v-if="selected.questions.length">
      <h3>已保存的题目快照</h3>
      <QuestionSections :questions="selected.questions" show-answers />
    </template>
    <template v-if="selected.validation">
      <h3>验证结论：{{ validationNames[selected.validation.status] }}</h3>
      <template v-if="selected.validation.report">
        <p>检查 {{ selected.validation.report.sample_count }} 道题，失败检查 {{ selected.validation.report.failure_count }} 次。</p>
        <ul><li v-for="(failure, index) in selected.validation.report.failures" :key="index">{{ failure.error_code }}：{{ failure.message }}</li></ul>
        <p v-if="selected.validation.report.failures_truncated">失败列表已截断。</p>
        <h4 v-if="selected.validation.report.samples?.length">一、{{ selected.validation.report.samples[0]?.question_type === 'fill' ? '填空题' : ( selected.validation.report.samples[0]?.question_type === 'choice' ? '选择题' : '竖式计算') }}</h4>
        <QuestionRenderer v-for="(question, index) in selected.validation.report.samples" :key="question.id" :question="{ ...question, position: index + 1 }" show-answers />
      </template>
    </template>
  </section>
</template>

<style scoped>
form { max-width: none; }
.filters { display: flex; flex-wrap: wrap; gap: 12px; align-items: end; border: 0; padding: 0; }
label { display: flex; flex-direction: column; gap: 6px; }
select { padding: 10px; border: 1px solid var(--papr-border); border-radius: 8px; }
.totals { display: flex; flex-wrap: wrap; gap: 24px; }
dd { margin: 6px 0; font-size: 24px; font-weight: 600; }
.table-scroll { overflow-x: auto; margin: 16px 0; }
table { border-collapse: collapse; width: 100%; text-align: left; }
caption { text-align: left; font-weight: 600; margin-bottom: 10px; }
th, td { padding: 12px 8px; border-bottom: 1px solid var(--papr-border); vertical-align: top; }
td p { margin: 4px 0; }
.identifier { overflow-wrap: anywhere; }
</style>
