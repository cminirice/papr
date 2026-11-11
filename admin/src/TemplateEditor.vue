<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ApiError, requestData } from '@papr/shared/api'
import { formatBeijingTime } from '@papr/shared/time'
import type { CsrfToken, DraftDetail, FixedCaseInput, MultiplicationProfile, QuestionLayout, TemplateDetail, ReleaseContext } from '@papr/shared/contracts'
import ValidationPanel from './ValidationPanel.vue'
import PreviewPanel from './PreviewPanel.vue'

const props = defineProps<{ templateId: string; csrfToken: string; initialVersionId?: string }>()
const emit = defineEmits<{ saved: [] }>()
type ProfileForm = Omit<MultiplicationProfile, 'layout' | 'max_per_paper'> & { layout: Required<QuestionLayout>; max_per_paper: number }
const template = ref<TemplateDetail | null>(null)
const draft = ref<DraftDetail | null>(null)
const versionId = ref(props.initialVersionId ?? '')
const profiles = ref<ProfileForm[]>([])
const cases = ref<FixedCaseInput[]>([])
const busy = ref(false)
const error = ref('')
const notice = ref('')
const csrf = ref(props.csrfToken)

function show(data: DraftDetail) {
  draft.value = data
  profiles.value = data.config.profiles.map(profile => ({ ...profile,
    max_per_paper: profile.max_per_paper ?? 12,
    layout: { questions_per_row: profile.layout?.questions_per_row ?? 2, solutions_per_row: profile.layout?.solutions_per_row ?? 1, answer_space_mm: profile.layout?.answer_space_mm ?? 35, keep_together: true, diagram_size_mm: null },
  }))
  cases.value = structuredClone(data.config.test_cases)
}
async function reload() {
  if (busy.value) return
  busy.value = true
  error.value = ''; notice.value = ''
  draft.value = null
  try {
    template.value = await requestData<TemplateDetail>(`/admin/api/v1/templates/${props.templateId}`)
    versionId.value ||= template.value.versions.find(v => v.status === 'draft')?.id ?? template.value.versions[0]?.id ?? ''
    if (versionId.value) show(await requestData<DraftDetail>(`/admin/api/v1/template-versions/${versionId.value}`))
  } catch (cause) {
    error.value = cause instanceof ApiError ? cause.message : '草稿加载失败，请重试。'
  } finally { busy.value = false }
}
async function save() {
  if (busy.value || !draft.value?.editable) return
  busy.value = true; error.value = ''; notice.value = ''
  const send = () => requestData<DraftDetail>(`/admin/api/v1/template-versions/${draft.value!.id}`, {
    method: 'PATCH', body: { profiles: profiles.value, test_cases: cases.value },
    csrf: csrf.value, ifMatch: `"${draft.value!.lock_version}"`,
  })
  try {
    let result: DraftDetail
    try { result = await send() }
    catch (cause) {
      if (!(cause instanceof ApiError && cause.code === 'CSRF_INVALID')) throw cause
      csrf.value = (await requestData<CsrfToken>('/admin/api/v1/session/csrf', { body: {} })).csrf_token
      result = await send()
    }
    show(result)
    notice.value = '草稿已保存。已有有效题量已清空，后续须重新验证和审题。'
    emit('saved')
  } catch (cause) {
    error.value = cause instanceof ApiError ? cause.message : '未确认保存结果，请重新加载核对；当前输入已保留。'
  } finally { busy.value = false }
}
function addCase() {
  if (cases.value.length >= 30) return
  let number = cases.value.length + 1
  while (cases.value.some(item => item.code === `CASE_${number}`)) number++
  cases.value.push({ code: `CASE_${number}`, difficulty: profiles.value[0]?.difficulty ?? 'basic', params: { a: 123, b: 12 }, expected_answer: profiles.value[0]?.task === 'missing_digit' ? '2' : profiles.value[0]?.task === 'error_choice' ? '十位部分积没有按十位对齐' : '1476' })
}
async function clonePublished() {
  if (busy.value || !draft.value || draft.value.status !== 'published') return
  busy.value = true; error.value = ''; notice.value = ''
  const source = draft.value
  try {
    const context = await requestData<ReleaseContext>(`/admin/api/v1/template-versions/${source.id}/release-context`)
    const send = () => requestData<DraftDetail>(`/admin/api/v1/templates/${source.template_id}/versions`, {
      body: { source_version_id: source.id }, csrf: csrf.value, ifMatch: `"${context.template_lock_version}"`,
    })
    let created: DraftDetail
    try { created = await send() }
    catch (cause) {
      if (!(cause instanceof ApiError && cause.code === 'CSRF_INVALID')) throw cause
      csrf.value = (await requestData<CsrfToken>('/admin/api/v1/session/csrf', { body: {} })).csrf_token
      created = await send()
    }
    template.value = await requestData<TemplateDetail>(`/admin/api/v1/templates/${source.template_id}`)
    versionId.value = created.id
    show(created)
    notice.value = '已复制为新草稿，需要重新验证和审题。'
    emit('saved')
  } catch (cause) { error.value = cause instanceof ApiError ? cause.message : '复制结果未确认，请重新加载核对。' }
  finally { busy.value = false }
}
onMounted(reload)
</script>

