<script setup lang="ts">
import { computed, onMounted, ref, useId } from 'vue'
import { requestData, ApiError } from '@papr/shared/api'
import { formatBeijingTime } from '@papr/shared/time'
import type { AdminOverview } from '@papr/shared/contracts'
const emit=defineEmits<{navigate:[page:'catalogs'|'templates'|'operations']}>()
const uid=useId(),data=ref<AdminOverview|null>(null),busy=ref(false),error=ref(''),from=ref(''),to=ref('')
const maximum=computed(()=>Math.max(1,...(data.value?.daily.map(d=>Math.max(d.submitted ?? 0,d.succeeded ?? 0))??[])))
const cards=computed(()=>data.value?[
 {label:'成功出卷',value:data.value.totals.succeeded ?? 0,note:'已完成题目与双版 PDF'},
 {label:'受理任务',value:data.value.totals.submitted ?? 0,note:'统计周期内提交的任务'},
 {label:'活跃匿名主体',value:data.value.totals.active_subjects ?? 0,note:'按浏览器身份去重'},
 {label:'生成失败',value:data.value.totals.failed??0,note:'失败不启动新的冷却'},
]:[])
async function load(){if(busy.value)return;busy.value=true;error.value='';try{
 const params=new URLSearchParams();if(from.value)params.set('date_from',from.value);if(to.value)params.set('date_to',to.value)
 data.value=await requestData<AdminOverview>('/admin/api/v2/overview?'+params);from.value=data.value.date_from;to.value=data.value.date_to
}catch(e){error.value=e instanceof ApiError?e.message:'报表加载失败，请重试'}finally{busy.value=false}}
onMounted(load)
</script>
<template>
 <div class="dashboard">
  <div class="dashboard-intro"><div><h2>练习数据，一目了然</h2><p class="muted">查看出卷情况与使用趋势，开始今天的内容整理。</p></div><button @click="emit('navigate','templates')">管理模板 →</button></div>
  <section class="card report-range" aria-label="报表时间范围"><form @submit.prevent="load"><label :for="uid+'-from'">开始日期</label><input :id="uid+'-from'" v-model="from" type="date"><span class="muted">至</span><label class="sr-only" :for="uid+'-to'">结束日期</label><input :id="uid+'-to'" v-model="to" type="date"><button class="secondary" :disabled="busy">{{busy?'加载中…':'查询报表'}}</button><span class="muted range-note">默认最近 7 天</span></form></section>
  <p v-if="error" role="alert">{{error}}</p>
  <p v-if="busy&&!data" role="status">正在加载报表…</p>
  <template v-if="data">
   <div class="metric-grid"><article v-for="(card,index) in cards" :key="card.label" class="card metric"><div class="metric-label">{{card.label}}<span class="metric-symbol" aria-hidden="true">{{['▤','↗','◉','▧'][index]}}</span></div><strong>{{card.value.toLocaleString()}}</strong><small>{{card.note}}</small></article></div>
   <div class="dashboard-columns"><section class="card trend" aria-label="出卷趋势"><div class="toolbar"><h2>出卷趋势</h2><div class="chart-legend"><span>● 受理</span><span>● 成功</span></div></div><p class="muted period">{{data.date_from}} — {{data.date_to}}</p>
     <div v-if="data.daily.some(d=>d.submitted||d.succeeded)" class="bar-chart"><div v-for="day in data.daily" :key="day.date" class="chart-day" :title="`${day.date}：受理 ${day.submitted}，成功 ${day.succeeded}`"><div class="bar-pair"><span :style="{height:(day.submitted ?? 0)/maximum*100+'%'}"></span><span :style="{height:(day.succeeded ?? 0)/maximum*100+'%'}"></span></div><small>{{day.date.slice(5)}}</small></div></div>
     <div v-else class="chart-empty"><span aria-hidden="true">▥</span><strong>这段时间还没有出卷记录</strong><p>发布模板并开放题量后，使用数据会展示在这里。</p></div>
    </section>
    <section class="card queue-card" aria-label="当前任务"><h2>当前任务</h2><p class="muted">队列实时状态</p><div class="queue-line"><span>出卷排队</span><strong>{{data.generation_queue.queued}}</strong></div><div class="queue-line"><span>出卷执行中</span><strong>{{data.generation_queue.running}}</strong></div><div class="queue-line"><span>验证排队</span><strong>{{data.validation_queue.queued}}</strong></div><div class="queue-line"><span>验证执行中</span><strong>{{data.validation_queue.running}}</strong></div><button class="secondary" @click="emit('navigate','operations')">查看生成记录 →</button></section>
   </div>
   <section class="card" aria-label="每日明细"><div class="toolbar"><h2>每日明细</h2><span class="muted">更新于 {{formatBeijingTime(data.as_of)}}</span></div><div class="table-wrap"><table class="data-table"><thead><tr><th>日期</th><th>受理任务</th><th>成功出卷</th><th>失败</th><th>取消</th><th>活跃匿名主体</th></tr></thead><tbody><tr v-for="day in data.daily" :key="day.date"><td>{{day.date}}</td><td>{{day.submitted}}</td><td>{{day.succeeded}}</td><td>{{day.failed}}</td><td>{{day.cancelled}}</td><td>{{day.active_subjects}}</td></tr></tbody></table></div><p class="muted footnote">受理按提交日期，成功按出卷日期，失败与取消按结束日期统计；各项不一定相加相等。</p></section>
  </template>
 </div>
