<script setup lang="ts">
import { computed, onMounted, ref, useId } from 'vue'
import { ApiError, requestData } from '@papr/shared/api'
import { formatBeijingTime } from '@papr/shared/time'
import type { CatalogSummary, NodeView, PointView, CapabilityView, CsrfToken, CapabilitySelection, CreatePaperJob, PaperJobView, UserSessionView, PaperSelection } from '@papr/shared/contracts'
const props = defineProps<{ csrfToken: string }>()
const emit = defineEmits<{ submitted: [] }>()
const pending = ref<{ key: string; body: CreatePaperJob } | null>(null)
const notice = ref('')
const catalogs = ref<CatalogSummary[]>([])
const themes = ref<NodeView[]>([])
const points = ref<PointView[]>([])
const catalogId = ref('')
const themeId = ref('')
const selected = ref<string[]>([])
const difficulty = ref<CapabilitySelection['difficulty']>('basic')
const capability = ref<CapabilityView | null>(null)
const answerCount = ref(0)
const fillCount = ref(0)
const choiceCount = ref(0)
const uid = useId()
const totalCount = computed(() => answerCount.value + fillCount.value + choiceCount.value)
const feasible = computed(() => capability.value?.feasible_counts.some(c => c.choice === choiceCount.value && c.fill === fillCount.value && c.answer === answerCount.value) ?? false)
const busy = ref(false)
const error = ref('')
const csrf = ref(props.csrfToken)
const currentCatalog = computed(() => catalogs.value.find(c => c.id === catalogId.value))
async function run(action: () => Promise<void>) {
  if (busy.value) return
  busy.value = true; error.value = ''
  try { await action() } catch (cause) {
    capability.value = null
    error.value = cause instanceof ApiError ? cause.message : '内容暂时无法加载，请重试。'
  } finally { busy.value = false }
}
function clear() { capability.value = null; answerCount.value = 0; fillCount.value = 0; choiceCount.value = 0 }
function loadCatalogs() {
  void run(async () => {
    clear(); catalogId.value = ''; themeId.value = ''; themes.value = []; points.value = []; selected.value = []
    catalogs.value = await requestData<CatalogSummary[]>('/api/v1/catalogs')
  })
}
function loadThemes() {
  void run(async () => {
    clear(); themeId.value = ''; themes.value = []; points.value = []; selected.value = []
    if (catalogId.value) themes.value = await requestData<NodeView[]>(`/api/v1/catalogs/${catalogId.value}/themes`)
  })
}
function loadPoints() {
  void run(async () => {
    clear(); points.value = []; selected.value = []
    if (themeId.value) points.value = await requestData<PointView[]>(`/api/v1/themes/${themeId.value}/knowledge-points`)
  })
}
function check() {
  void run(async () => {
    clear()
    const body: CapabilitySelection = { theme_id: themeId.value, knowledge_point_ids: [...selected.value], difficulty: difficulty.value }
    capability.value = await fetchCapabilities(body)
    const initial = capability.value.feasible_counts.find(c => c.answer > 0 && !c.choice && !c.fill) ?? capability.value.feasible_counts[0]
    if (initial) { answerCount.value = initial.answer; fillCount.value = initial.fill; choiceCount.value = initial.choice }

  })
}
async function fetchCapabilities(body: CapabilitySelection) {
  const send = () => requestData<CapabilityView>('/api/v1/capabilities', { body, csrf: csrf.value })
  try { return await send() } catch (cause) {
    if (!(cause instanceof ApiError) || cause.status !== 403 || cause.code !== 'CSRF_INVALID') throw cause
    csrf.value = (await requestData<CsrfToken>('/api/v1/session/csrf', { body: {} })).csrf_token
    return send()
  }
}
async function reusePaper(selection: PaperSelection) {
  if (busy.value || pending.value) {
    error.value = '请先完成或确认当前提交，再沿用历史配置。'
    return
  }
  await run(async () => {
    clear(); notice.value = ''; catalogId.value = ''; themeId.value = ''; selected.value = []
    themes.value = []; points.value = []
    catalogs.value = await requestData<CatalogSummary[]>('/api/v1/catalogs')
    if (!catalogs.value.some(c => c.id === selection.catalog_id)) throw new ApiError(409, 'CONTENT_UNAVAILABLE', '原目录当前未开放，不能沿用配置。')
    catalogId.value = selection.catalog_id
    themes.value = await requestData<NodeView[]>(`/api/v1/catalogs/${catalogId.value}/themes`)
    if (!themes.value.some(t => t.id === selection.theme_id)) throw new ApiError(409, 'CONTENT_UNAVAILABLE', '原主题当前未开放，不能沿用配置。')
    themeId.value = selection.theme_id
    points.value = await requestData<PointView[]>(`/api/v1/themes/${themeId.value}/knowledge-points`)
    if (!selection.knowledge_point_ids.every(id => points.value.some(p => p.id === id))) {
      throw new ApiError(409, 'CONTENT_UNAVAILABLE', '原知识点当前未全部开放，请重新选择练习内容。')
    }
    selected.value = [...selection.knowledge_point_ids]; difficulty.value = selection.difficulty
    const available = await fetchCapabilities({ theme_id: themeId.value, knowledge_point_ids: selected.value, difficulty: difficulty.value })
    const counts = selection.question_type_counts
    if (!available.feasible_counts.some(c => c.choice === counts.choice && c.fill === counts.fill && c.answer === counts.answer)) {
      throw new ApiError(409, 'CONTENT_UNAVAILABLE', '原题型或题量当前不可用，请重新查询可用题量；不会自动减少题数或降低难度。')
    }
    capability.value = available; answerCount.value = counts.answer; fillCount.value = counts.fill; choiceCount.value = counts.choice
    notice.value = '已沿用原目录、知识点、难度和题量，并检查当前可用性。确认后点击“生成练习”创建新题。'
  })
}
defineExpose({ reusePaper })
async function generate() {
  if (busy.value || (!pending.value && (!capability.value || !feasible.value))) return
  if (!pending.value) pending.value = { key: crypto.randomUUID(), body: {
    theme_id: themeId.value, knowledge_point_ids: [...selected.value], difficulty: difficulty.value,
    content_epoch: capability.value!.content_epoch,
    question_type_counts: { choice: choiceCount.value, fill: fillCount.value, answer: answerCount.value },
  } }
  const attempt = pending.value
  busy.value = true; error.value = ''; notice.value = ''
  const send = () => requestData<PaperJobView>('/api/v1/paper-jobs', {
    body: attempt.body, csrf: csrf.value, idempotencyKey: attempt.key,
  })
  try {
    let job: PaperJobView
    try { job = await send() } catch (cause) {
      if (!(cause instanceof ApiError) || cause.code !== 'CSRF_INVALID') throw cause
      csrf.value = (await requestData<CsrfToken>('/api/v1/session/csrf', { body: {} })).csrf_token
      job = await send()
    }
    pending.value = null
    notice.value = job.status === 'succeeded' ? '这份练习已完成，可在下方打开。' : '任务已受理，可在下方查看进度。'
    emit('submitted')
  } catch (cause) {
    error.value = cause instanceof ApiError ? cause.message : '尚未确认提交结果，请点击“确认提交结果”，会沿用同一请求编号。'
    if (cause instanceof ApiError && ['SERVICE_NOT_READY', 'QUEUE_FULL', 'RATE_LIMITED',
      'ACTIVE_JOB_EXISTS', 'GENERATION_COOLDOWN', 'CAPABILITY_CHANGED', 'CONTENT_UNAVAILABLE',
      'UNSUPPORTED_COMBINATION', 'INVALID_CONFIG', 'SESSION_EXPIRED', 'CSRF_INVALID'].includes(cause.code)) {
      pending.value = null
      if (['CAPABILITY_CHANGED', 'CONTENT_UNAVAILABLE'].includes(cause.code)) clear()
      if (cause.code === 'ACTIVE_JOB_EXISTS') emit('submitted')
      if (cause.code === 'GENERATION_COOLDOWN') {
        try {
          const current = await requestData<UserSessionView>('/api/v1/session')
          if (current.next_generation_at) notice.value = '下次可生成时间：' + formatBeijingTime(current.next_generation_at)
        } catch { /* Keep the original admission error. */ }
      }
    }
  } finally { busy.value = false }
}
onMounted(loadCatalogs)
</script>
<template>
  <section class="card" aria-labelledby="selection-title">
    <h2 id="selection-title">选择练习内容</h2>
    <p class="muted">选择内容后生成练习；成功后可下载学生版和解析版PDF。</p>
    <button :disabled="busy || !!pending" @click="loadCatalogs">刷新目录</button>
    <p v-if="error" role="alert">{{ error }}</p>
    <p v-if="busy" role="status">正在加载……</p>
    <p v-if="!busy && !catalogs.length">首批内容正在整理，开放后会显示在这里。</p>
    <fieldset v-if="catalogs.length" :disabled="busy || !!pending">
      <label>目录 <select v-model="catalogId" @change="loadThemes"><option value="">请选择</option>
        <option v-for="catalog in catalogs" :key="catalog.id" :value="catalog.id">{{ catalog.name }}</option>
      </select></label>
      <p v-if="currentCatalog?.verification_status === 'provisional'" class="muted">此目录为候选知识目录，尚未确认与具体教材版本同步。</p>
      <label v-if="catalogId">主题 <select v-model="themeId" @change="loadPoints"><option value="">请选择</option>
        <option v-for="theme in themes" :key="theme.id" :value="theme.id">{{ theme.name }}</option>
      </select></label>
      <p v-if="catalogId && !themes.length">此目录暂无开放主题。</p>
      <div v-if="themeId">
        <p>知识点</p>
        <label v-for="point in points" :key="point.id"><input v-model="selected" :value="point.id" type="checkbox" @change="clear" />{{ point.name }}</label>
        <p v-if="!points.length">此主题暂无已发布知识点。</p>
        <label>难度 <select v-model="difficulty" @change="clear"><option value="basic">基础</option><option value="standard">提高</option><option value="challenge">挑战</option></select></label>
        <p><button :disabled="!selected.length || selected.length > 10" @click="check">查看可用题量</button></p>
      </div>
      <div v-if="capability">
        <p v-for="warning in capability.warnings" :key="warning" role="status">{{ warning }}</p>
        <template v-if="capability.feasible_counts.length">
          <template v-if="capability.count_options.answer.some(n => n > 0)">
            <label :for="uid + '-answer'">解答题</label><select :id="uid + '-answer'" v-model="answerCount"><option v-for="count in capability.count_options.answer" :key="count" :value="count">{{ count }}题</option></select>
          </template>
          <template v-if="capability.count_options.fill.some(n => n > 0)">
            <label :for="uid + '-fill'">填空题</label><select :id="uid + '-fill'" v-model="fillCount"><option v-for="count in capability.count_options.fill" :key="count" :value="count">{{ count }}题</option></select>
          </template>
          <template v-if="capability.count_options.choice.some(n => n > 0)">
            <label :for="uid + '-choice'">选择题</label><select :id="uid + '-choice'" v-model="choiceCount"><option v-for="count in capability.count_options.choice" :key="count" :value="count">{{ count }}题</option></select>
          </template>
          <p>整卷共 {{ totalCount }} 题。</p>
          <p v-if="!feasible" role="status">此题量组合暂不能覆盖所选知识点或超过可用容量，请调整各题型题数。</p>
          <p class="muted">题量为整卷各题型总数，每个所选知识点至少覆盖一道题。生成完成后开始十分钟冷却。</p>
        </template>
      </div>
    </fieldset>
    <p v-if="notice" role="status">{{ notice }}</p>
    <p v-if="pending" class="muted">正在确认这次提交，请先确认结果后再修改练习配置。</p>
    <button v-if="pending || (capability && feasible)" :disabled="busy" @click="generate">
      {{ busy ? '处理中……' : pending ? '确认提交结果' : '生成练习' }}
    </button>
  </section>
</template>
<style scoped>
fieldset { border: 0; padding: 0; margin-top: 16px; min-width: 0; }
label { display: block; margin: 12px 0; }
select { max-width: 100%; padding: 8px; margin-left: 8px; border: 1px solid #e5e7eb; border-radius: 6px; }
input[type=checkbox] { margin-right: 8px; }
</style>
