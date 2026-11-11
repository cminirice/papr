<script setup lang="ts">
import { onMounted, ref, useId } from 'vue'
import { ApiError, requestData } from '@papr/shared/api'
import { formatBeijingTime } from '@papr/shared/time'
import type { SettingList, SettingView, CountSetting, GenerationSetting } from '@papr/shared/contracts'
import { useAdminWrite } from './useAdminWrite'
const props = defineProps<{csrfToken:string}>()
const uid=useId(), send=useAdminWrite(props.csrfToken)
const settings=ref<SettingList|null>(null), selected=ref<SettingView|null>(null)
const counts=ref<CountSetting>({choice:[],fill:[],answer:[]}), limits=ref<GenerationSetting>({queue_limit:10,ip_accept_limit:12})
const reason=ref(''),error=ref(''),saved=ref(''),busy=ref(false)
const labels={question_count_options:'题量档位',generation_limits:'生成限额',retention_policy:'历史保留'}
const kinds=['choice','fill','answer'] as const
const kindNames={choice:'选择题',fill:'填空题',answer:'解答题'}
async function load(){busy.value=true;error.value='';try{settings.value=await requestData<SettingList>('/admin/api/v1/settings');selected.value=null}catch(e){error.value=e instanceof ApiError?e.message:'配置加载失败，请重试'}finally{busy.value=false}}
function open(item:SettingView){selected.value=item;reason.value=saved.value=error.value='';if(item.key==='question_count_options')counts.value=JSON.parse(JSON.stringify(item.value)) as CountSetting;if(item.key==='generation_limits')limits.value={...item.value as GenerationSetting}}
async function save(){if(!selected.value||busy.value)return;busy.value=true;error.value='';saved.value='';try{
 const item=selected.value,value=item.key==='question_count_options'?counts.value:item.key==='generation_limits'?limits.value:{enabled:false}
 const result=await send<SettingView>('/admin/api/v1/settings/'+item.key,{value,schema_version:1,reason:reason.value},'PATCH',item.lock_version)
 selected.value=result;settings.value!.items=settings.value!.items.map(row=>row.key===result.key?result:row);saved.value='设置已保存';reason.value=''
}catch(e){error.value=e instanceof ApiError?e.message:'保存结果未确认，请重新加载核对'}finally{busy.value=false}}
onMounted(load)
</script>
<template>
 <section class="card" :aria-labelledby="uid+'-title'"><h2 :id="uid+'-title'">系统设置</h2>
 <p>题数在模板规则中配置，成功冷却固定为600秒。</p>
 <p v-if="error" role="alert">{{error}}</p><p v-if="saved" role="status">{{saved}}</p>
 <button :disabled="busy" @click="load">重新加载设置</button>
 <div v-if="settings"><button v-for="item in settings.items.filter(item=>item.key!=='question_count_options')" :key="item.key" :disabled="busy" @click="open(item)">{{labels[item.key]}}</button></div>
 <form v-if="selected" @submit.prevent="save"><fieldset :disabled="busy"><legend>{{labels[selected.key]}}</legend>
 <p>版本 {{selected.lock_version}} · {{selected.updated_at?formatBeijingTime(selected.updated_at):'系统默认值'}}</p>
 <template v-if="selected.key==='question_count_options'">
 <fieldset v-for="kind in kinds" :key="kind"><legend>{{kindNames[kind]}}</legend>
 <template v-for="n in [3,6,8,10,12]" :key="n"><input :id="uid+kind+n" v-model="counts[kind]" type="checkbox" :value="n"><label :for="uid+kind+n">{{kindNames[kind]}} {{n}}题</label></template></fieldset>
 <p>取消某题型的全部档位会关闭该题型。增加档位仍须有对应模板验证证据。</p>
 </template>
 <template v-else-if="selected.key==='generation_limits'">
 <label :for="uid+'-queue'">全局处理中任务上限</label><input :id="uid+'-queue'" v-model.number="limits.queue_limit" type="number" min="1" max="100" required>
 <label :for="uid+'-ip'">同IP每600秒受理上限</label><input :id="uid+'-ip'" v-model.number="limits.ip_accept_limit" type="number" min="1" max="120" required>
 <p>队列限额对生成、验证和预览的新任务同时生效；不取消已有任务。IP仅辅助限流，不合并用户身份。</p>
 </template>
 <p v-else>自动清理已关闭。本机试用保留历史，不自动删除。正式开放前另行确定保留周期和清理方案。</p>
 <label :for="uid+'-reason'">设置修改理由</label><input :id="uid+'-reason'" v-model="reason" required maxlength="2000">
 <button type="submit">保存设置</button></fieldset></form></section>
</template>
