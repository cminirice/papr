<script setup lang="ts">
import { onMounted, ref, useId } from 'vue'
import { ApiError, requestData } from '@papr/shared/api'
import { formatBeijingTime } from '@papr/shared/time'
import QuestionSections from '@papr/shared/questions'
import type { AdminPaperList, AdminPaperDetail, NoticeCreate } from '@papr/shared/contracts'
import { useAdminWrite } from './useAdminWrite'
const props=defineProps<{csrfToken:string}>()
const emit=defineEmits<{openTemplate:[templateId:string,versionId:string]}>()
const uid=useId(),send=useAdminWrite(props.csrfToken)
const list=ref<AdminPaperList|null>(null),selected=ref<AdminPaperDetail|null>(null)
const dateFrom=ref(''),dateTo=ref(''),status=ref(''),owner=ref(''),version=ref(''),lookup=ref('')
const message=ref(''),reason=ref(''),question=ref(''),action=ref<'notice'|'withdraw'>('notice'),severity=ref<'info'|'error'>('info')
const busy=ref(false),error=ref(''),saved=ref('')
const pending=ref<{key:string;body:NoticeCreate;lock:number;paperId:string}|null>(null)
let applied=''
async function perform(work:()=>Promise<void>){if(busy.value)return;busy.value=true;error.value='';try{await work()}catch(e){error.value=e instanceof ApiError?e.message:'请求未确认，请重试。'}finally{busy.value=false}}
function search(more=false){void perform(async()=>{
  if(!more){const params=new URLSearchParams();for(const [key,value] of Object.entries({date_from:dateFrom.value,date_to:dateTo.value,status:status.value,owner_user_id:owner.value,template_version_id:version.value}))if(value)params.set(key,value);applied=params.toString()}
  const data=await requestData<AdminPaperList>('/admin/api/v1/papers?'+applied+(more&&list.value?.next_cursor?'&cursor='+encodeURIComponent(list.value.next_cursor):''))
  list.value=more&&list.value?{...data,items:[...list.value.items,...data.items]}:data
})}
function open(id:string){if(pending.value){error.value='请先确认当前说明的提交结果。';return}void perform(async()=>{selected.value=await requestData<AdminPaperDetail>('/admin/api/v1/papers/'+id);message.value=reason.value=question.value=saved.value='';action.value='notice';severity.value='info'})}
function submit(){void perform(async()=>{
  if(!selected.value)return
  pending.value??={key:crypto.randomUUID(),paperId:selected.value.id,lock:selected.value.lock_version,body:{question_id:question.value||null,message:message.value,severity:severity.value,action:action.value,reason:reason.value}}
  const attempt=pending.value
  try{selected.value=await send<AdminPaperDetail>('/admin/api/v1/papers/'+attempt.paperId+'/notices',attempt.body,'POST',attempt.lock,attempt.key);pending.value=null;saved.value='说明已保存。原题与答案快照保持不变。';message.value=reason.value=''}
  catch(e){if(e instanceof ApiError&&[401,403,409,422].includes(e.status))pending.value=null;throw e}
})}
onMounted(()=>search())
</script>
<template>
  <section class="card" :aria-labelledby="uid+'-title'"><h2 :id="uid+'-title'">试卷排查与勘误</h2>
    <p>默认查询最近7天，可按日期、匿名主体或来源版本排查；单次日期范围最多93天。</p>
    <p v-if="error" role="alert">{{error}}</p><p v-if="saved" role="status">{{saved}}</p>
    <fieldset :disabled="busy"><label :for="uid+'-from'">开始日期</label><input :id="uid+'-from'" v-model="dateFrom" type="date">
      <label :for="uid+'-to'">结束日期</label><input :id="uid+'-to'" v-model="dateTo" type="date">
      <label :for="uid+'-status'">试卷状态</label><select :id="uid+'-status'" v-model="status"><option value="">全部</option><option value="active">可用</option><option value="withdrawn">已撤下</option></select>
      <label :for="uid+'-owner'">匿名主体编号</label><input :id="uid+'-owner'" v-model="owner">
      <label :for="uid+'-version'">来源模板版本编号</label><input :id="uid+'-version'" v-model="version">
      <button @click="search()">查询试卷</button>
      <label :for="uid+'-id'">试卷编号</label><input :id="uid+'-id'" v-model="lookup"><button :disabled="!lookup" @click="open(lookup)">按编号查看</button>
    </fieldset>
    <p v-if="list&&!list.items.length">没有符合条件的试卷。</p>
    <article v-for="paper in list?.items??[]" :key="paper.id"><p>{{paper.title}} · {{paper.total_count}}题 · {{formatBeijingTime(paper.generated_at)}}· {{paper.status==='withdrawn'?'已撤下':'可用'}}</p><code>{{paper.id}}</code><button :disabled="busy||!!pending" @click="open(paper.id)">排查此卷</button></article>
    <button v-if="list?.has_more" :disabled="busy" @click="search(true)">更多试卷</button>
  </section>
  <section v-if="selected" class="card" :aria-labelledby="uid+'-detail'"><h2 :id="uid+'-detail'">试卷排查详情</h2>
    <p>{{selected.title}} · {{selected.status==='withdrawn'?'已撤下':'可用'}} · 匿名主体 {{selected.owner_user_id}}</p>
    <p v-for="source in selected.sources" :key="source.version_id">{{source.template_name}} · {{source.version_id}} <button @click="emit('openTemplate',source.template_id,source.version_id)">查看来源版本</button></p>
    <p v-for="notice in selected.notices??[]" :key="notice.id">{{notice.action==='withdraw'?'撤下':'说明'}}：{{notice.message}} · {{formatBeijingTime(notice.created_at)}}</p>
    <form @submit.prevent="submit"><fieldset :disabled="busy||!!pending">
      <label :for="uid+'-question'">关联题目</label><select :id="uid+'-question'" v-model="question"><option value="">整份试卷</option><option v-for="q in selected.questions" :key="q.id" :value="q.id">第{{q.position}}题</option></select>
      <label :for="uid+'-severity'">说明级别</label><select :id="uid+'-severity'" v-model="severity"><option value="info">一般说明</option><option value="error">内容错误</option></select>
      <label :for="uid+'-action'">处理方式</label><select :id="uid+'-action'" v-model="action"><option value="notice">追加说明，保留下载</option><option value="withdraw">撤下整卷，禁止下载打印</option></select>
      <label :for="uid+'-message'">用户可见说明</label><textarea :id="uid+'-message'" v-model="message" maxlength="2000" required></textarea>
      <label :for="uid+'-reason'">操作理由</label><input :id="uid+'-reason'" v-model="reason" maxlength="2000" required>
    </fieldset><button :disabled="busy||(!pending&&(!message.trim()||!reason.trim()))">{{pending?'确认说明提交结果':'保存试卷说明'}}</button></form>
    <QuestionSections :questions="selected.questions" show-answers />
  </section>
</template>
<style scoped>
fieldset{border:0;padding:0}label{display:block;margin-top:12px}input,select,textarea{max-width:100%;padding:8px}button{margin:8px}code{overflow-wrap:anywhere}article{border-top:1px solid #ddd;margin-top:12px}
</style>
