<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { ApiError, requestData } from '@papr/shared/api'
import { formatBeijingTime } from '@papr/shared/time'
import type { CsrfToken, ValidationList, ValidationView } from '@papr/shared/contracts'
import ReviewPanel from './ReviewPanel.vue'

const props = defineProps<{ versionId: string; lockVersion: number; contentHash: string; csrfToken: string; editable: boolean }>()
const emit = defineEmits<{ released: [] }>()
const selectedRun = ref<ValidationView | null>(null)
const runs = ref<ValidationView[]>([])
const busy = ref(false)
const refreshing = ref(false)
const error = ref('')
const pendingKey = ref('')
const csrf = ref(props.csrfToken)
const labels = { queued: '排队中', running: '验证中', passed: '通过', failed: '失败', stale: '已过期' }
let timer: ReturnType<typeof setInterval> | undefined

async function refresh() {
  if (refreshing.value) return
  refreshing.value = true
  const identity = props.versionId
  try {
    const data = await requestData<ValidationList>(`/admin/api/v1/template-versions/${identity}/validation-runs`)
    if (identity === props.versionId) runs.value = data.items
  } catch (cause) {
    error.value = cause instanceof ApiError ? cause.message : '验证记录加载失败，请重试。'
  } finally { refreshing.value = false }
}
async function submit() {
  if (busy.value || !props.editable) return
  busy.value = true; error.value = ''
  pendingKey.value ||= crypto.randomUUID()
  const identity = props.versionId
  const key = pendingKey.value
  const body = { lock_version: props.lockVersion, content_hash: props.contentHash }
  const send = () => requestData<ValidationView>(`/admin/api/v1/template-versions/${identity}/validation-jobs`, {
    body, csrf: csrf.value, idempotencyKey: key,
  })
  try {
    let accepted: ValidationView
    try { accepted = await send() }
    catch (cause) {
      if (!(cause instanceof ApiError && cause.code === 'CSRF_INVALID')) throw cause
      csrf.value = (await requestData<CsrfToken>('/admin/api/v1/session/csrf', { body: {} })).csrf_token
      accepted = await send()
    }
    if (identity === props.versionId) runs.value = [accepted, ...runs.value.filter(item => item.id !== accepted.id)].slice(0, 20)
    if (pendingKey.value === key) pendingKey.value = ''
  } catch (cause) {
    error.value = cause instanceof ApiError ? cause.message : '未确认是否受理，请重试；将沿用原请求标识。'
  } finally { busy.value = false }
}
watch(() => [props.versionId, props.lockVersion, props.contentHash], () => {
  pendingKey.value = ''; selectedRun.value = null; error.value = ''; void refresh()
})
onMounted(() => {
  void refresh()
  timer = setInterval(() => {
    if (runs.value.some(run => run.job_status === 'queued' || run.job_status === 'running')) void refresh()
  }, 3000)
})
onUnmounted(() => clearInterval(timer))
</script>

<template>
  <section aria-labelledby="validation-heading">
    <h3 id="validation-heading">批量验证</h3>
    <p class="muted">验证已保存的草稿，每档检查100个随机样例和多个题量的整卷去重。通过后仍需人工审题与PDF样张检查。</p>
    <button type="button" :disabled="busy || !editable || runs.some(run => run.job_status === 'queued' || run.job_status === 'running')" @click="submit">{{ busy ? '提交中……' : '验证已保存草稿' }}</button>
    <button type="button" :disabled="refreshing" @click="refresh">刷新验证记录</button>
    <p v-if="error" role="alert">{{ error }}</p>
    <p v-if="!runs.length">暂无验证记录。</p>
    <article v-for="run in runs" :key="run.id" class="validation-result">
      <h4>{{ labels[run.status] }} · {{ formatBeijingTime(run.created_at) }}</h4>
      <p v-if="run.job_status === 'queued'">等待验证服务处理。</p>
      <p v-if="run.job_status === 'running'">正在执行第{{ run.attempt }}次尝试。</p>
      <p v-if="run.status === 'stale'">该报告已不适用于当前草稿，不会更新当前有效题量。</p>
      <p v-if="run.error_code">执行错误：{{ run.error_code }}。任务终止后可重新发起验证。</p>
      <template v-if="run.report">
        <button v-if="run.status === 'passed' && run.content_hash === contentHash" type="button" @click="selectedRun = run">查看样题与发布</button>
        <p>已检查{{ run.report.sample_count }}道题；失败检查{{ run.report.failure_count }}次。</p>
        <ul>
          <li v-for="item in run.report.coverage" :key="item.difficulty">
            {{ item.difficulty === 'basic' ? '基础' : '提高' }}：合法参数{{ item.exact_capacity }}组；
            通过题量{{ item.checked_count_options.join('、') || '无' }}。
          </li>
        </ul>
        <details v-if="run.report.failures.length">
          <summary>查看失败样例（{{ run.report.failures.length }}条{{ run.report.failures_truncated ? '，已截断' : '' }}）</summary>
          <ul><li v-for="(item, index) in run.report.failures" :key="index">{{ item.difficulty === 'basic' ? '基础' : '提高' }} · {{ item.case_code ?? item.seed ?? '题量检查' }}：{{ item.message }}</li></ul>
        </details>
      </template>
    </article>
    <p v-if="runs.length >= 20" class="muted">展示最近20条记录。</p>
    <ReviewPanel v-if="selectedRun" :key="selectedRun.id" :run="selectedRun" :version-lock="lockVersion" :csrf-token="csrf" :editable="editable" @released="emit('released')" />
  </section>
</template>

<style scoped>
.validation-result { border-top: 1px solid #dce6e3; margin-top: 16px; }
button { margin: 0 8px 8px 0; }
</style>
