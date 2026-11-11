<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { ApiError, requestData } from '@papr/shared/api'
import { formatBeijingTime } from '@papr/shared/time'
import type { PaperList, PaperSummary, PaperDetail, PaperSelection } from '@papr/shared/contracts'
import PaperPreview from './PaperPreview.vue'
defineProps<{csrfToken:string}>()
const emit = defineEmits<{ reuse: [selection: PaperSelection] }>()
const items = ref<PaperSummary[]>([])
const papers = ref<Record<string, PaperDetail>>({})
const cursor = ref<string | null>(null)
const busy = ref(false)
const loaded = ref(false)
const error = ref('')
const names = { basic: '基础', standard: '提高', challenge: '挑战' }
let alive = true
function fail(cause: unknown) {
  if (cause instanceof ApiError && cause.status === 401) {
    items.value = []; papers.value = {}; cursor.value = null; loaded.value = false
    error.value = '浏览器会话已失效，请刷新页面重新连接。原会话失效后，可能无法找回原有历史。'
  } else error.value = cause instanceof ApiError ? cause.message : '暂时无法加载历史练习，请重试。'
}
async function load(more = false) {
  if (busy.value) return
  busy.value = true; error.value = ''
  try {
    const query = new URLSearchParams({ limit: '20' })
    if (more && cursor.value) query.set('cursor', cursor.value)
    const data = await requestData<PaperList>('/api/v1/papers?' + query)
    if (!alive) return
    items.value = more ? [...items.value, ...data.items.filter(p => !items.value.some(old => old.id === p.id))] : data.items
    if (!more) papers.value = {}
    cursor.value = data.next_cursor; loaded.value = true
  } catch (cause) { if (alive) fail(cause) }
  finally { busy.value = false }
}
async function open(id: string) {
  if (busy.value) return
  busy.value = true; error.value = ''
  try {
    const detail = await requestData<PaperDetail>('/api/v1/papers/' + id)
    if (alive) papers.value[id] = detail
  } catch (cause) { if (alive) fail(cause) }
  finally { busy.value = false }
}
onMounted(() => { void load() })
onUnmounted(() => { alive = false })
</script>

<template>
  <section class="card" aria-labelledby="history-title">
    <h2 id="history-title">历史练习</h2>
    <p class="muted">按生成时间倒序展示本浏览器已完成的练习。查看、下载和打印不会延长冷却。</p>
    <p><a href="#/tasks">查看生成任务</a>：查看排队、处理中、失败和取消的任务。</p>
    <button :disabled="busy" @click="load()">刷新历史</button>
    <p v-if="busy" role="status">正在加载历史练习……</p>
    <p v-if="error" role="alert">{{ error }}</p>
    <p v-if="loaded && !items.length">暂无已完成的练习。<a href="#/">去生成第一份练习</a></p>
    <article v-for="paper in items" :key="paper.id" :data-paper-id="paper.id">
      <h3>{{ paper.title }}{{ paper.status === 'withdrawn' ? '（已撤下）' : '' }}</h3>
      <p v-if="paper.notices?.length">此练习有{{ paper.notices.length }}条说明，请打开查看。</p>
      <p>{{ paper.catalog_name }} · {{ paper.theme_name }} · {{ names[paper.difficulty] }}</p>
      <p>共 {{ paper.total_count }} 题：选择 {{ paper.question_type_counts.choice }} 题，填空 {{ paper.question_type_counts.fill }} 题，解答 {{ paper.question_type_counts.answer }} 题</p>
      <p class="muted">{{ formatBeijingTime(paper.generated_at) }}</p>
      <button v-if="!papers[paper.id]" :disabled="busy" @click="open(paper.id)">查看练习</button>
      <PaperPreview v-else :csrf-token="csrfToken" :paper="papers[paper.id]!" @reuse="emit('reuse', $event)" @close="delete papers[paper.id]" />
    </article>
    <p v-if="cursor"><button :disabled="busy" @click="load(true)">查看更多练习</button></p>
    <p v-else-if="loaded && items.length" class="muted">已显示全部历史练习。</p>
  </section>
</template>

<style scoped>
article { border-top: 1px solid #e5e7eb; margin-top: 16px; padding-top: 8px; }
</style>
