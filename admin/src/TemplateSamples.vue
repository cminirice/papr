<script setup lang="ts">
import {computed,nextTick,onUnmounted,ref} from 'vue'
import {requestData} from '@papr/shared/api'
import {demo,command,refreshWorkspace,publishTemplate,type Item,type WorkflowJob} from './content-demo'
const props=defineProps<{template:Item}>()
const current=computed(()=>demo.templates.find(t=>t.id===props.template.id)??props.template)
const versions=ref<{id:string;number:number;name:string;sealed:boolean;review_id:string|null}[]>([])
async function history(){versions.value=await requestData<typeof versions.value>(`/admin/api/v2/templates/${current.value.id}/versions`)}
async function rollback(version:typeof versions.value[number]){busy.value=true;try{await command(`/templates/${current.value.id}/publish`,{revision:current.value.revision,version_id:version.id,review_id:version.review_id});await refreshWorkspace();notice.value='已切换发布版本。'}catch(e){notice.value=e instanceof Error?e.message:'回退失败'}finally{busy.value=false}}
const publishedMessage=ref(''),publishResult=ref<HTMLElement|null>(null)
const notice=ref(''),busy=ref(false),answers=ref(false),comment=ref(''),job=ref<WorkflowJob|null>(null)
let timer:ReturnType<typeof setTimeout>|undefined
const preview=computed(()=>current.value.preview_job)
const pdf=computed(()=>preview.value?.status==='succeeded'?preview.value.assets.find(a=>a.kind===(answers.value?'solution_pdf':'student_pdf')):null)
async function poll(id:string){
 try{const data=await requestData<WorkflowJob>(`/admin/api/v2/jobs/${id}`);job.value=data
 if(['queued','running'].includes(data.status)){timer=setTimeout(()=>poll(id),1500);return}
 busy.value=false;await refreshWorkspace();notice.value=data.status==='succeeded'?'任务已完成。':`任务失败：${data.error??data.status}`
 }catch(e){busy.value=false;notice.value=e instanceof Error?e.message:'读取失败'}
}
async function start(kind:'preview'|'validate'){
 if(!current.value.version_id)return
 busy.value=true;notice.value=''
 try{const data=await command<WorkflowJob>(`/versions/${current.value.version_id}/jobs/${kind}`,{version_id:current.value.version_id,configuration_hash:current.value.configuration_hash},'POST',crypto.randomUUID());job.value=data;await poll(data.id)}catch(e){busy.value=false;notice.value=e instanceof Error?e.message:'提交失败'}
}
async function review(approved:boolean){
 busy.value=true
 try{await command(`/versions/${current.value.version_id}/review`,{preview_id:current.value.preview_job?.id,validation_id:current.value.validation_job?.id,approved,comment:comment.value});await refreshWorkspace();notice.value=approved?'审题通过，可以发布。':'已记录审题不通过，请修改模板。'}catch(e){notice.value=e instanceof Error?e.message:'保存失败'}finally{busy.value=false}
}
async function publish(){if(busy.value)return;busy.value=true;publishedMessage.value='';try{await publishTemplate(current.value);publishedMessage.value='发布成功！模板已开放，用户端可选择此模板生成练习。'}catch(e){publishedMessage.value=e instanceof Error?e.message:'发布失败，请重试'}finally{busy.value=false;await nextTick();publishResult.value?.scrollIntoView({block:'nearest'})}}
onUnmounted(()=>{if(timer)clearTimeout(timer)})
</script>
<template>
 <section class="template-samples" aria-label="样例题查看">
  <h3>样例题与发布</h3><p>按模板实际题数和排版生成完整样卷，完成验证与人工审题后发布。</p>
  <div class="actions"><button :disabled="busy||!current.version_id" @click="start('preview')">生成样例题查看</button><button :disabled="busy||!current.version_id" @click="start('validate')">运行自动验证</button><button class="secondary" @click="refreshWorkspace">刷新任务状态</button></div>
  <p v-if="notice" role="status">{{notice}}</p><p v-if="busy&&job">{{job.status}} · {{job.phase}}</p>
  <p v-if="current.published_version_id&&current.published_version_id!==current.version_id">当前编辑的是新草稿，用户端仍使用上一发布版本。</p><p>样例：{{current.preview_job?.status??'尚未生成'}} · 自动验证：{{current.validation_job?.status??'尚未验证'}}</p>
  <template v-if="pdf"><label><input v-model="answers" type="checkbox">显示答案与解析</label> <a :href="`/admin/api/v2/artifacts/${pdf.id}`" target="_blank" rel="noopener">打开PDF · {{pdf.pages}} 页</a><iframe :src="`/admin/api/v2/artifacts/${pdf.id}`" title="完整样卷PDF"></iframe></template>
  <label class="review-label" for="review-comment">审题意见<textarea id="review-comment" v-model="comment" rows="3" placeholder="检查题目、答案、难度及A4排版后填写意见"></textarea></label>
  <div class="actions"><button :disabled="busy||!comment.trim()||current.preview_job?.status!=='succeeded'||current.validation_job?.status!=='succeeded'" @click="review(true)">审题通过</button><button class="secondary" :disabled="busy||!comment.trim()||current.preview_job?.status!=='succeeded'||current.validation_job?.status!=='succeeded'" @click="review(false)">审题不通过</button><button :disabled="busy||!current.review_id" @click="publish">{{busy?'处理中…':'发布模板'}}</button></div><p v-if="publishedMessage" ref="publishResult" role="status" aria-live="polite" class="publish-result">{{publishedMessage}}</p>
  <button class="secondary" @click="history">查看版本历史</button><ul v-if="versions.length"><li v-for="v in versions" :key="v.id">版本 {{v.number}} · {{v.name}} · {{v.sealed?'已封存':'草稿'}} <button v-if="v.sealed&&v.review_id&&v.id!==current.published_version_id" class="text-action" :disabled="busy" @click="rollback(v)">回退到此版本</button></li></ul><p v-if="current.review_comment">最近审题：{{current.review_comment}}</p>
 </section>
</template>
<style scoped>
.publish-result{padding:16px;background:#eaf6ee;color:#18785d;border:1px solid #b8dfcc;border-radius:8px;font-weight:600}.template-samples{border-top:1px solid #e1e9e6;padding-top:24px;margin-top:28px}.actions{display:flex;gap:12px;flex-wrap:wrap}iframe{display:block;width:100%;height:850px;border:1px solid #ddd;margin:20px 0}.review-label{display:flex;flex-direction:column;gap:10px;margin:20px 0}
</style>
