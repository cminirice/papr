<script setup lang="ts">
import {onMounted,ref} from 'vue'
import {requestData} from '@papr/shared/api'
import {formatBeijingTime} from '@papr/shared/time'
const rows=ref<{id:string;action:string;entity_id:string;created_at:string;detail:object}[]>([]),error=ref(''),more=ref(false)
async function load(append=false){try{const data=await requestData<typeof rows.value>(`/admin/api/v2/audit?offset=${append?rows.value.length:0}`);rows.value=append?[...rows.value,...data]:data;more.value=data.length===50}catch(e){error.value=String(e)}}
onMounted(()=>load())
</script>
<template><section class="card"><div class="toolbar"><h2>操作记录</h2><button @click="load()">刷新</button></div><p v-if="error" role="alert">{{error}}</p><div class="table-wrap"><table class="data-table"><thead><tr><th>时间</th><th>操作</th><th>对象</th><th>摘要</th></tr></thead><tbody><tr v-for="r in rows" :key="r.id"><td>{{formatBeijingTime(r.created_at)}}</td><td>{{r.action}}</td><td>{{r.entity_id}}</td><td>{{r.detail}}</td></tr></tbody></table></div><button v-if="more" @click="load(true)">加载更多</button></section></template>
