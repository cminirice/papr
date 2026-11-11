<script setup lang="ts">
import { computed, ref } from 'vue'
import { blank, demo, persistItem, hasLocalConfiguration, importLocalConfiguration, type Item } from './content-demo'
import { generators, registry } from './generator-demo'
const view=ref<'tree'|'edit'|'mapping'>('tree'),level=ref<1|2>(1),draft=ref<Item>(blank()),original=ref(''),query=ref(''),notice=ref(''),error=ref(''),discard=ref(false)
const busy=ref(false)
const collapsed=ref<string[]>([])
const matches=(item:Item)=>[item.name,item.code].join(' ').includes(query.value.trim())
const children=(id:string)=>demo.nodes.filter(n=>n.catalog===id).sort((a,b)=>a.sort-b.sort)
const roots=computed(()=>demo.catalogs.filter(c=>matches(c)||children(c.id).some(matches)))
const visibleChildren=(root:Item)=>children(root.id).filter(n=>!query.value.trim()||matches(root)||matches(n))
const expanded=(id:string)=>!!query.value.trim()||!collapsed.value.includes(id)
const name=computed(()=>level.value===1?'一级目录':'二级目录')
const parentName=computed(()=>demo.catalogs.find(c=>c.id===draft.value.catalog)?.name??'')
function toggle(id:string){collapsed.value=collapsed.value.includes(id)?collapsed.value.filter(c=>c!==id):[...collapsed.value,id]}
function open(depth:1|2,item?:Item,parent='',screen:'edit'|'mapping'='edit'){
 if(busy.value)return
 level.value=depth;draft.value=JSON.parse(JSON.stringify(item??blank()));if(!item)draft.value.catalog=parent
 original.value=JSON.stringify(draft.value);view.value=screen;notice.value='';error.value=''
}
function back(){if(JSON.stringify(draft.value)!==original.value)discard.value=true;else view.value='tree'}
async function save(){
 const d=draft.value;error.value=''
 if(!d.name.trim()||!d.code.trim()){error.value='请填写名称和编码。';return}
 if(level.value===2&&!demo.catalogs.some(c=>c.id===d.catalog)){error.value='请选择所属一级目录。';return}
 const collection=level.value===1?demo.catalogs:demo.nodes
 if(collection.some(c=>c.id!==d.id&&c.code===d.code.trim()&&(level.value===1||c.catalog===d.catalog))){error.value='编码已存在，请更换编码。';return}
 busy.value=true
 try{
  const saved=await persistItem(level.value===1?'catalogs':'nodes',d)
  notice.value=`${name.value}已保存。`
  if(level.value===2)collapsed.value=collapsed.value.filter(id=>id!==saved.catalog)
 }catch(e){error.value=e instanceof Error?e.message:'保存失败';return}finally{busy.value=false}
 view.value='tree'
}
async function changeStatus(item:Item){busy.value=true;try{await persistItem(item.catalog?'nodes':'catalogs',{...item,status:item.status==='启用'?'停用':'启用'});notice.value='状态已更新。'}catch(e){notice.value=e instanceof Error?e.message:'保存失败'}finally{busy.value=false}}
async function importSaved(){try{await importLocalConfiguration();notice.value='配置已导入，模板保持草稿，请验证审题后发布。'}catch(e){notice.value=e instanceof Error?e.message:'导入失败'}}
const generatorName=(id:string)=>generators.find(g=>g.id===id)?.name??id
</script>
<template>
 <div class="content-workspace">
  <p v-if="notice" role="status">{{notice}}</p>
  <section v-if="view==='tree'" class="card">
   <div class="toolbar"><div><h2>目录管理</h2><p class="muted">一级目录组织内容，二级目录关联出题组件，供模板选择使用。</p></div><button :disabled="busy" @click="open(1)">＋ 新建一级目录</button></div>
   <p v-if="!demo.catalogs.length&&hasLocalConfiguration()"><button :disabled="busy" class="secondary" @click="importSaved">导入此浏览器已有配置</button></p><div class="filters-row"><label for="directory-search">搜索目录<input id="directory-search" v-model="query" placeholder="目录名称或编码"></label><button :disabled="busy" class="secondary" @click="query=''">重置</button><button :disabled="busy" class="secondary" @click="collapsed=[]">全部展开</button><button :disabled="busy" class="secondary" @click="collapsed=demo.catalogs.map(c=>c.id);query=''">全部收起</button></div>
   <div class="table-wrap"><table class="data-table directory-tree"><thead><tr><th>目录名称 / 编码</th><th>层级</th><th>出题组件</th><th>状态</th><th>操作</th></tr></thead><tbody>
    <template v-for="root in roots" :key="root.id">
     <tr class="root-row"><td><div class="tree-name"><button :disabled="busy" class="text-action expander" :aria-label="(expanded(root.id)?'收起':'展开')+root.name" :aria-expanded="expanded(root.id)" @click="toggle(root.id)">{{expanded(root.id)?'▾':'▸'}}</button><div><strong>{{root.name}}</strong><small>{{root.code}} · {{children(root.id).length}} 个二级目录</small></div></div></td><td>一级目录</td><td>—</td><td>{{root.status}}</td><td><button :disabled="busy" class="text-action" @click="open(1,root)">编辑</button><button :disabled="busy" class="text-action" @click="open(2,undefined,root.id)">添加二级目录</button><button :disabled="busy" class="text-action" @click="changeStatus(root)">{{root.status==='启用'?'停用':'启用'}}</button></td></tr>
     <template v-if="expanded(root.id)">
      <tr v-for="leaf in visibleChildren(root)" :key="leaf.id"><td><div class="tree-name leaf-name"><span aria-hidden="true">└</span><div><strong>{{leaf.name}}</strong><small>{{leaf.code}}</small></div></div></td><td>二级目录</td><td><span v-if="!leaf.generators.length" class="muted">未关联</span><div v-for="id in leaf.generators" :key="id">{{generatorName(id)}}<small v-if="registry[id]===false">已停用</small></div></td><td>{{leaf.status}}</td><td><button :disabled="busy" class="text-action" @click="open(2,leaf)">编辑</button><button :disabled="busy" class="text-action" @click="open(2,leaf,'','mapping')">关联组件</button><button :disabled="busy" class="text-action" @click="changeStatus(leaf)">{{leaf.status==='启用'?'停用':'启用'}}</button></td></tr>
      <tr v-if="!children(root.id).length"><td colspan="5" class="empty-leaf">暂无二级目录，点击“添加二级目录”开始维护。</td></tr>
     </template>
    </template>
   </tbody></table></div><p v-if="!roots.length" class="empty-state">{{query?'没有符合条件的目录。':'尚无目录，请先新建一级目录。'}}</p>
  </section>
  <template v-else>
   <button :disabled="busy" class="secondary back-link" @click="back">← 返回目录树</button>
   <section class="card"><h2>{{view==='mapping'?'关联出题组件':(draft.id?'编辑':'新建')+name}}</h2><p v-if="level===2" class="muted">{{parentName}} / {{draft.name||'新建二级目录'}}</p><p v-if="error" role="alert">{{error}}</p>
    <form v-if="view==='edit'" @submit.prevent="save"><div class="directory-form">
     <label for="directory-name">{{name}}名称<input id="directory-name" v-model="draft.name" maxlength="120" required></label>
     <label for="directory-code">{{name}}编码<input id="directory-code" v-model="draft.code" pattern="[A-Z][A-Z0-9_]{0,63}" title="以大写字母开头，仅使用大写字母、数字、下划线" required></label>
     <label v-if="level===2" for="directory-parent"><span id="directory-parent-label">所属一级目录</span><select id="directory-parent" v-model="draft.catalog" aria-labelledby="directory-parent-label" :disabled="!!draft.id" required><option value="">请选择一级目录</option><option v-for="c in demo.catalogs" :key="c.id" :value="c.id">{{c.name}}</option></select></label>
     <label v-if="level===2" for="directory-sort">排序值<input id="directory-sort" v-model.number="draft.sort" type="number" min="0" max="100000" required></label>
     <label for="directory-description">说明<textarea id="directory-description" v-model="draft.description" rows="3"></textarea></label>
    </div><footer><button :disabled="busy" type="button" class="secondary" @click="back">取消</button><button :disabled="busy" type="submit">保存{{name}}</button></footer></form>
    <template v-else><p class="muted">一个二级目录可关联多个出题组件，模板再选择组件、题型、难度和题数。</p><div class="component-options"><label v-for="g in generators" :key="g.id"><input v-model="draft.generators" type="checkbox" :value="g.id"><span><strong>{{g.name}}</strong><small>{{g.description}}</small></span></label></div><footer><button :disabled="busy" class="secondary" @click="back">取消</button><button :disabled="busy" @click="save">保存组件关联</button></footer></template>
   </section>
  </template>
  <div v-if="discard" class="discard-overlay"><section class="card" role="dialog" aria-modal="true" aria-label="放弃未保存的修改"><h2>放弃未保存的修改？</h2><button :disabled="busy" class="secondary" @click="discard=false">继续编辑</button> <button :disabled="busy" @click="discard=false;view='tree'">放弃修改并返回</button></section></div>
 </div>
</template>
<style scoped>
.tree-name{display:flex;align-items:center;gap:12px;min-width:240px}.leaf-name{padding-left:40px}.leaf-name>span{color:#b3c6bf}.root-row{background:#f3f8f6}.directory-tree th:last-child{min-width:240px}.empty-leaf{padding-left:65px;color:#81958c}.directory-form{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px;max-width:850px}.directory-form label{display:flex;flex-direction:column;gap:8px}.component-options{display:grid;gap:12px}.component-options label{display:flex;gap:14px;align-items:center;border:1px solid #e0e8e4;padding:16px;border-radius:8px}.component-options small{display:block;margin-top:6px;color:#80928b}footer{display:flex;gap:12px;justify-content:flex-end;margin-top:24px}.discard-overlay{position:fixed;inset:0;background:#152b2355;z-index:60;display:grid;place-items:center}@media(max-width:900px){.directory-form{grid-template-columns:1fr}}
</style>
