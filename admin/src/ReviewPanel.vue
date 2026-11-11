<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ApiError, requestData } from '@papr/shared/api'
import QuestionSections from '@papr/shared/questions'
import type { CsrfToken, DependencyView, ReleaseContext, ReviewView, ValidationView } from '@papr/shared/contracts'

const props = defineProps<{ run: ValidationView; versionLock: number; csrfToken: string; editable: boolean }>()
const emit = defineEmits<{ released: [] }>()
const context = ref<ReleaseContext | null>(null)
const busy = ref(false)
const error = ref('')
const notice = ref('')
const comment = ref('')
const reason = ref('')
const checkedSamples = ref<string[]>([])
const printChecked = ref(false)
const decision = ref<'approved' | 'rejected'>('rejected')
const csrf = ref(props.csrfToken)
const showAnswers = ref(true)
const latestReview = computed(() => context.value?.reviews.find(item => item.content_hash === props.run.content_hash))

async function load() {
  context.value = await requestData<ReleaseContext>(`/admin/api/v1/template-versions/${props.run.template_version_id}/release-context`)
}
async function post<T>(path: string, body: object, lock: number): Promise<T> {
  const send = () => requestData<T>(path, { body, csrf: csrf.value, ifMatch: `"${lock}"` })
  try { return await send() }
  catch (cause) {
    if (!(cause instanceof ApiError && cause.code === 'CSRF_INVALID')) throw cause
    csrf.value = (await requestData<CsrfToken>('/admin/api/v1/session/csrf', { body: {} })).csrf_token
    return send()
  }
}
async function perform(action: () => Promise<void>) {
  if (busy.value) return
  busy.value = true; error.value = ''; notice.value = ''
  try { await action(); await load() }
  catch (cause) { error.value = cause instanceof ApiError ? cause.message : '未确认操作结果，请刷新后核对。' }
  finally { busy.value = false }
}
function approveDependency(dependency: DependencyView) {
  void perform(async () => {
    const resource = dependency.kind === 'knowledge_revision' ? 'knowledge-revisions' : 'objective-revisions'
    await post(`/admin/api/v1/${resource}/${dependency.id}/publish`, { content_hash: dependency.content_hash, reason: reason.value }, dependency.lock_version)
    notice.value = '修订已发布。'
  })
}
function submitReview() {
  void perform(async () => {
    await post<ReviewView>(`/admin/api/v1/template-versions/${props.run.template_version_id}/reviews`, {
      validation_run_id: props.run.id, content_hash: props.run.content_hash, decision: decision.value,
      comment: comment.value, sample_refs: checkedSamples.value, print_checked: printChecked.value,
    }, props.versionLock)
    notice.value = '人工审题记录已保存；尚未发布模板。'
  })
}
function release(action: 'publish' | 'disable' | 'enable' | 'rollback') {
  void perform(async () => {
    if (!context.value) return
    const latest = context.value.reviews.find(item => item.content_hash === props.run.content_hash)
    if (action !== 'disable' && (!latest || latest.decision !== 'approved' || latest.validation_run_id !== props.run.id)) {
      throw new ApiError(409, 'CONTENT_UNAVAILABLE', '须使用此报告对应的最新人工通过记录。')
    }
    const body = action === 'disable' ? { reason: reason.value } : {
      reason: reason.value, version_id: props.run.template_version_id, validation_run_id: props.run.id, review_id: latest!.id,
    }
    await post(`/admin/api/v1/templates/${context.value.template_id}/${action}`, body, context.value.template_lock_version)
    notice.value = '模板状态已更新。'
    emit('released')
  })
}
function printSamples() {
  document.body.classList.add('printing-review')
  try { window.print() } finally { document.body.classList.remove('printing-review') }
}
onMounted(() => perform(async () => {}))
</script>

<template>
  <section class="card">
    <h3>人工审题与发布</h3>
    <p>请逐题检查题意、答案、解析和难度，并实际打印检查留白。自动验证不能代替人工审题。</p>
    <p v-if="error" role="alert">{{ error }}</p><p v-if="notice" role="status">{{ notice }}</p>
    <button type="button" :disabled="busy" @click="perform(async () => {})">刷新发布状态</button>
    <label><input v-model="showAnswers" type="checkbox">展示解析版样题</label>
    <button type="button" @click="printSamples">打印当前样题</button>
    <div class="review-print">
      <h2>纸上练 · 审题样张</h2>
      <p>{{ showAnswers ? '解析版' : '学生版' }}</p>
      <QuestionSections :questions="run.report?.samples ?? []" :show-answers="showAnswers" />
    </div>
    <form v-if="editable" @submit.prevent="submitReview">
      <fieldset :disabled="busy">
        <legend>人工检查记录</legend>
        <label v-for="(sample, index) in run.report?.samples ?? []" :key="sample.id">
          <input v-model="checkedSamples" type="checkbox" :value="sample.id">已检查样题{{ index + 1 }}：{{ sample.render_spec.multiplicand }} × {{ sample.render_spec.multiplier }}
        </label>
        <label><input v-model="printChecked" type="checkbox">已实际检查两种样张的打印排版和答题留白</label>
        <label>审题结论 <select v-model="decision"><option value="rejected">不通过</option><option value="approved">通过</option></select></label>
        <label>审题意见 <textarea v-model="comment" required maxlength="2000"></textarea></label>
        <button type="submit">记录审题结论</button>
      </fieldset>
    </form>
    <template v-if="context">
      <h4>发布前置修订</h4>
      <label>发布或状态变更理由 <textarea v-model="reason" maxlength="2000" placeholder="请填写具体理由"></textarea></label>
      <article v-for="dependency in context.dependencies" :key="dependency.id">
        <h4>{{ dependency.name }} · {{ dependency.status === 'published' ? '已发布' : '草稿' }}</h4>
        <p class="description">{{ dependency.description }}</p>
        <button v-if="dependency.status === 'draft'" type="button" :disabled="busy || !reason.trim()" @click="approveDependency(dependency)">确认并发布此修订</button>
      </article>
      <p>当前内容最近审题：{{ latestReview?.decision === 'approved' ? '通过' : latestReview ? '不通过' : '尚无记录' }}</p>
      <p v-if="latestReview">审题意见：{{ latestReview.comment }}</p>
      <button v-if="editable" type="button" :disabled="busy || !reason.trim()" @click="release('publish')">发布当前模板版本</button>
      <button v-if="context.current_published_version_id && context.template_status === 'active'" type="button" :disabled="busy || !reason.trim()" @click="release('disable')">停用模板</button>
      <button v-if="context.current_published_version_id === run.template_version_id && context.template_status === 'disabled'" type="button" :disabled="busy || !reason.trim()" @click="release('enable')">重新启用模板</button>
      <button v-if="!editable && context.current_published_version_id && context.current_published_version_id !== run.template_version_id" type="button" :disabled="busy || !reason.trim()" @click="release('rollback')">回退到此历史版本</button>
    </template>
  </section>
</template>

<style scoped>
label { display: block; margin: 10px 0; }
input[type="checkbox"] { width: auto; margin-right: 8px; }
textarea { display: block; width: 100%; min-height: 70px; }
button { margin: 8px; }
.description { white-space: pre-wrap; }
</style>
<style>
@media print {
  @page { size: A4; margin: 15mm; }
  body.printing-review * { visibility: hidden; }
  body.printing-review .review-print, body.printing-review .review-print * { visibility: visible; }
  body.printing-review .review-print { position: absolute; left: 0; top: 0; width: 100%; background: white; }
}
</style>
