<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ApiError, requestData } from '@papr/shared/api'
import type { CatalogSummary, NodeView, PointView, PointCapabilities, CsrfToken } from '@papr/shared/contracts'
const props = defineProps<{ catalog: CatalogSummary; csrfToken: string }>()
const emit = defineEmits<{ changed: [] }>()
const nodes = ref<NodeView[]>([])
const points = ref<PointView[]>([])
const selectedNode = ref('')
const matrix = ref<PointCapabilities | null>(null)
const busy = ref(false)
const error = ref('')
const notice = ref('')
const reason = ref('')
const csrf = ref(props.csrfToken)
const difficulties = { basic: '基础', standard: '提高', challenge: '挑战' }
const types = { choice: '选择题', fill: '填空题', answer: '解答题' }
async function run(action: () => Promise<void>) {
  if (busy.value) return
  busy.value = true; error.value = ''; notice.value = ''
  try { await action() } catch (cause) {
    error.value = cause instanceof ApiError ? cause.message : '操作失败，请重试。'
  } finally { busy.value = false }
}
async function send<T>(path: string, body: object, lock: number, method: 'PATCH' | 'PUT') {
  const request = () => requestData<T>(path, { body, method, csrf: csrf.value, ifMatch: `"${lock}"` })
  try { return await request() } catch (cause) {
    if (!(cause instanceof ApiError) || cause.status !== 403 || cause.code !== 'CSRF_INVALID') throw cause
    csrf.value = (await requestData<CsrfToken>('/admin/api/v1/session/csrf', { body: {} })).csrf_token
    return request()
  }
}
async function load() {
  nodes.value = await requestData<NodeView[]>(`/admin/api/v1/catalogs/${props.catalog.id}/nodes`)
}
function changeCatalog() {
  void run(async () => {
    await send(`/admin/api/v1/catalogs/${props.catalog.id}`, {
      status: props.catalog.status === 'active' ? 'archived' : 'active', reason: reason.value,
    }, props.catalog.lock_version, 'PATCH')
    emit('changed'); notice.value = '目录状态已更新。'
  })
}
function changeNode(node: NodeView) {
  void run(async () => {
    await send(`/admin/api/v1/catalog-nodes/${node.id}`, { status: node.status === 'active' ? 'disabled' : 'active', reason: reason.value }, node.lock_version, 'PATCH')
    await load(); notice.value = '节点状态已更新。'
  })
}
function selectNode(id: string) {
  void run(async () => {
    selectedNode.value = id; matrix.value = null; points.value = []
    points.value = await requestData<PointView[]>(`/admin/api/v1/catalog-nodes/${id}/knowledge-points`)
  })
}
function selectPoint(id: string) {
  void run(async () => {
    matrix.value = null
    matrix.value = await requestData<PointCapabilities>(`/admin/api/v1/knowledge-points/${id}/capabilities`)
  })
}
function save() {
  if (!matrix.value) return
  const current = matrix.value
  void run(async () => {
    const policies = current.policies.map(p => ({ difficulty: p.difficulty, question_type: p.question_type,
      count_options: p.count_options, default_count: p.default_count !== null && p.count_options.includes(p.default_count) ? p.default_count : null }))
    matrix.value = await send<PointCapabilities>(`/admin/api/v1/knowledge-points/${current.point.id}/quantity-policies`,
      { policies, reason: reason.value }, current.lock_version, 'PUT')
    notice.value = '题量策略已保存，公开能力已更新。'
  })
}
onMounted(() => run(load))
</script>

<template>
  <section class="card">
    <h2>{{ catalog.name }} · 开放设置</h2>
    <p class="muted">目录、节点、已发布内容和题量策略共同决定用户可选内容。启用目录不会代替来源核验或模板审题。</p>
    <label>操作说明 <input v-model="reason" :disabled="busy" maxlength="2000" placeholder="说明本次开放或调整的原因" /></label>
    <p><button :disabled="busy || !reason.trim()" @click="changeCatalog">{{ catalog.status === 'active' ? '归档目录' : '启用目录' }}</button></p>
    <p v-if="error" role="alert">{{ error }}</p><p v-if="notice" role="status">{{ notice }}</p>
    <button :disabled="busy" @click="run(load)">刷新节点状态</button>
    <ul>
      <li v-for="node in nodes" :key="node.id">
        {{ node.name }} · {{ node.status === 'active' ? '启用' : '未开放' }}
        <button :disabled="busy || !reason.trim()" @click="changeNode(node)">{{ node.status === 'active' ? '停用节点' : '启用节点' }}</button>
        <button :disabled="busy" @click="selectNode(node.id)">查看知识点</button>
      </li>
    </ul>
    <p v-if="!nodes.length">当前目录尚无节点。</p>
    <div v-if="selectedNode">
      <p v-if="!points.length">当前节点尚无知识点。</p>
      <button v-for="point in points" :key="point.id" :disabled="busy" @click="selectPoint(point.id)">{{ point.code }} · {{ point.name }}</button>
    </div>
    <template v-if="matrix">
      <h3>{{ matrix.point.name }} · 题量策略</h3>
      <button :disabled="busy" @click="selectPoint(matrix.point.id)">重新加载（放弃未保存修改）</button>
      <fieldset v-for="cell in matrix.policies" :key="cell.difficulty + cell.question_type" :disabled="busy">
        <legend>{{ difficulties[cell.difficulty] }} / {{ types[cell.question_type] }}</legend>
        <p v-if="cell.unavailable_reason" class="muted">{{ cell.unavailable_reason }}</p>
        <label v-for="count in [...new Set([...cell.supported_count_options, ...cell.count_options])].sort((a,b) => a-b)" :key="count">
          <input v-model="cell.count_options" type="checkbox" :value="count" :disabled="!cell.supported_count_options.includes(count) && !cell.count_options.includes(count)" />
          {{ count }}题{{ cell.supported_count_options.includes(count) ? '' : '（已失效，保存前须取消）' }}
        </label>
        <p v-if="cell.supported_count_options.length || cell.count_options.length">
          <label>默认题量 <select v-model="cell.default_count"><option :value="null">不指定</option>
            <option v-for="count in cell.count_options" :key="count" :value="count">{{ count }}题</option>
          </select></label>
        </p>
        <p class="muted">当前生效：{{ cell.effective_count_options.join('、') || '未开放' }}；有效模板：{{ cell.evidence_version_ids.length }}个</p>
      </fieldset>
      <button :disabled="busy || !reason.trim()" @click="save">保存完整题量策略</button>
    </template>
  </section>
</template>
<style scoped>
fieldset { margin: 16px 0; border: 1px solid var(--color-border, #e5e7eb); border-radius: 8px; }
label { display: inline-block; margin: 4px 12px 4px 0; }
button { margin: 4px; }
input:not([type=checkbox]) { width: min(440px, 100%); }
</style>
