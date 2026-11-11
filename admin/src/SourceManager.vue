<script setup lang="ts">
import { onMounted, ref, useId } from 'vue'
import { ApiError, requestData } from '@papr/shared/api'
import type { SourceEdit, SourceView, SourceList } from '@papr/shared/contracts'
import { useAdminWrite } from './useAdminWrite'
const props = defineProps<{ csrfToken: string }>()
const uid = useId()
const send = useAdminWrite(props.csrfToken)
const items = ref<SourceView[]>([]), total = ref(0), selected = ref<SourceView | null>(null)
const title = ref(''), publisher = ref(''), url = ref(''), reference = ref(''), published = ref('')
const checked = ref(''), evidence = ref(''), reason = ref('')
const verification = ref<SourceEdit['verification_status']>('reference')
const busy = ref(false), error = ref(''), notice = ref('')
async function run(action: () => Promise<void>) {
  if (busy.value) return
  busy.value = true; error.value = ''; notice.value = ''
  try { await action() } catch (cause) { error.value = cause instanceof ApiError ? cause.message : '资料操作失败，请重试。' }
  finally { busy.value = false }
}
async function load(more = false) {
  const data = await requestData<SourceList>('/admin/api/v1/sources?limit=100&offset=' + (more ? items.value.length : 0))
  items.value = more ? [...items.value, ...data.items] : data.items; total.value = data.total
}
function choose(source: SourceView | null) {
  selected.value = source; title.value = source?.title ?? ''; publisher.value = source?.publisher ?? ''
  url.value = source?.url ?? ''; reference.value = source?.reference_note ?? ''; published.value = source?.published_on ?? ''
  checked.value = source?.checked_at?.slice(0, 19) ?? ''; evidence.value = source?.evidence_note ?? ''
  verification.value = source?.verification_status ?? 'reference'
}
function save() {
  void run(async () => {
    const body: SourceEdit = { title: title.value, publisher: publisher.value.trim() || null, url: url.value.trim() || null,
      reference_note: reference.value.trim() || null, published_on: published.value || null,
      checked_at: checked.value ? checked.value + '+08:00' : null, evidence_note: evidence.value.trim() || null,
      verification_status: verification.value, reason: reason.value }
    const saved = await send<SourceView>('/admin/api/v1/sources' + (selected.value ? '/' + selected.value.id : ''),
      body, selected.value ? 'PATCH' : 'POST', selected.value?.lock_version)
    choose(saved); await load(); notice.value = '资料来源已保存。'
  })
}
onMounted(() => run(load))
</script>
<template>
  <section class="card" :aria-labelledby="uid + '-title'"><h2 :id="uid + '-title'">资料来源维护</h2>
    <p>记录出处和核验依据；保存链接不会自动访问或抓取该网站。</p>
    <p v-if="error" role="alert">{{ error }}</p><p v-if="notice" role="status">{{ notice }}</p>
    <button :disabled="busy" @click="choose(null)">新建资料来源</button>
    <button :disabled="busy" @click="run(load)">刷新资料列表</button>
    <ul><li v-for="source in items" :key="source.id">{{ source.title }} <button :disabled="busy" @click="run(async () => choose(await requestData<SourceView>('/admin/api/v1/sources/' + source.id)))">编辑{{ source.title }}</button></li></ul>
    <button v-if="items.length < total" :disabled="busy" @click="run(() => load(true))">更多资料来源</button>
    <form @submit.prevent="save"><fieldset :disabled="busy">
      <label :for="uid + '-name'">资料标题</label><input :id="uid + '-name'" v-model="title" maxlength="120" required>
      <label :for="uid + '-publisher'">出版者</label><input :id="uid + '-publisher'" v-model="publisher" maxlength="500">
      <label :for="uid + '-url'">资料链接</label><input :id="uid + '-url'" v-model="url" type="url" maxlength="2000">
      <label :for="uid + '-reference'">参考说明</label><textarea :id="uid + '-reference'" v-model="reference" maxlength="4000" />
      <label :for="uid + '-published'">出版日期</label><input :id="uid + '-published'" v-model="published" type="date">
      <label :for="uid + '-verification'">核验状态</label><select :id="uid + '-verification'" v-model="verification"><option value="unverified">未核验</option><option value="reference">仅供参考</option><option value="verified">已核验</option></select>
      <label :for="uid + '-checked'">核验时间</label><input :id="uid + '-checked'" v-model="checked" type="datetime-local" step="1" :required="verification === 'verified'">
      <label :for="uid + '-evidence'">核验证据说明</label><textarea :id="uid + '-evidence'" v-model="evidence" maxlength="4000" :required="verification === 'verified'" />
      <label :for="uid + '-reason'">资料变更理由</label><input :id="uid + '-reason'" v-model="reason" maxlength="2000" required>
      <button type="submit" :disabled="!reason.trim() || !title.trim() || (!url.trim() && !reference.trim())">保存资料来源</button>
    </fieldset></form>
  </section>
</template>
<style scoped>
fieldset { border: 0; padding: 0; min-width: 0; }
label { display: block; margin-top: 12px; }
input, textarea, select { max-width: 100%; padding: 8px; }
textarea { display: block; width: 100%; min-height: 70px; }
button { margin: 8px 8px 8px 0; }
</style>
