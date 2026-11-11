<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { formatBeijingTime } from '@papr/shared/time'
import { ApiError, requestData } from '@papr/shared/api'
import type { AdminSessionView, AdminSessionCreated, CsrfToken } from '@papr/shared/contracts'
import DashboardPanel from './DashboardPanel.vue'
import ContentOverview from './ContentOverview.vue'
import OperationsPanel from './WorkflowRecords.vue'
import ContentPrototype from './ContentPrototype.vue'
import GeneratorPrototype from './GeneratorPrototype.vue'
import SourceManager from './SourceManager.vue'
import PaperManager from './PaperManager.vue'
import SettingsPanel from './SettingsPanel.vue'
import { refreshWorkspace } from './content-demo'
import DirectoryTree from './DirectoryTree.vue'
import AuditPanel from './WorkflowAudit.vue'
type Page = 'generators' | 'dashboard' | 'catalogs' | 'templates' | 'operations' | 'sources' | 'papers' | 'settings' | 'audit'
const menus: { title: string; items: { id: Page; label: string; icon: string }[] }[] = [
  { title: '工作台', items: [{ id: 'dashboard', label: '数据概览', icon: '▦' }] },
  { title: '内容管理', items: [{ id: 'catalogs', label: '目录管理', icon: '▤' }, { id: 'templates', label: '模板管理', icon: '▧' }, { id: 'generators', label: '出题组件管理', icon: '⚒' }, { id: 'sources', label: '资料来源', icon: '▥' }] },
  { title: '练习管理', items: [{ id: 'operations', label: '生成记录', icon: '≡' }, { id: 'papers', label: '试卷与勘误', icon: '▱' }] },
  { title: '系统管理', items: [{ id: 'settings', label: '系统设置', icon: '⚙' }, { id: 'audit', label: '操作记录', icon: '◷' }] },
]
const collapsed = ref<string[]>([])
function readPage(): Page { const value = location.hash.replace('#/', ''); return menus.some(g => g.items.some(i => i.id === value)) ? value as Page : 'dashboard' }
const activePanel = ref<Page>(readPage())
const activeMenu = computed(() => menus.find(g => g.items.some(i => i.id === activePanel.value))!)
const pageTitle = computed(() => activeMenu.value.items.find(i => i.id === activePanel.value)!.label)
function navigate(id: Page) { source.value = null; activePanel.value = id; location.hash = '/' + id }
function syncPage() { activePanel.value = readPage(); collapsed.value = collapsed.value.filter(g => g !== activeMenu.value.title) }
function toggle(title: string) { collapsed.value = collapsed.value.includes(title) ? collapsed.value.filter(g => g !== title) : [...collapsed.value, title] }
onMounted(() => window.addEventListener('hashchange', syncPage))
onUnmounted(() => window.removeEventListener('hashchange', syncPage))
const source = ref<{ templateId: string; versionId: string } | null>(null)
function openTemplate(templateId: string, versionId: string) {
  source.value = { templateId, versionId }
  activePanel.value = 'templates'
  location.hash = '/templates'
}
const session = ref<AdminSessionView | null>(null)
const username = ref('')
const password = ref('')
const csrfToken = ref('')
const busy = ref(true)
const error = ref('')

function message(cause: unknown) {
  return cause instanceof ApiError ? cause.message : '暂时无法连接服务，请稍后重试。'
}
async function refreshCsrf() {
  csrfToken.value = (await requestData<CsrfToken>('/admin/api/v1/session/csrf', { body: {} })).csrf_token
}
onMounted(async () => {
  try {
    const current = await requestData<AdminSessionView>('/admin/api/v1/session')
    await refreshCsrf()
    await refreshWorkspace()
    session.value = current
  } catch (cause) {
    if (!(cause instanceof ApiError && cause.status === 401)) error.value = message(cause)
  } finally { busy.value = false }
})
async function login() {
  if (busy.value) return
  busy.value = true
  error.value = ''
  try {
    const created = await requestData<AdminSessionCreated>('/admin/api/v1/session/login', { body: { username: username.value, password: password.value } })
    // 与用户端一致，确认浏览器实际保留了Cookie。
    session.value = await requestData<AdminSessionView>('/admin/api/v1/session')
    csrfToken.value = created.csrf_token
    await refreshWorkspace()
    navigate('dashboard')
  } catch (cause) { error.value = message(cause) }
  finally { password.value = ''; busy.value = false }
}
async function logout() {
  if (busy.value) return
  busy.value = true
  error.value = ''
  try {
    try {
      await requestData<void>('/admin/api/v1/session/logout', { body: {}, csrf: csrfToken.value })
    } catch (cause) {
      if (!(cause instanceof ApiError && cause.code === 'CSRF_INVALID')) throw cause
      await refreshCsrf()
      await requestData<void>('/admin/api/v1/session/logout', { body: {}, csrf: csrfToken.value })
    }
    session.value = null
    csrfToken.value = ''
  } catch (cause) {
    if (cause instanceof ApiError && cause.status === 401) { session.value = null; csrfToken.value = '' }
    else error.value = message(cause)
  } finally { busy.value = false }
}
</script>

