<script setup lang="ts">
import { onMounted, ref, useId } from 'vue'
import { requestData, ApiError } from '@papr/shared/api'
import { formatBeijingTime } from '@papr/shared/time'
import type { OperationList } from '@papr/shared/contracts'
const uid=useId(),data=ref<OperationList|null>(null),busy=ref(false),error=ref('')
const filters=ref({date_from:'',date_to:'',admin_id:'',target_type:'',target_id:'',action:''})
const fields=[['date_from','操作开始日期'],['date_to','操作结束日期'],['admin_id','操作者编号'],['target_type','对象类型'],['target_id','对象编号'],['action','操作名称']] as const
let applied=''
async function search(more=false){if(busy.value)return;busy.value=true;error.value='';try{
 if(!more){const params=new URLSearchParams();for(const [key,value] of Object.entries(filters.value))if(value)params.set(key,value);applied=params.toString()}
 const result=await requestData<OperationList>('/admin/api/v1/operations?'+applied+(more&&data.value?.next_cursor?'&cursor='+encodeURIComponent(data.value.next_cursor):''))
 data.value=more&&data.value?{...result,items:[...data.value.items,...result.items]}:result
}catch(e){error.value=e instanceof ApiError?e.message:'查询失败，请重试'}finally{busy.value=false}}
onMounted(()=>search())
</script>
<template>
 <section class="card" :aria-labelledby="uid+'-title'"><h2 :id="uid+'-title'">操作记录</h2>
 <p>默认最近7天，单次最多93天。记录只读，不能在此修改历史。</p>
 <p v-if="error" role="alert">{{error}}</p>
 <form @submit.prevent="search()"><fieldset :disabled="busy"><template v-for="[key,label] in fields" :key="key">
 <label :for="uid+key">{{label}}</label><input :id="uid+key" v-model="filters[key]" :type="key.startsWith('date_')?'date':'text'">
 </template><button type="submit">查询操作记录</button></fieldset></form>
 <p v-if="data&&!data.items.length">没有符合条件的操作记录。</p>
 <article v-for="item in data?.items??[]" :key="item.id" class="card">
 <h3>{{item.action}} · {{item.target_type}}</h3><p>{{formatBeijingTime(item.created_at)}} · {{item.reason}}</p>
 <p>操作者：{{item.admin_id}} · 对象：{{item.target_id}}</p>
 <details><summary>查看变更详情</summary><p>请求编号：{{item.request_id}}</p><h4>修改前</h4><pre>{{JSON.stringify(item.before_summary,null,2)}}</pre><h4>修改后</h4><pre>{{JSON.stringify(item.after_summary,null,2)}}</pre></details>
 </article><button v-if="data?.has_more" :disabled="busy" @click="search(true)">加载更多操作记录</button>
 </section>
</template>
<style scoped>pre {white-space:pre-wrap;overflow-wrap:anywhere;} article p {overflow-wrap:anywhere;}</style>
