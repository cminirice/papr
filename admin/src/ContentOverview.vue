<script setup lang="ts">
import { onMounted, ref, useId } from 'vue'
import { ApiError, requestData } from '@papr/shared/api'
import { formatBeijingTime } from '@papr/shared/time'
import type { CatalogList, TemplateList } from '@papr/shared/contracts'
import TemplateEditor from './TemplateEditor.vue'
import CatalogAccess from './CatalogAccess.vue'
import CatalogEditor from './CatalogEditor.vue'
import TemplateCreator from './TemplateCreator.vue'

const props = defineProps<{ csrfToken: string; mode: 'catalogs' | 'templates'; initialTemplateId?: string; initialVersionId?: string }>()
const selectedTemplate = ref(props.initialTemplateId ?? '')
const selectedVersion = ref(props.initialVersionId ?? '')
const selectedCatalog = ref('')
const editingCatalog = ref<string | null>(null)
const creatingTemplate = ref(false)
const uid = useId(), query = ref(''), templateStatus = ref(''), published = ref('')
let appliedQuery = ''
function templateQuery() {
  const params = new URLSearchParams({ limit: '100' })
  if (query.value.trim()) params.set('q', query.value.trim())
  if (templateStatus.value) params.set('status', templateStatus.value)
  if (published.value) params.set('published', published.value)
  return params.toString()
}
function created(templateId: string, versionId: string) {
  creatingTemplate.value = false; selectedTemplate.value = templateId; selectedVersion.value = versionId
  query.value = templateStatus.value = published.value = ''
  void reload()
}
async function moreTemplates() {
  if (busy.value || !templates.value) return
  busy.value = true; error.value = ''
  try {
    const data = await requestData<TemplateList>('/admin/api/v1/templates?' + appliedQuery + '&offset=' + templates.value.items.length)
    templates.value = { ...data, items: [...templates.value.items, ...data.items.filter(t => !templates.value!.items.some(old => old.id === t.id))] }
  } catch (cause) { error.value = cause instanceof ApiError ? cause.message : '模板列表加载失败，请重试。' }
  finally { busy.value = false }
}

async function moreCatalogs() {
  if (busy.value || !catalogs.value) return
  busy.value = true; error.value = ''
  try { const data = await requestData<CatalogList>('/admin/api/v1/catalogs?limit=100&offset=' + catalogs.value.items.length); catalogs.value = { ...data, items: [...catalogs.value.items, ...data.items] } }
  catch (cause) { error.value = cause instanceof ApiError ? cause.message : '目录加载失败，请重试' }
  finally { busy.value = false }
}
const catalogs = ref<CatalogList | null>(null)
const templates = ref<TemplateList | null>(null)
const busy = ref(false)
const error = ref('')
const statusLabels = { draft: '草稿', active: '启用', archived: '归档', disabled: '停用' }

async function reload() {
  if (busy.value) return
  busy.value = true
  error.value = ''
  try {
    const nextQuery = templateQuery()
    if (props.mode === 'catalogs') catalogs.value = await requestData<CatalogList>('/admin/api/v1/catalogs?limit=100')
    else templates.value = await requestData<TemplateList>('/admin/api/v1/templates?' + nextQuery)
    appliedQuery = nextQuery
  } catch (cause) {
    error.value = cause instanceof ApiError ? cause.message : '内容暂时无法加载，请重试。'
  } finally { busy.value = false }
}
onMounted(reload)
</script>

