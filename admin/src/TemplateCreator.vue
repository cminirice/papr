<script setup lang="ts">
import { computed, onMounted, ref, useId } from 'vue'
import { ApiError, requestData } from '@papr/shared/api'
import type { GeneratorChoice, ObjectiveView, DraftDetail } from '@papr/shared/contracts'
import { useAdminWrite } from './useAdminWrite'
const props = defineProps<{ csrfToken: string }>()
const emit = defineEmits<{ created: [templateId: string, versionId: string]; close: [] }>()
const uid = useId(), send = useAdminWrite(props.csrfToken)
const choices = ref<GeneratorChoice[]>([]), generatorId = ref(''), targetId = ref('')
const questionType = ref('answer'), task = ref('product')
const targets = ref<Record<string, ObjectiveView>>({})
const code = ref(''), name = ref(''), reason = ref(''), error = ref(''), busy = ref(false)
const targetOptions = computed(() => current.value?.task_objective_revision_ids[task.value] ?? [])
const current = computed(() => choices.value.find(g => g.id === generatorId.value))
async function load() {
  busy.value = true; error.value = ''
  try {
    choices.value = await requestData<GeneratorChoice[]>('/admin/api/v1/generators')
    generatorId.value = choices.value.find(g => g.available && g.objective_revision_ids.length)?.id ?? ''
    const ids = [...new Set(choices.value.flatMap(g => g.objective_revision_ids))]
    const rows = await Promise.all(ids.map(id => requestData<ObjectiveView>('/admin/api/v1/objective-revisions/' + id)))
    targets.value = Object.fromEntries(rows.map(r => [r.id, r]))
    targetId.value = targetOptions.value[0] ?? ''
  } catch (cause) { error.value = cause instanceof ApiError ? cause.message : '生成组件加载失败，请重试。' }
  finally { busy.value = false }
}
async function create() {
  if (busy.value || !current.value) return
  busy.value = true; error.value = ''
  try {
    const draft = await send<DraftDetail>('/admin/api/v1/templates', { code: code.value, name: name.value,
      task: task.value, question_type: questionType.value, generator_id: current.value.id, objective_revision_id: targetId.value, config: current.value.task_configs[task.value], reason: reason.value })
    emit('created', draft.template_id, draft.id)
  } catch (cause) { error.value = cause instanceof ApiError ? cause.message : '尚未确认创建结果，请先刷新模板列表核对相同编码，避免重复创建。' }
  finally { busy.value = false }
}
onMounted(load)
</script>
<template>
  <section class="card" :aria-labelledby="uid + '-title'"><h2 :id="uid + '-title'">新建模板</h2>
    <p>只能选择当前生成组件支持的目标修订。创建后先调整参数和固定用例，再预览、验证、审题和发布。</p>
    <button :disabled="busy" @click="emit('close')">关闭新建模板</button><button :disabled="busy" @click="load">刷新生成组件</button>
    <p v-if="error" role="alert">{{ error }}</p>
    <form @submit.prevent="create"><fieldset :disabled="busy">
      <label :for="uid + '-code'">新模板编码</label><input :id="uid + '-code'" v-model="code" maxlength="64" pattern="[A-Za-z0-9_-]+" required>
      <label :for="uid + '-name'">新模板名称</label><input :id="uid + '-name'" v-model="name" maxlength="120" required>
      <label :for="uid + '-generator'">生成组件</label><select :id="uid + '-generator'" v-model="generatorId" @change="targetId = targetOptions[0] ?? ''"><option v-for="g in choices" :key="g.id" :value="g.id" :disabled="!g.available || !g.objective_revision_ids.length">{{ g.key }} · {{ g.version }}{{ g.available ? '' : '（不可用）' }}</option></select>
      <label :for="uid + '-target'">主训练目标修订</label><select :id="uid + '-target'" v-model="targetId"><option v-for="id in targetOptions" :key="id" :value="id">{{ targets[id]?.content.name }} · 第{{ targets[id]?.revision_no }}版</option></select>
      <label :for="uid + '-task'">训练内容</label><select :id="uid + '-task'" v-model="task" @change="questionType = task === 'missing_digit' ? 'fill' : task === 'error_choice' ? 'choice' : 'answer'; targetId = targetOptions[0] ?? ''"><option value="product">普通求积（基础、提高）</option><option value="missing_digit">缺数填空（挑战）</option><option value="error_choice">错误原因选择（挑战）</option><option value="correction">纠错解答（挑战）</option><option value="zero_product">含零因数乘法（提高）</option></select>
      <label :for="uid + '-type'">模板题型</label><select :id="uid + '-type'" v-model="questionType" :disabled="!['product', 'zero_product'].includes(task)"><option v-for="kind in current?.question_types ?? []" :key="kind" :value="kind">{{ kind === 'fill' ? '乘积填空题' : kind === 'choice' ? '乘积选择题' : '竖式解答题' }}</option></select>
      <p v-if="current">初始配置：{{ task === 'product' ? '基础与提高乘法' : task === 'zero_product' ? '提高档含零因数' : '挑战档推理' }}；题目每行2道、解析每行1道。创建后可在配置中调整。</p>
      <p v-if="!targetId">当前没有兼容的目标修订，不能新建模板。</p>
      <label :for="uid + '-reason'">新建模板理由</label><input :id="uid + '-reason'" v-model="reason" maxlength="2000" required>
      <button type="submit" :disabled="!targetId || !reason.trim() || !code || !name.trim()">创建模板草稿</button>
    </fieldset></form>
  </section>
</template>
<style scoped>
fieldset { border: 0; padding: 0; min-width: 0; }
label { display: block; margin-top: 12px; }
input, select { max-width: 100%; padding: 8px; }
button { margin: 8px; }
</style>