<template>
  <section class="card" aria-labelledby="editor-heading">
    <h2 id="editor-heading">{{ template?.name ?? '模板' }} · 草稿配置</h2>
    <p class="muted">当前可调整已有难度的参数、每行题数、留白和固定用例。固定样例检查通过不代表完成批量验证或人工审题。</p>
    <p v-if="error" role="alert">{{ error }}</p>
    <p v-if="notice" role="status">{{ notice }}</p>
    <button type="button" :disabled="busy" @click="reload">重新加载（放弃未保存修改）</button>
    <button v-if="draft?.status === 'published'" type="button" :disabled="busy" @click="clonePublished">复制为新草稿</button>
    <label v-if="template?.versions.length">版本
      <select v-model="versionId" :disabled="busy" @change="reload">
        <option v-for="version in template.versions" :key="version.id" :value="version.id">第{{ version.version_no }}版 · {{ version.status === 'draft' ? '草稿' : version.status === 'published' ? '已发布' : '已退役' }}</option>
      </select>
    </label>
    <form v-if="draft" @submit.prevent="save">
      <p>最近更新：{{ formatBeijingTime(draft.updated_at) }}</p>
      <p v-if="!draft.editable">此版本当前不可编辑。</p>
      <fieldset :disabled="busy || !draft.editable">
        <legend>难度与参数</legend>
        <section v-for="profile in profiles" :key="profile.difficulty" class="profile-grid">
          <h3>{{ profile.difficulty === 'basic' ? '基础' : profile.difficulty === 'standard' ? '提高' : '挑战' }}</h3>
          <label>三位数下限 <input v-model.number="profile.a_min" type="number" min="100" max="999" required></label>
          <label>三位数上限 <input v-model.number="profile.a_max" type="number" min="100" max="999" required></label>
          <label>两位数下限 <input v-model.number="profile.b_min" type="number" min="11" max="99" required></label>
          <label>两位数上限 <input v-model.number="profile.b_max" type="number" min="11" max="99" required></label>
          <label>进位次数上限 <input v-model.number="profile.max_carry_events" type="number" min="0" :max="profile.difficulty === 'basic' ? 2 : 9" required></label>
          <label>单卷题量上限 <input v-model.number="profile.max_per_paper" type="number" min="1" max="12" required></label>
          <label>题目每行题数 <select v-model.number="profile.layout.questions_per_row"><option v-for="count in 5" :key="count" :value="count">{{ count }}道</option></select></label>
          <label>解析每行题数 <select v-model.number="profile.layout.solutions_per_row"><option v-for="count in 5" :key="count" :value="count">{{ count }}道</option></select></label>
          <label>答题留白（毫米） <input v-model.number="profile.layout.answer_space_mm" type="number" min="20" max="100" required></label>
          <p class="muted">普通竖式题按完整答题区域计高，包含已给出的两行竖式；其他题型按额外留白计高。</p>
          <label>允许因数含零 <input v-model="profile.allow_zero" type="checkbox" :disabled="profile.difficulty === 'basic'"></label>
        </section>
      </fieldset>
      <fieldset :disabled="busy || !draft.editable">
        <legend>固定用例（{{ cases.length }}/30）</legend>
        <section v-for="(item, index) in cases" :key="index" class="case-grid">
          <label>编码 <input v-model="item.code" pattern="[A-Z][A-Z0-9_]{0,63}" required></label>
          <label>难度 <select v-model="item.difficulty"><option v-for="p in profiles" :key="p.difficulty" :value="p.difficulty">{{ p.difficulty === 'basic' ? '基础' : p.difficulty === 'standard' ? '提高' : '挑战' }}</option></select></label>
          <label>三位数 <input v-model.number="item.params.a" type="number" min="100" max="999" required></label>
          <label>两位数 <input v-model.number="item.params.b" type="number" min="11" max="99" required></label>
          <label>预期答案 <input v-model="item.expected_answer" maxlength="100" required></label>
          <button type="button" @click="cases.splice(index, 1)">移除此用例</button>
        </section>
        <button type="button" :disabled="cases.length >= 30" @click="addCase">添加固定用例</button>
      </fieldset>
      <button type="submit" :disabled="busy || !draft.editable">{{ busy ? '处理中……' : '保存草稿' }}</button>
    </form>
    <PreviewPanel v-if="draft" :key="draft.id" :draft="draft" :csrf-token="csrf" />
    <ValidationPanel v-if="draft" :version-id="draft.id" :lock-version="draft.lock_version" :content-hash="draft.content_hash" :csrf-token="csrf" :editable="draft.editable && !busy" @released="reload(); emit('saved')" />
  </section>
</template>

<style scoped>
fieldset { border: 1px solid #dce6e3; border-radius: 8px; margin: 16px 0; padding: 16px; }
.profile-grid, .case-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; padding: 12px 0; }
h3 { grid-column: 1 / -1; }
label { display: flex; flex-direction: column; gap: 6px; }
input[type="checkbox"] { width: 22px; height: 22px; }
select { padding: 10px; border: 1px solid #dce6e3; border-radius: 6px; background: white; }
</style>
