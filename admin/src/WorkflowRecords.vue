<script setup lang="ts">
import {onMounted,ref} from 'vue'
import {command} from './content-demo'
import {requestData} from '@papr/shared/api'
import {formatBeijingTime} from '@papr/shared/time'
import type {RecordItem} from '../../web/src/live-workflow'
import {statusLabel} from '../../web/src/live-workflow'
const note=ref(''),withdraw=ref(false)
async function saveNotice(){if(!selected.value)return;try{selected.value=await command<RecordItem>(`/papers/${selected.value.id}/notices`,{message:note.value,withdraw:withdraw.value});note.value='';await load()}catch(e){error.value=String(e)}}
const rows=ref<RecordItem[]>([]),error=ref(''),selected=ref<RecordItem|null>(null),offset=ref(0),hasMore=ref(false)
async function load(more=false){try{const data=await requestData<RecordItem[]>(`/admin/api/v2/operations?offset=${more?offset.value:0}&limit=50`);rows.value=more?[...rows.value,...data]:data;offset.value=rows.value.length;hasMore.value=data.length===50}catch(e){error.value=String(e)}}
onMounted(()=>load())
</script>
<template><p v-if="error" role="alert">{{error}}</p><section class="card"><div class="toolbar"><h2>生成记录</h2><button @click="load()">刷新</button></div><div class="table-wrap"><table class="data-table"><thead><tr><th>练习名称</th><th>题数</th><th>状态</th><th>提交时间</th><th>操作</th></tr></thead><tbody><tr v-for="r in rows" :key="r.id"><td>{{r.name}}</td><td>{{r.rules.reduce((n,r)=>n+r.count,0)}}</td><td>{{statusLabel(r.status)}}<small>{{r.error}}</small></td><td>{{formatBeijingTime(r.created)}}</td><td><button class="text-action" @click="selected=r">查看详情</button></td></tr></tbody></table></div><p v-if="!rows.length">暂无生成记录。</p><button v-if="hasMore" @click="load(true)">加载更多</button></section><section v-if="selected" class="card"><div class="toolbar"><h2>{{selected.name}}</h2><button class="secondary" @click="selected=null">关闭详情</button></div><p v-for="(r,i) in selected.rules" :key="i">{{r.point}} · {{r.kind}} · {{r.difficulty}} · {{r.count}}题</p><p v-for="a in selected.assets" :key="a.id"><a :href="`/admin/api/v2/artifacts/${a.id}`" target="_blank" rel="noopener">{{a.kind==='student_pdf'?'学生版':'解析版'}} · {{a.pages}}页</a></p><p v-for="n in selected.notices" :key="n">勘误：{{n}}</p><form v-if="selected.status==='succeeded'" @submit.prevent="saveNotice"><label for="paper-notice">勘误说明<textarea id="paper-notice" v-model="note" required></textarea></label><label><input v-model="withdraw" type="checkbox">撤回试卷并关闭用户下载</label><button>保存勘误</button></form></section></template>
