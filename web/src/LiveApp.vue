<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref } from 'vue'
import PracticeSelection from './PracticeSelection.vue'
import GenerationTasks from './GenerationTasks.vue'
import PaperHistory from './PaperHistory.vue'
import InformationPage from './InformationPage.vue'
import { formatBeijingTime } from '@papr/shared/time'
import { ApiError, requestData } from '@papr/shared/api'
import type { UserSessionCreated, UserSessionView, PaperSelection } from '@papr/shared/contracts'
const selectionForm = ref<InstanceType<typeof PracticeSelection> | null>(null)
type Page = 'practice' | 'records' | 'help' | 'privacy'
function currentPage(): Page {
  return ({ '#/records': 'records', '#/help': 'help', '#/privacy': 'privacy' } as Record<string, Page>)[location.hash] ?? 'practice'
}
const page = ref<Page>(currentPage())
function navigate() {
  page.value = currentPage()
  if (location.hash === '#/tasks') void nextTick(() => document.getElementById('tasks-title')?.scrollIntoView())
}
async function reuse(selection: PaperSelection) {
  location.hash = '#/'
  page.value = 'practice'
  await nextTick()
  void selectionForm.value?.reusePaper(selection)
  document.getElementById('selection-title')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}
const taskRefresh = ref(0)
const serverTime = ref('')
const ready = ref(false)
const busy = ref(false)
const error = ref('')
// CSRF只保存在页面内存；后续出卷请求使用，不写入localStorage。
const csrfToken = ref('')

async function connect() {
  if (busy.value) return
  busy.value = true
  error.value = ''
  ready.value = false
  csrfToken.value = ''
  try {
    const created = await requestData<UserSessionCreated>('/api/v1/session', { body: {} })
    csrfToken.value = created.csrf_token
    // 验证浏览器接收了Cookie；失败后不自动循环创建新身份。
    const current = await requestData<UserSessionView>('/api/v1/session')
    if (current.user_id !== created.user_id) throw new Error('浏览器会话发生变化，请重试')
    serverTime.value = formatBeijingTime(current.server_now)
    ready.value = true
  } catch (cause) {
    csrfToken.value = ''
    error.value = cause instanceof ApiError && cause.status === 401
      ? '请允许此网站使用 Cookie，再点击重试。'
      : cause instanceof ApiError ? cause.message : '暂时无法连接服务，请稍后重试。'
  } finally {
    busy.value = false
  }
}
onMounted(() => { window.addEventListener('hashchange', navigate); void connect() })
onUnmounted(() => window.removeEventListener('hashchange', navigate))
</script>

<template>
  <main>
    <div class="brand">纸上练 / papr</div>
    <p><a href="?">← 返回新版交互演示</a></p>
    <h1>每天一张，认真练习。</h1>
    <p class="muted">四年级数学练习，按知识点与难度选择，打印后在纸上作答。</p>
    <nav aria-label="主导航">
      <a href="#/" :aria-current="page === 'practice' ? 'page' : undefined">开始练习</a>
      <a href="#/records" :aria-current="page === 'records' ? 'page' : undefined">历史练习</a>
      <a href="#/help" :aria-current="page === 'help' ? 'page' : undefined">使用说明</a>
      <a href="#/privacy" :aria-current="page === 'privacy' ? 'page' : undefined">隐私说明</a>
    </nav>
    <section v-show="page === 'practice' || page === 'records'" class="card" aria-labelledby="preparing">
      <span class="label">浏览器会话</span>
      <h2 id="preparing">无需注册，按需选择练习</h2>
      <p>选择已开放内容生成练习，完成后可查看、下载和打印。</p>
      <p v-if="busy" role="status">正在连接……</p>
      <p v-else-if="ready">无需注册，后续生成的练习可在此浏览器中查看。</p>
      <div v-if="error" role="alert">
        <p>{{ error }}</p>
        <button type="button" :disabled="busy" @click="connect">重试</button>
      </div>
      <p class="muted">清除 Cookie、使用无痕窗口或更换浏览器，可能失去原有练习的访问入口。</p>
      <p v-if="serverTime" class="muted">当前时间：{{ serverTime }}</p>
    </section>
    <PracticeSelection v-if="ready" v-show="page === 'practice'" ref="selectionForm" :csrf-token="csrfToken" @submitted="taskRefresh++" />
    <GenerationTasks v-if="ready" v-show="page === 'practice'" :key="taskRefresh" :csrf-token="csrfToken" @reuse="reuse" />
    <PaperHistory v-if="ready && page === 'records'" :csrf-token="csrfToken" @reuse="reuse" />
    <InformationPage v-if="page === 'help' || page === 'privacy'" :page="page" />
  </main>
</template>

<style scoped>
nav { display: flex; flex-wrap: wrap; gap: 20px; margin-bottom: 20px; }
nav [aria-current=page] { font-weight: 700; text-decoration-thickness: 3px; }
</style>