</template>
<style scoped>
.dashboard-intro { display:flex; justify-content:space-between; align-items:center; gap:16px; margin-bottom:22px; }.dashboard-intro h2 { margin:0; }.dashboard-intro p { margin:6px 0 0; }.report-range form { display:flex; align-items:center; flex-wrap:wrap; gap:12px; }.range-note { margin-left:auto; font-size:12px; }.metric-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:18px; margin-top:20px; }.metric-grid .metric { margin:0; }.metric-label { display:flex; justify-content:space-between; color:#64756e; }.metric-symbol { color:#07ac8e; background:#edf8f4; width:30px; text-align:center; border-radius:6px; }.metric strong { display:block; font-size:34px; margin:8px 0; font-weight:600; }.metric small { color:#8b9892; font-size:11px; }.dashboard-columns { display:grid; grid-template-columns:minmax(0,2fr) minmax(260px,1fr); gap:20px; margin-top:20px; }.dashboard-columns .card { margin:0; }.period,.footnote { font-size:12px; }.chart-legend { display:flex; gap:16px; font-size:12px; color:#a9dace; }.chart-legend span:last-child { color:#07ac8e; }.chart-empty { display:flex; flex-direction:column; align-items:center; justify-content:center; min-height:220px; color:#96a69e; background:repeating-linear-gradient(to bottom,#fff 0,#fff 54px,#f2f5f3 55px); }.chart-empty>span { font-size:40px; color:#bdcfc6; }.chart-empty strong { font-size:14px; font-weight:500; }.chart-empty p { font-size:12px; }.queue-line { display:flex; justify-content:space-between; padding:10px 0; border-bottom:1px solid #f0f3f1; }.queue-line strong { font-weight:600; }.queue-card button { width:100%; margin-top:18px; }.bar-chart { display:flex; gap:10px; height:220px; overflow-x:auto; }.chart-day { flex:1; min-width:24px; text-align:center; }.bar-pair { height:185px; display:flex; align-items:end; justify-content:center; gap:3px; border-bottom:1px solid #e3eae6; }.bar-pair span { width:14px; max-width:40%; background:#b4e1d5; border-radius:3px 3px 0 0; }.bar-pair span:last-child { background:#07ac8e; }.chart-day small { font-size:10px; color:#8b9892; }.sr-only { position:absolute; width:1px; height:1px; overflow:hidden; clip-path:inset(50%); }
@media(max-width:1100px){.metric-grid{grid-template-columns:repeat(2,minmax(0,1fr));}.dashboard-columns{grid-template-columns:1fr;}}@media(max-width:700px){.metric-grid{grid-template-columns:1fr;}.dashboard-intro{align-items:start;flex-direction:column;}.range-note{margin:0;}.dashboard .report-range{padding:14px;}}
</style>
