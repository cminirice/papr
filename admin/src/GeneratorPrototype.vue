<script setup lang="ts">
import { computed, ref } from 'vue'
import { demo, toggleComponent } from './content-demo'
import { generators, registry } from './generator-demo'
const query=ref(''),selected=ref(''),notice=ref('')
const generator=computed(()=>generators.find(g=>g.id===selected.value))
const rows=computed(()=>generators.filter(g=>`${g.name} ${g.id}`.includes(query.value)))
const nodes=(id:string)=>demo.nodes.filter(n=>n.generators.includes(id))
const catalogName=(id:string)=>demo.catalogs.find(c=>c.id===id)?.name??''
async function toggle(id:string){try{await toggleComponent(id);notice.value='组件状态已更新。'}catch(e){notice.value=e instanceof Error?e.message:'保存失败'}}
</script>
<template>
 <p v-if="notice" role="status">{{notice}}</p>
 <template v-if="!generator"><section class="card"><div class="toolbar"><div><h2>出题组件</h2><p class="muted">查看组件支持的题型和难度。二级目录关联在目录管理中维护。</p></div></div><div class="filters-row"><label for="generator-search">组件名称或编码<input id="generator-search" v-model="query" placeholder="搜索出题组件"></label></div>
 <div class="table-wrap"><table class="data-table"><thead><tr><th>组件名称 / 编码</th><th>支持题型</th><th>关联二级目录</th><th>版本 / 状态</th><th>操作</th></tr></thead><tbody><tr v-for="g in rows" :key="g.id"><td><strong>{{g.name}}</strong><small>{{g.id}}</small></td><td>{{g.capabilities.map(c=>c.kind).join('、')}}</td><td>{{nodes(g.id).length}} 个二级目录</td><td>{{g.version}}<small>{{registry[g.id]?'可用':'停用'}}</small></td><td><button class="text-action" @click="selected=g.id">能力详情</button><button class="text-action" @click="toggle(g.id)">{{registry[g.id]?'停用':'启用'}}</button></td></tr></tbody></table></div><p v-if="!rows.length" class="empty-state">没有符合条件的组件。</p></section></template>
 <template v-else><button class="secondary back-link" @click="selected=''">← 返回组件列表</button><section class="card"><div class="toolbar"><div><h2>{{generator.name}}</h2><p class="muted">{{generator.id}} · v{{generator.version}}</p></div><span class="status-tag" :class="{enabled:registry[generator.id]}">{{registry[generator.id]?'可用':'停用'}}</span></div><p>{{generator.description}}</p><h3>支持能力</h3><div class="table-wrap"><table class="data-table"><thead><tr><th>题型</th><th>难度</th><th>训练说明</th></tr></thead><tbody><tr v-for="c in generator.capabilities" :key="c.kind"><td>{{c.kind}}</td><td>{{c.difficulties.join('、')}}</td><td>{{c.sample}}</td></tr></tbody></table></div><h3>关联二级目录</h3><div class="table-wrap"><table class="data-table"><thead><tr><th>目录</th><th>二级目录</th><th>状态</th></tr></thead><tbody><tr v-for="n in nodes(generator.id)" :key="n.id"><td>{{catalogName(n.catalog)}}</td><td>{{n.name}}</td><td>{{n.status}}</td></tr></tbody></table></div><p v-if="!nodes(generator.id).length" class="empty-state">暂未关联二级目录，可到目录管理中添加关联。</p></section></template>
</template>