<template>
  <div v-if="session" class="admin-shell">
    <header class="admin-header">
      <a class="admin-brand" href="#/dashboard"><span class="brand-mark">纸</span><strong>纸上练</strong><span class="brand-caption">管理台</span></a>
      <div class="header-account"><span class="online-dot"></span><span>管理员 · 已登录</span><span class="session-expiry">会话到期 {{ formatBeijingTime(session.expires_at) }}</span><button class="secondary" :disabled="busy" @click="logout">退出登录</button></div>
    </header>
    <aside class="admin-sidebar"><nav aria-label="管理台导航">
      <section v-for="group in menus" :key="group.title" class="menu-group">
        <button class="menu-group-title" :aria-expanded="!collapsed.includes(group.title)" @click="toggle(group.title)">{{ group.title }}<span aria-hidden="true">{{ collapsed.includes(group.title) ? '›' : '⌄' }}</span></button>
        <div v-show="!collapsed.includes(group.title)"><a v-for="item in group.items" :key="item.id" :href="'#/' + item.id" :aria-current="activePanel === item.id ? 'page' : undefined" @click="navigate(item.id)"><span aria-hidden="true" class="menu-icon">{{ item.icon }}</span>{{ item.label }}</a></div>
      </section>
    </nav><div class="sidebar-foot">纸上练 · 内容工作空间</div></aside>
    <main class="admin-main">
      <div class="page-heading"><div class="breadcrumb">{{ activeMenu.title }} <span>/</span> {{ pageTitle }}</div><h1>{{ pageTitle }}</h1></div>
      <p v-if="error" role="alert">{{ error }}</p>
      <DashboardPanel v-if="activePanel === 'dashboard'" @navigate="navigate" />
      <ContentOverview v-else-if="activePanel === 'templates' && source" :key="activePanel" :mode="activePanel" :csrf-token="csrfToken" :initial-template-id="source?.templateId" :initial-version-id="source?.versionId" />
      <OperationsPanel v-else-if="activePanel === 'operations'" :csrf-token="csrfToken" @open-template="openTemplate" />
      <DirectoryTree v-else-if="activePanel === 'catalogs'" />
      <ContentPrototype v-else-if="activePanel === 'templates'" :mode="activePanel" />
      <GeneratorPrototype v-else-if="activePanel === 'generators'" />
      <SourceManager v-else-if="activePanel === 'sources'" :csrf-token="csrfToken" />
      <AuditPanel v-else-if="activePanel === 'audit'" />
      <SettingsPanel v-else-if="activePanel === 'settings'" :csrf-token="csrfToken" />
      <OperationsPanel v-else />
    </main>
  </div>
  <main v-else class="admin-login">
    <div class="admin-brand"><span class="brand-mark">纸</span><strong>纸上练</strong><span class="brand-caption">管理台</span></div>
    <section class="card"><h1>欢迎登录</h1><p class="muted">维护练习内容，查看使用数据。</p><p v-if="error" role="alert">{{ error }}</p>
      <form @submit.prevent="login"><label for="username">用户名</label><input id="username" v-model="username" autocomplete="username" maxlength="64" required :disabled="busy">
      <label for="password">密码</label><input id="password" v-model="password" type="password" autocomplete="current-password" maxlength="128" required :disabled="busy">
      <button type="submit" :disabled="busy">{{ busy ? '请稍候……' : '登录' }}</button></form>
    </section>
  </main>
</template>
