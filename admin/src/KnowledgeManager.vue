<script setup lang="ts">
import { computed, onMounted, ref, useId } from 'vue'
import { ApiError, requestData } from '@papr/shared/api'
import type { KnowledgeCreate, KnowledgeContent, KnowledgeDetail, KnowledgeList, KnowledgeView,
  ObjectiveContent, ObjectiveDetail, ObjectiveList, ObjectiveView, SourceView, SourceList } from '@papr/shared/contracts'
import { useAdminWrite } from './useAdminWrite'
const props = defineProps<{ csrfToken: string }>()
const uid = useId(), send = useAdminWrite(props.csrfToken)
const points = ref<KnowledgeDetail[]>([]), pointTotal = ref(0), point = ref<KnowledgeDetail | null>(null)
const sources = ref<SourceView[]>([]), sourceTotal = ref(0)
const objectives = ref<ObjectiveDetail[]>([]), objectiveTotal = ref(0), objective = ref<ObjectiveDetail | null>(null)
const revisionId = ref(''), objectiveRevisionId = ref('')
const revision = computed(() => point.value?.revisions.find(r => r.id === revisionId.value))
const objectiveRevision = computed(() => objective.value?.revisions.find(r => r.id === objectiveRevisionId.value))
const code = ref(''), domain = ref<KnowledgeCreate['domain']>('operation')
const name = ref(''), definition = ref(''), boundary = ref(''), aliases = ref(''), misconceptions = ref(''), sourceId = ref('')
const objectiveCode = ref(''), objectiveName = ref(''), scope = ref(''), criteria = ref(''), prerequisites = ref(''), knowledgeId = ref('')
const reason = ref(''), error = ref(''), notice = ref(''), busy = ref(false)
const knowledgeChecked = ref(false), objectiveChecked = ref(false)
const lines = (text: string) => text.split('\n').map(s => s.trim()).filter(Boolean)
function knowledgeContent(): KnowledgeContent {
  return { name: name.value, aliases: lines(aliases.value), definition: definition.value, boundary: boundary.value,
    misconceptions: lines(misconceptions.value), source_id: sourceId.value || null }
}
function objectiveContent(): ObjectiveContent {
  return { knowledge_revision_id: knowledgeId.value, name: objectiveName.value, scope: scope.value,
    success_criteria: lines(criteria.value), allowed_prerequisites: lines(prerequisites.value) }
}
const knowledgeDirty = computed(() => !!revision.value && JSON.stringify(knowledgeContent()) !== JSON.stringify(revision.value.content))
const objectiveDirty = computed(() => !!objectiveRevision.value && JSON.stringify(objectiveContent()) !== JSON.stringify(objectiveRevision.value.content))
async function run(action: () => Promise<void>) {
  if (busy.value) return
  busy.value = true; error.value = ''; notice.value = ''
  try { await action() } catch (cause) { error.value = cause instanceof ApiError ? cause.message : '内容操作失败，请重新加载后重试。' }
  finally { busy.value = false }
}
async function loadPoints(more = false) {
  const result = await requestData<KnowledgeList>('/admin/api/v1/knowledge-points?limit=50&offset=' + (more ? points.value.length : 0))
  points.value = more ? [...points.value, ...result.items] : result.items; pointTotal.value = result.total
}
async function loadSources(more = false) {
  const result = await requestData<SourceList>('/admin/api/v1/sources?limit=100&offset=' + (more ? sources.value.length : 0))
  sources.value = more ? [...sources.value, ...result.items] : result.items; sourceTotal.value = result.total
}
async function loadObjectives(more = false) {
  if (!point.value) return
  const result = await requestData<ObjectiveList>(`/admin/api/v1/knowledge-points/${point.value.id}/objectives?limit=50&offset=` + (more ? objectives.value.length : 0))
  objectives.value = more ? [...objectives.value, ...result.items] : result.items; objectiveTotal.value = result.total
}
function chooseRevision() {
  const content = revision.value?.content
  name.value = content?.name ?? ''; definition.value = content?.definition ?? ''; boundary.value = content?.boundary ?? ''
  aliases.value = content?.aliases?.join('\n') ?? ''; misconceptions.value = content?.misconceptions?.join('\n') ?? ''
  sourceId.value = content?.source_id ?? ''; knowledgeChecked.value = false
}
function chooseObjectiveRevision() {
  const content = objectiveRevision.value?.content
  objectiveName.value = content?.name ?? ''; scope.value = content?.scope ?? ''; criteria.value = content?.success_criteria.join('\n') ?? ''
  prerequisites.value = content?.allowed_prerequisites?.join('\n') ?? ''; knowledgeId.value = content?.knowledge_revision_id ?? revisionId.value
  objectiveChecked.value = false
}
function chooseObjective(value: ObjectiveDetail | null) {
  objective.value = value; objectiveCode.value = value?.code ?? ''; objectiveRevisionId.value = value?.revisions[0]?.id ?? ''
  chooseObjectiveRevision()
}
async function choosePoint(value: KnowledgeDetail | null, selectedRevision?: string) {
  point.value = value; code.value = value?.code ?? ''; domain.value = (value?.domain ?? 'operation') as KnowledgeCreate['domain']
  revisionId.value = selectedRevision ?? value?.revisions[0]?.id ?? ''; chooseRevision()
  objectives.value = []; objectiveTotal.value = 0; chooseObjective(null)
  if (value) await loadObjectives()
}
function savePoint() {
  void run(async () => {
    if (point.value && revision.value) {
      const result = await send<KnowledgeView>('/admin/api/v1/knowledge-revisions/' + revision.value.id,
        { ...knowledgeContent(), reason: reason.value }, 'PATCH', revision.value.lock_version)
      await choosePoint(await requestData<KnowledgeDetail>('/admin/api/v1/knowledge-points/' + point.value.id), result.id)
    } else await choosePoint(await send<KnowledgeDetail>('/admin/api/v1/knowledge-points',
      { code: code.value, domain: domain.value, content: knowledgeContent(), reason: reason.value }))
    await loadPoints(); notice.value = '知识点草稿已保存，尚未发布。'
  })
}
function copyPoint() {
  void run(async () => {
    if (!point.value || !revision.value) return
    const result = await send<KnowledgeDetail>(`/admin/api/v1/knowledge-points/${point.value.id}/revisions`,
      { source_revision_id: revision.value.id, reason: reason.value }, 'POST', point.value.lock_version)
    await choosePoint(result); await loadPoints(); notice.value = '已复制知识点新草稿，原发布修订保持不变。'
  })
}
function publishPoint() {
  void run(async () => {
    if (!point.value || !revision.value || knowledgeDirty.value || !knowledgeChecked.value) return
    const id = revision.value.id
    await send(`/admin/api/v1/knowledge-revisions/${id}/publish`, { content_hash: revision.value.content_hash, reason: reason.value }, 'POST', revision.value.lock_version)
    await choosePoint(await requestData<KnowledgeDetail>('/admin/api/v1/knowledge-points/' + point.value.id), id)
    await loadPoints(); notice.value = '知识点修订已发布。目录映射和模板关联需按修订分别维护。'
  })
}
function saveObjective() {
  void run(async () => {
    if (!point.value) return
    if (objective.value && objectiveRevision.value) {
      const saved = await send<ObjectiveView>('/admin/api/v1/objective-revisions/' + objectiveRevision.value.id,
        { ...objectiveContent(), reason: reason.value }, 'PATCH', objectiveRevision.value.lock_version)
      chooseObjective(await requestData<ObjectiveDetail>('/admin/api/v1/objectives/' + objective.value.id))
      objectiveRevisionId.value = saved.id; chooseObjectiveRevision()
    } else chooseObjective(await send<ObjectiveDetail>(`/admin/api/v1/knowledge-points/${point.value.id}/objectives`,
      { code: objectiveCode.value, content: objectiveContent(), reason: reason.value }))
    await loadObjectives(); notice.value = '训练目标草稿已保存，尚未发布。'
  })
}
function copyObjective() {
  void run(async () => {
    if (!objective.value || !objectiveRevision.value) return
    chooseObjective(await send<ObjectiveDetail>(`/admin/api/v1/objectives/${objective.value.id}/revisions`,
      { source_revision_id: objectiveRevision.value.id, reason: reason.value }, 'POST', objective.value.lock_version))
    await loadObjectives(); notice.value = '已复制训练目标新草稿。'
  })
}
function publishObjective() {
  void run(async () => {
    if (!objective.value || !objectiveRevision.value || objectiveDirty.value || !objectiveChecked.value) return
    const id = objectiveRevision.value.id
    await send(`/admin/api/v1/objective-revisions/${id}/publish`, { content_hash: objectiveRevision.value.content_hash, reason: reason.value }, 'POST', objectiveRevision.value.lock_version)
    chooseObjective(await requestData<ObjectiveDetail>('/admin/api/v1/objectives/' + objective.value.id))
    objectiveRevisionId.value = id; chooseObjectiveRevision(); await loadObjectives(); notice.value = '训练目标修订已发布。'
  })
}
onMounted(() => run(async () => { await loadPoints(); await loadSources() }))
</script>

