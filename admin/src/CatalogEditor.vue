<script setup lang="ts">
import { onMounted, ref, useId } from 'vue'
import { ApiError, requestData } from '@papr/shared/api'
import type { CatalogDetail, NodeView, MappingItem, MappingView, RevisionOption, RevisionOptions, CsrfToken } from '@papr/shared/contracts'
const fieldPrefix = useId()
const props = defineProps<{ catalogId: string; csrfToken: string }>()
const emit = defineEmits<{ changed: []; close: [] }>()
const catalog = ref<CatalogDetail | null>(null)
const code = ref(''), name = ref(''), term = ref<'upper' | 'lower'>('upper')
const nodes = ref<NodeView[]>([])
const node = ref<NodeView | null>(null)
const nodeCode = ref(''), nodeName = ref(''), parentId = ref('')
const nodeType = ref<'theme' | 'group'>('theme'), sortOrder = ref(0)
const mapping = ref<MappingView | null>(null)
const entries = ref<MappingItem[]>([])
const options = ref<RevisionOption[]>([]), optionsTotal = ref(0), revisionId = ref('')
const reason = ref(''), error = ref(''), notice = ref(''), busy = ref(false)
const csrf = ref(props.csrfToken)
async function run(action: () => Promise<void>) {
  if (busy.value) return
  busy.value = true; error.value = ''; notice.value = ''
  try { await action() } catch (cause) { error.value = cause instanceof ApiError ? cause.message : '操作失败，请重新加载后重试。' }
  finally { busy.value = false }
}
async function send<T>(path: string, body: object, method: 'POST' | 'PATCH' | 'PUT', lock?: number) {
  const execute = () => requestData<T>(path, { body, method, csrf: csrf.value, ...(lock ? { ifMatch: `"${lock}"` } : {}) })
  try { return await execute() } catch (cause) {
    if (!(cause instanceof ApiError) || cause.code !== 'CSRF_INVALID') throw cause
    csrf.value = (await requestData<CsrfToken>('/admin/api/v1/session/csrf', { body: {} })).csrf_token
    return execute()
  }
}
async function loadOptions(more = false) {
  const result = await requestData<RevisionOptions>('/admin/api/v1/knowledge-revision-options?limit=100&offset=' + (more ? options.value.length : 0))
  options.value = more ? [...options.value, ...result.items] : result.items
  optionsTotal.value = result.total
}
function newNode() {
  node.value = null; nodeCode.value = ''; nodeName.value = ''; parentId.value = ''; nodeType.value = 'theme'; sortOrder.value = 0
  mapping.value = null; entries.value = []; revisionId.value = ''
}
async function loadCatalog(id: string) {
  catalog.value = await requestData<CatalogDetail>('/admin/api/v1/catalogs/' + id)
  code.value = catalog.value.code; name.value = catalog.value.name; term.value = catalog.value.term
  nodes.value = await requestData<NodeView[]>(`/admin/api/v1/catalogs/${id}/nodes`)
  newNode()
}
function saveCatalog() {
  void run(async () => {
    if (catalog.value) {
      await send(`/admin/api/v1/catalogs/${catalog.value.id}`, { name: name.value, term: term.value, reason: reason.value }, 'PATCH', catalog.value.lock_version)
      await loadCatalog(catalog.value.id)
    } else {
      const result = await send<CatalogDetail>('/admin/api/v1/catalogs', { code: code.value, name: name.value, term: term.value, reason: reason.value }, 'POST')
      await loadCatalog(result.id)
    }
    emit('changed'); notice.value = '目录已保存。新目录保持草稿，开放状态请到开放设置维护。'
  })
}
async function selectNode(id: string) {
  const selected = nodes.value.find(n => n.id === id)
  if (!selected) return
  node.value = selected; nodeCode.value = selected.code; nodeName.value = selected.name
  parentId.value = selected.parent_id ?? ''; nodeType.value = selected.node_type; sortOrder.value = selected.sort_order
  mapping.value = await requestData<MappingView>(`/admin/api/v1/catalog-nodes/${id}/knowledge-mappings`)
  entries.value = mapping.value.items.map(item => ({ ...item }))
  revisionId.value = ''
}
function saveNode() {
  void run(async () => {
    if (!catalog.value) return
    let id = node.value?.id
    const fields = { name: nodeName.value, parent_id: parentId.value || null, sort_order: sortOrder.value, reason: reason.value }
    if (node.value) await send(`/admin/api/v1/catalog-nodes/${id}`, fields, 'PATCH', node.value.lock_version)
    else id = (await send<NodeView>(`/admin/api/v1/catalogs/${catalog.value.id}/nodes`, { ...fields, code: nodeCode.value, node_type: nodeType.value }, 'POST')).id
    nodes.value = await requestData<NodeView[]>(`/admin/api/v1/catalogs/${catalog.value.id}/nodes`)
    await selectNode(id!)
    emit('changed'); notice.value = '节点已保存。新节点保持草稿。'
  })
}
function addMapping() {
  if (revisionId.value && !entries.value.some(e => e.knowledge_revision_id === revisionId.value)) {
    entries.value.push({ knowledge_revision_id: revisionId.value, role: 'primary' })
    revisionId.value = ''
  }
}
function move(index: number, delta: number) {
  const other = index + delta
  if (other >= 0 && other < entries.value.length) [entries.value[index], entries.value[other]] = [entries.value[other]!, entries.value[index]!]
}
function mappingLabel(id: string) {
  const option = options.value.find(o => o.id === id)
  return option ? `${option.code} · ${option.name} · 第${option.revision_no}版（${option.status === 'published' ? '已发布' : '草稿'}）` : `未加载的修订 ${id}`
}
function saveMappings() {
  void run(async () => {
    if (!mapping.value || !catalog.value) return
    mapping.value = await send<MappingView>(`/admin/api/v1/catalog-nodes/${mapping.value.node_id}/knowledge-mappings`,
      { items: entries.value, reason: reason.value }, 'PUT', mapping.value.lock_version)
    nodes.value = await requestData<NodeView[]>(`/admin/api/v1/catalogs/${catalog.value.id}/nodes`)
    node.value = nodes.value.find(n => n.id === mapping.value!.node_id) ?? null
    emit('changed'); notice.value = '知识点映射已保存，公开能力已更新。草稿修订不会因此发布。'
  })
}
onMounted(() => run(async () => { if (props.catalogId) await loadCatalog(props.catalogId); await loadOptions() }))
</script>

