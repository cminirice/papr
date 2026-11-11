<script setup lang="ts">
import { onMounted, onUnmounted, ref, useId, watch } from 'vue'
import { ApiError, requestData } from '@papr/shared/api'
import { formatBeijingTime } from '@papr/shared/time'
import QuestionSections from '@papr/shared/questions'
import type { DraftDetail, PreviewRequest, PreviewView, PreviewList } from '@papr/shared/contracts'
import { useAdminWrite } from './useAdminWrite'
const props = defineProps<{ draft: DraftDetail; csrfToken: string }>()
const uid = useId(), send = useAdminWrite(props.csrfToken)
const difficulty = ref<'basic' | 'standard' | 'challenge'>(props.draft.config.profiles[0]?.difficulty ?? 'basic')
const count = ref(3), seed = ref('preview-1'), answers = ref(false)
const items = ref<PreviewView[]>([]), error = ref(''), busy = ref(false)
const pending = ref<{ key: string; body: PreviewRequest } | null>(null)
let alive = true, timer: ReturnType<typeof setTimeout> | undefined
const names = { queued: '排队中', running: '预览中', succeeded: '预览完成', failed: '预览失败', cancelled: '已取消' }
function schedule() {
  clearTimeout(timer)
  if (alive && items.value.some(j => j.status === 'queued' || j.status === 'running')) timer = setTimeout(() => { void load() }, 1500)
}
async function load() {
  if (busy.value) return
  busy.value = true; error.value = ''; clearTimeout(timer)
  try {
    const data = await requestData<PreviewList>(`/admin/api/v1/template-versions/${props.draft.id}/preview-jobs`)
    if (alive) { items.value = data.items; schedule() }
  } catch (cause) { error.value = cause instanceof ApiError ? cause.message : '无法加载预览记录，请刷新重试。' }
  finally { busy.value = false }
}
async function submit() {
  if (busy.value || (!pending.value && !props.draft.editable)) return
  pending.value ??= { key: crypto.randomUUID(), body: { lock_version: props.draft.lock_version, content_hash: props.draft.content_hash,
    difficulty: difficulty.value, count: count.value, seed: seed.value } }
  busy.value = true; error.value = ''; clearTimeout(timer)
  try {
    const job = await send<PreviewView>(`/admin/api/v1/template-versions/${props.draft.id}/preview-jobs`, pending.value.body, 'POST', undefined, pending.value.key)
    pending.value = null
    items.value = [job, ...items.value.filter(j => j.id !== job.id)].slice(0, 20)
  } catch (cause) {
    error.value = cause instanceof ApiError ? cause.message : '未确认预览提交结果，请使用同一请求编号确认。'
    if (cause instanceof ApiError && [401, 403, 409, 422, 429].includes(cause.status)) pending.value = null
    if (cause instanceof ApiError && cause.code === 'QUEUE_FULL') pending.value = null
  } finally { busy.value = false; schedule() }
}
onMounted(load)
watch(() => props.draft.lock_version, () => { void load() })
onUnmounted(() => { alive = false; clearTimeout(timer) })
</script>
<template>
  <section :aria-labelledby="uid + '-title'"><h3 :id="uid + '-title'">草稿独立预览</h3>
    <p>预览使用已保存草稿；未保存修改不参与预览。最多10题，仅供检查，不代表批量验证、人工审题或正式发布通过。</p>
    <p v-if="error" role="alert">{{ error }}</p>
    <fieldset :disabled="busy || !!pending || !draft.editable">
      <label :for="uid + '-difficulty'">预览难度</label><select :id="uid + '-difficulty'" v-model="difficulty"><option v-for="p in draft.config.profiles" :key="p.difficulty" :value="p.difficulty">{{ p.difficulty === 'basic' ? '基础' : p.difficulty === 'standard' ? '提高' : '挑战' }}</option></select>
      <label :for="uid + '-count'">预览题数</label><input :id="uid + '-count'" v-model.number="count" type="number" min="1" max="10" step="1">
      <label :for="uid + '-seed'">预览种子</label><input :id="uid + '-seed'" v-model="seed" maxlength="128">
    </fieldset>
    <button :disabled="busy || (!pending && !draft.editable) || !seed" @click="submit">{{ pending ? '确认预览提交结果' : '生成草稿预览' }}</button>
    <button :disabled="busy" @click="load">刷新预览记录</button>
    <input :id="uid + '-answers'" v-model="answers" type="checkbox"><label :for="uid + '-answers'">显示预览答案与解析</label>
    <p v-if="!items.length && !busy">暂无预览任务。</p>
    <article v-for="job in items" :key="job.id" class="preview-job">
      <h4>{{ names[job.status] }} · {{ formatBeijingTime(job.created_at) }}</h4>
      <p v-if="job.stale" role="status">草稿或关联内容已变化，这是提交时的旧快照，请重新预览。</p>
      <p v-if="job.error_code" role="alert">{{ job.error_code === 'WORKER_LOST' ? '执行服务中断，自动重试已用尽。' : '预览未完成，请核对配置后重试。' }}</p>
      <QuestionSections v-if="job.questions.length" :questions="job.questions" :show-answers="answers" />
    </article>
  </section>
</template>
<style scoped>
fieldset { border: 1px solid #e5e7eb; margin: 12px 0; }
fieldset label { display: block; margin-top: 8px; }
input, select { max-width: 100%; padding: 8px; }
button { margin: 8px; }
.preview-job { border-top: 1px solid #e5e7eb; margin-top: 16px; }
</style>
