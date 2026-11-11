<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { ApiError, requestData } from '@papr/shared/api'
import { formatBeijingTime } from '@papr/shared/time'
import type { PaperJobView, PaperJobList, CsrfToken, PaperDetail, PaperSelection } from '@papr/shared/contracts'
import PaperPreview from './PaperPreview.vue'
const props = defineProps<{ csrfToken: string }>()
const emit = defineEmits<{ reuse: [selection: PaperSelection] }>()
const items = ref<PaperJobView[]>([])
const cursor = ref<string | null>(null)
const busy = ref(false)
const error = ref('')
const csrf = ref(props.csrfToken)
const loaded = ref(false)
const papers = ref<Record<string, PaperDetail>>({})
async function loadPaper(id: string) {
  if (busy.value) return
  busy.value = true; error.value = ''
  try { papers.value[id] = await requestData<PaperDetail>('/api/v1/papers/' + id) }
  catch (cause) { error.value = cause instanceof ApiError ? cause.message : '暂时无法加载练习，请重试。' }
  finally { busy.value = false; schedule() }
}
const statusLabels = { queued: '排队中', running: '处理中', succeeded: '已完成', failed: '未完成', cancelled: '已取消' }
const phaseLabels = { queued: '等待处理', generating: '生成题目', rendering: '排版PDF', saving: '保存文件', done: '已结束' }
let alive = true
let timer: ReturnType<typeof setTimeout> | undefined
function schedule() {
  clearTimeout(timer)
  if (alive && items.value.some(j => j.status === 'queued' || j.status === 'running')) {
    timer = setTimeout(() => { void reload() }, 3000)
  }
}
async function reload(more = false) {
  if (busy.value) return
  busy.value = true; error.value = ''
  clearTimeout(timer)
  try {
    const query = new URLSearchParams({ limit: '20' })
    if (more && cursor.value) query.set('cursor', cursor.value)
    const data = await requestData<PaperJobList>('/api/v1/jobs?' + query)
    if (!alive) return
    items.value = more ? [...items.value, ...data.items.filter(j => !items.value.some(old => old.id === j.id))] : data.items
    cursor.value = data.next_cursor
    loaded.value = true
    schedule()
  } catch (cause) {
    // Stop polling after an error; reconnect explicitly rather than interpreting network loss as failure.
    error.value = cause instanceof ApiError ? cause.message : '无法查询任务状态，请稍后刷新。网络中断不代表生成失败。'
  } finally { busy.value = false }
}
async function cancel(job: PaperJobView) {
  if (busy.value) return
  busy.value = true; error.value = ''
  clearTimeout(timer)
  const send = () => requestData<PaperJobView>(`/api/v1/jobs/${job.id}/cancel`, { body: {}, csrf: csrf.value })
  try {
    let updated: PaperJobView
    try { updated = await send() } catch (cause) {
      if (!(cause instanceof ApiError) || cause.status !== 403 || cause.code !== 'CSRF_INVALID') throw cause
      csrf.value = (await requestData<CsrfToken>('/api/v1/session/csrf', { body: {} })).csrf_token
      updated = await send()
    }
    items.value = items.value.map(j => j.id === updated.id ? updated : j)
  } catch (cause) {
    error.value = cause instanceof ApiError ? cause.message : '未确认取消结果，请刷新任务状态后再操作。'
  } finally { busy.value = false; schedule() }
}
onMounted(() => { void reload() })
onUnmounted(() => { alive = false; clearTimeout(timer) })
</script>

<template>
  <section class="card" aria-labelledby="tasks-title">
    <h2 id="tasks-title">本浏览器的任务与历史练习</h2>
    <p class="muted">只有试卷和两版PDF全部保存成功后，才开始十分钟冷却。</p>
    <button :disabled="busy" @click="reload()">{{ busy ? '查询中……' : '刷新任务' }}</button>
    <p v-if="error" role="alert">{{ error }}</p>
    <p v-if="loaded && !items.length">尚无出卷任务。生成练习后可在这里查看进度和下载PDF。</p>
    <article v-for="job in items" :key="job.id">
      <h3>{{ statusLabels[job.status] }}<span v-if="job.status === 'running'"> · {{ phaseLabels[job.phase] }}</span></h3>
      <p class="muted">提交于 {{ formatBeijingTime(job.created_at) }}</p>
      <p v-if="job.error_message" role="status">{{ job.error_message }}</p>
      <p v-if="job.status === 'cancelled'">已取消，没有新增冷却。</p>
      <div v-if="job.status === 'succeeded' && job.paper_id">
        <button v-if="!papers[job.paper_id]" :disabled="busy" @click="loadPaper(job.paper_id)">打开练习</button>
        <PaperPreview v-else :csrf-token="csrfToken" :paper="papers[job.paper_id]!" @reuse="emit('reuse', $event)" @close="delete papers[job.paper_id!]" />
      </div>
      <button v-if="job.status === 'queued'" :disabled="busy" @click="cancel(job)">取消排队</button>
    </article>
    <p v-if="cursor"><button :disabled="busy" @click="reload(true)">查看更多任务</button></p>
  </section>
</template>
<style scoped>
article { border-top: 1px solid #e5e7eb; margin-top: 16px; padding-top: 8px; }
</style>