<template>
  <section class="card" :aria-labelledby="uid + '-title'"><h2 :id="uid + '-title'">知识点与训练目标维护</h2>
    <p>已发布修订只读。复制新草稿后编辑、核对并单独发布；不会自动改写目录映射、模板关联或历史试卷。</p>
    <p v-if="error" role="alert">{{ error }}</p><p v-if="notice" role="status">{{ notice }}</p>
    <button :disabled="busy" @click="run(() => choosePoint(null))">新建知识点</button>
    <button :disabled="busy" @click="run(loadPoints)">刷新知识点列表</button>
    <ul><li v-for="item in points" :key="item.id">{{ item.code }} · {{ item.revisions[0]?.content.name }}
      <button :disabled="busy" @click="run(async () => choosePoint(await requestData<KnowledgeDetail>('/admin/api/v1/knowledge-points/' + item.id)))">维护{{ item.code }}</button></li></ul>
    <button v-if="points.length < pointTotal" :disabled="busy" @click="run(() => loadPoints(true))">更多知识点</button>
    <label :for="uid + '-reason'">内容变更理由</label><input :id="uid + '-reason'" v-model="reason" :disabled="busy" maxlength="2000">
    <fieldset :disabled="busy"><legend>知识点</legend>
      <label :for="uid + '-code'">知识点编码</label><input :id="uid + '-code'" v-model="code" :disabled="!!point" maxlength="64">
      <label :for="uid + '-domain'">知识领域</label><select :id="uid + '-domain'" v-model="domain" :disabled="!!point"><option value="number">数的认识</option><option value="operation">运算</option><option value="geometry">几何</option><option value="model">数量关系</option><option value="statistics">统计</option><option value="practice">综合实践</option></select>
      <template v-if="point">
        <label :for="uid + '-revision'">知识点修订</label><select :id="uid + '-revision'" v-model="revisionId" @change="chooseRevision"><option v-for="r in point.revisions" :key="r.id" :value="r.id">第{{ r.revision_no }}版 · {{ r.status === 'published' ? '已发布' : '草稿' }}{{ r.id === point.current_revision_id ? ' · 当前发布' : '' }}</option></select>
        <button @click="run(async () => choosePoint(await requestData<KnowledgeDetail>('/admin/api/v1/knowledge-points/' + point!.id), revisionId))">重新加载知识点（放弃未保存修改）</button>
      </template>
      <fieldset :disabled="revision?.status === 'published'"><legend>知识点修订内容</legend>
        <label :for="uid + '-name'">知识点名称</label><input :id="uid + '-name'" v-model="name" maxlength="120">
        <label :for="uid + '-definition'">知识点定义</label><textarea :id="uid + '-definition'" v-model="definition" maxlength="4000" />
        <label :for="uid + '-boundary'">知识边界</label><textarea :id="uid + '-boundary'" v-model="boundary" maxlength="4000" />
        <label :for="uid + '-aliases'">别名（每行一项）</label><textarea :id="uid + '-aliases'" v-model="aliases" />
        <label :for="uid + '-misconceptions'">常见误区（每行一项）</label><textarea :id="uid + '-misconceptions'" v-model="misconceptions" />
        <label :for="uid + '-source'">资料来源</label><select :id="uid + '-source'" v-model="sourceId"><option value="">暂未关联</option><option v-if="sourceId && !sources.some(s => s.id === sourceId)" :value="sourceId">原有关联来源（可加载更多）</option><option v-for="source in sources" :key="source.id" :value="source.id">{{ source.title }}</option></select>
      </fieldset>
      <button @click="run(loadSources)">刷新来源选项</button><button v-if="sources.length < sourceTotal" @click="run(() => loadSources(true))">更多来源选项</button>
      <button v-if="revision?.status !== 'published'" :disabled="!reason.trim() || !code || !name.trim() || !definition.trim() || !boundary.trim()" @click="savePoint">保存知识点草稿</button>
      <button v-if="revision" :disabled="!reason.trim()" @click="copyPoint">复制知识点修订为新草稿</button>
      <template v-if="revision?.status === 'draft'">
        <p v-if="knowledgeDirty" class="muted">内容有未保存修改，请先保存再发布。</p>
        <input :id="uid + '-knowledge-checked'" v-model="knowledgeChecked" type="checkbox"><label :for="uid + '-knowledge-checked'">我已核对知识点修订内容与边界</label>
        <button :disabled="!reason.trim() || !knowledgeChecked || knowledgeDirty" @click="publishPoint">发布知识点修订</button>
      </template>
    </fieldset>
    <fieldset v-if="point" :disabled="busy"><legend>训练目标</legend>
      <button @click="chooseObjective(null)">新建训练目标</button>
      <ul><li v-for="item in objectives" :key="item.id">{{ item.code }} <button @click="run(async () => chooseObjective(await requestData<ObjectiveDetail>('/admin/api/v1/objectives/' + item.id)))">维护目标{{ item.code }}</button></li></ul>
      <button v-if="objectives.length < objectiveTotal" @click="run(() => loadObjectives(true))">更多训练目标</button>
      <label :for="uid + '-objective-code'">目标编码</label><input :id="uid + '-objective-code'" v-model="objectiveCode" :disabled="!!objective" maxlength="64">
      <template v-if="objective"><label :for="uid + '-objective-revision'">目标修订</label><select :id="uid + '-objective-revision'" v-model="objectiveRevisionId" @change="chooseObjectiveRevision"><option v-for="r in objective.revisions" :key="r.id" :value="r.id">第{{ r.revision_no }}版 · {{ r.status === 'published' ? '已发布' : '草稿' }}{{ r.id === objective.current_revision_id ? ' · 当前发布' : '' }}</option></select></template>
      <fieldset :disabled="objectiveRevision?.status === 'published'"><legend>目标修订内容</legend>
        <label :for="uid + '-knowledge-id'">关联知识点修订</label><select :id="uid + '-knowledge-id'" v-model="knowledgeId"><option v-for="r in point.revisions" :key="r.id" :value="r.id">第{{ r.revision_no }}版 · {{ r.content.name }} · {{ r.status === 'published' ? '已发布' : '草稿' }}</option></select>
        <label :for="uid + '-objective-name'">目标名称</label><input :id="uid + '-objective-name'" v-model="objectiveName" maxlength="120">
        <label :for="uid + '-scope'">目标范围</label><textarea :id="uid + '-scope'" v-model="scope" maxlength="4000" />
        <label :for="uid + '-criteria'">达成标准（每行一项）</label><textarea :id="uid + '-criteria'" v-model="criteria" />
        <label :for="uid + '-prerequisites'">先修知识点编码（每行一项）</label><textarea :id="uid + '-prerequisites'" v-model="prerequisites" />
      </fieldset>
      <button v-if="objectiveRevision?.status !== 'published'" :disabled="!reason.trim() || !objectiveCode || !knowledgeId || !objectiveName.trim() || !scope.trim() || !criteria.trim()" @click="saveObjective">保存训练目标草稿</button>
      <button v-if="objectiveRevision" :disabled="!reason.trim()" @click="copyObjective">复制目标修订为新草稿</button>
      <template v-if="objectiveRevision?.status === 'draft'">
        <p v-if="objectiveDirty" class="muted">内容有未保存修改，请先保存再发布。</p>
        <input :id="uid + '-objective-checked'" v-model="objectiveChecked" type="checkbox"><label :for="uid + '-objective-checked'">我已核对目标范围与达成标准</label>
        <button :disabled="!reason.trim() || !objectiveChecked || objectiveDirty" @click="publishObjective">发布目标修订</button>
      </template>
    </fieldset>
  </section>
</template>
<style scoped>
fieldset { margin: 16px 0; padding: 12px; border: 1px solid #e5e7eb; min-width: 0; }
label { display: block; margin-top: 12px; }
input, select, textarea { max-width: 100%; padding: 8px; }
textarea { display: block; width: 100%; min-height: 70px; }
button { margin: 8px 8px 8px 0; }
input[type=checkbox] + label { display: inline; margin-left: 8px; }
</style>