<template>
  <template v-if="editingCatalog !== null || selectedCatalog || creatingTemplate || selectedTemplate">
    <button class="secondary back-link" @click="editingCatalog = null; selectedCatalog = ''; creatingTemplate = false; selectedTemplate = ''; selectedVersion = ''; reload()">← 返回{{mode === 'catalogs' ? '目录' : '模板'}}列表</button>
    <CatalogEditor v-if="editingCatalog !== null" :key="editingCatalog" :catalog-id="editingCatalog" :csrf-token="csrfToken" @changed="reload" @close="editingCatalog = null" />
    <TemplateCreator v-else-if="creatingTemplate" :csrf-token="csrfToken" @created="created" @close="creatingTemplate = false" />
    <template v-else-if="selectedCatalog"><template v-for="catalog in catalogs?.items ?? []" :key="catalog.id"><CatalogAccess v-if="selectedCatalog === catalog.id" :catalog="catalog" :csrf-token="csrfToken" @changed="reload" /></template></template>
    <TemplateEditor v-else-if="selectedTemplate" :key="selectedTemplate + selectedVersion" :template-id="selectedTemplate" :initial-version-id="selectedVersion" :csrf-token="csrfToken" @saved="reload" />
  </template>
  <section v-else class="card" :aria-label="mode === 'catalogs' ? '目录列表' : '模板列表'">
    <div class="toolbar"><h2>{{mode === 'catalogs' ? '目录列表' : '模板列表'}} <span class="muted">{{mode === 'catalogs' ? catalogs?.total ?? 0 : templates?.total ?? 0}}</span></h2><div class="toolbar-actions"><button class="secondary" :disabled="busy" @click="reload">刷新</button><button v-if="mode === 'catalogs'" @click="editingCatalog = ''">＋ 新建目录</button><button v-else @click="creatingTemplate = true">＋ 新建模板</button></div></div>
    <p v-if="error" role="alert">{{error}}</p><p v-if="busy" role="status">正在加载…</p>
    <template v-if="mode === 'catalogs'">
      <p class="muted">按学期维护知识目录，选择目录后管理节点或调整开放设置。</p>
      <div class="table-wrap"><table class="data-table"><thead><tr><th>目录名称</th><th>学期</th><th>状态</th><th>教材核验</th><th>操作</th></tr></thead><tbody><tr v-for="catalog in catalogs?.items ?? []" :key="catalog.id"><td><strong>{{catalog.name}}</strong><small>{{catalog.code}}</small></td><td>{{catalog.term === 'upper' ? '上册' : '下册'}}</td><td><span class="status-tag" :class="{enabled:catalog.status==='active'}">{{statusLabels[catalog.status]}}</span></td><td>{{catalog.verification_status === 'provisional' ? '待核验' : '已核验'}}</td><td><button class="text-action" @click="editingCatalog=catalog.id">维护目录</button><button class="text-action" @click="selectedCatalog=catalog.id">开放设置</button></td></tr></tbody></table></div>
      <p v-if="catalogs&&!catalogs.total" class="empty-state">还没有目录，点击“新建目录”开始整理。</p>
      <div class="list-footer"><span>已显示 {{catalogs?.items.length ?? 0}} / {{catalogs?.total ?? 0}} 个目录</span><button v-if="catalogs && catalogs.items.length < catalogs.total" class="secondary" :disabled="busy" @click="moreCatalogs">加载更多目录</button></div>
    </template>
    <template v-else>
      <form class="filters-row" @submit.prevent="reload"><label :for="uid+'-q'">模板名称或编码<input :id="uid+'-q'" v-model="query" placeholder="搜索模板…" maxlength="100" :disabled="busy"></label><label :for="uid+'-status'">模板状态<select :id="uid+'-status'" v-model="templateStatus" :disabled="busy"><option value="">全部状态</option><option value="active">启用</option><option value="disabled">停用</option></select></label><label :for="uid+'-published'">发布情况<select :id="uid+'-published'" v-model="published" :disabled="busy"><option value="">全部</option><option value="true">已发布</option><option value="false">未发布</option></select></label><button type="submit" :disabled="busy">查询</button></form>
      <div class="table-wrap"><table class="data-table"><thead><tr><th>模板名称</th><th>发布情况</th><th>状态</th><th>更新时间</th><th>操作</th></tr></thead><tbody><tr v-for="item in templates?.items ?? []" :key="item.id"><td><strong>{{item.name}}</strong><small>{{item.code}}</small></td><td><span class="status-tag" :class="{enabled:!!item.current_published_version_id}">{{item.current_published_version_id?'已发布':'未发布'}}</span></td><td>{{statusLabels[item.status]}}</td><td>{{formatBeijingTime(item.updated_at)}}</td><td><button class="text-action" @click="selectedTemplate=item.id; selectedVersion=''">查看配置 →</button></td></tr></tbody></table></div>
      <p v-if="templates&&!templates.total" class="empty-state">没有符合条件的模板，可以调整筛选或新建模板。</p>
      <div class="list-footer"><span>已显示 {{templates?.items.length ?? 0}} / {{templates?.total ?? 0}} 个模板</span><button v-if="templates && templates.items.length < templates.total" class="secondary" :disabled="busy" @click="moreTemplates">加载更多模板</button></div>
    </template>
  </section>
</template>