<template>
  <section class="card" aria-labelledby="catalog-editor-title">
    <h2 id="catalog-editor-title">目录与节点维护</h2>
    <p>新建内容默认草稿；来源核验与内容发布分别维护。保存不会改写已有试卷。</p>
    <button :disabled="busy" @click="emit('close')">关闭目录维护</button>
    <button v-if="catalog" :disabled="busy" @click="run(() => loadCatalog(catalog!.id))">重新加载目录（放弃未保存修改）</button>
    <p v-if="error" role="alert">{{ error }}</p><p v-if="notice" role="status">{{ notice }}</p>
    <fieldset :disabled="busy">
      <div class="field"><label :for="fieldPrefix + '-reason'">变更理由</label><input :id="fieldPrefix + '-reason'" v-model="reason" maxlength="2000"></div>
      <h3>目录信息</h3>
      <div class="field"><label :for="fieldPrefix + '-catalog-code'">目录编码</label><input :id="fieldPrefix + '-catalog-code'" v-model="code" :disabled="!!catalog" maxlength="64"></div>
      <div class="field"><label :for="fieldPrefix + '-catalog-name'">目录名称</label><input :id="fieldPrefix + '-catalog-name'" v-model="name" maxlength="120"></div>
      <div class="field"><label :for="fieldPrefix + '-term'">学期</label><select :id="fieldPrefix + '-term'" v-model="term"><option value="upper">四年级上册</option><option value="lower">四年级下册</option></select></div>
      <button :disabled="!reason.trim() || !code || !name.trim()" @click="saveCatalog">保存目录</button>
      <template v-if="catalog">
        <h3>节点</h3>
        <button @click="newNode">新建节点</button>
        <ul><li v-for="item in nodes" :key="item.id">{{ item.sort_order }} · {{ item.name }}（{{ item.node_type === 'theme' ? '主题' : '分组' }}）
          <button @click="run(() => selectNode(item.id))">编辑{{ item.name }}</button>
        </li></ul>
        <div class="field"><label :for="fieldPrefix + '-node-code'">节点编码</label><input :id="fieldPrefix + '-node-code'" v-model="nodeCode" :disabled="!!node" maxlength="64"></div>
        <div class="field"><label :for="fieldPrefix + '-node-name'">节点名称</label><input :id="fieldPrefix + '-node-name'" v-model="nodeName" maxlength="120"></div>
        <div class="field"><label :for="fieldPrefix + '-node-type'">节点类型</label><select :id="fieldPrefix + '-node-type'" v-model="nodeType" :disabled="!!node"><option value="theme">主题</option><option value="group">分组</option></select></div>
        <div class="field"><label :for="fieldPrefix + '-parent'">父节点</label><select :id="fieldPrefix + '-parent'" v-model="parentId"><option value="">顶层</option><option v-for="item in nodes.filter(n => n.id !== node?.id)" :key="item.id" :value="item.id">{{ item.name }}</option></select></div>
        <div class="field"><label :for="fieldPrefix + '-sort'">排序值（越小越靠前）</label><input :id="fieldPrefix + '-sort'" v-model.number="sortOrder" type="number" min="0" max="100000" step="1"></div>
        <button :disabled="!reason.trim() || !nodeCode || !nodeName.trim()" @click="saveNode">保存节点</button>
      </template>
      <template v-if="mapping">
        <h3>当前节点的知识点映射</h3>
        <p class="muted">仅编辑当前节点的直接映射；下级节点的映射单独维护。移除全部映射不会删除知识点或旧卷。</p>
        <div class="field"><label :for="fieldPrefix + '-revision'">选择知识点修订</label><select :id="fieldPrefix + '-revision'" v-model="revisionId"><option value="">请选择</option><option v-for="option in options" :key="option.id" :value="option.id">{{ mappingLabel(option.id) }}</option></select></div>
        <button v-if="options.length < optionsTotal" @click="run(() => loadOptions(true))">加载更多修订</button>
        <button :disabled="!revisionId" @click="addMapping">添加映射</button>
        <ol><li v-for="(entry, index) in entries" :key="entry.knowledge_revision_id">
          {{ mappingLabel(entry.knowledge_revision_id) }}
          <div class="field"><label :for="fieldPrefix + '-role-' + entry.knowledge_revision_id">映射用途</label><select :id="fieldPrefix + '-role-' + entry.knowledge_revision_id" v-model="entry.role"><option value="primary">主学</option><option value="review">复习</option></select></div>
          <button :disabled="index === 0" @click="move(index, -1)">上移</button><button :disabled="index === entries.length - 1" @click="move(index, 1)">下移</button>
          <button @click="entries.splice(index, 1)">移除映射</button>
        </li></ol>
        <button :disabled="!reason.trim()" @click="saveMappings">保存知识点映射</button>
      </template>
    </fieldset>
  </section>
</template>

<style scoped>
fieldset { border: 0; padding: 0; min-width: 0; }
.field { margin: 12px 0; }
label { display: inline-block; margin-right: 8px; }
input, select { max-width: 100%; padding: 8px; }
button { margin: 4px; }
</style>
