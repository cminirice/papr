<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import TemplateSamples from './TemplateSamples.vue'
import { blank, demo, persistItem, disableTemplate, type Entity, type Item, type Rule } from './content-demo'
import { generators, registry, compatible, kinds, difficulties, ruleIssue, templateIssue, selectComponent, selectKind, selectDifficulty } from './generator-demo'
const props=defineProps<{mode:'templates'}>()
const entity=ref<Entity>(props.mode),view=ref<'list'|'edit'|'mapping'|'preview'>('list')
const catalogId=ref(''),query=ref(''),status=ref(''),notice=ref(''),error=ref(''),tagInput=ref('')
const draft=ref<Item>(blank()),original=ref(''),discard=ref(false),pending=ref<null|(()=>void)>(null)
const label=computed(()=>({catalogs:'目录',nodes:'节点',templates:'模板'})[entity.value])
const catalog=computed(()=>demo.catalogs.find(c=>c.id===catalogId.value))
const rows=computed(()=>demo[entity.value].filter(x=>(entity.value!=='nodes'||x.catalog===catalogId.value)&&(!status.value||x.status===status.value)&&(!query.value||[x.name,x.code,x.primaryCategory,x.secondaryCategory,...x.tags].join(' ').includes(query.value))).sort((a,b)=>entity.value==='nodes'?a.sort-b.sort:0))
const layoutKinds=['竖式计算','选择题','填空题','解答题','判断题','应用题']
const layoutSummary=computed(()=>[...new Set(draft.value.rules.map(r=>r.kind))].filter(Boolean).map(k=>`${k}每行 ${draft.value.columns_by_kind?.[k]??draft.value.columns} 题`).join(' · '))
const total=computed(()=>draft.value.rules.reduce((n,r)=>n+(Number(r.count)||0),0))
const topics=computed(()=>demo.nodes.filter(n=>n.catalog===draft.value.catalog&&n.generators.length>0))
const nodeName=(id:string)=>demo.nodes.find(n=>n.id===id)?.name??'待选择二级目录'
const generatorName=(id:string)=>generators.find(g=>g.id===id)?.name??'待选择组件'
const catalogName=(id:string)=>demo.catalogs.find(c=>c.id===id)?.name??'待选择目录'
const tagSuggestions=['专项','真题','基础巩固','综合提升','乘法','大数读写']
function addTag(value=tagInput.value){const tag=value.trim();if(tag&&!draft.value.tags.includes(tag))draft.value.tags.push(tag);tagInput.value=''}
const dirty=computed(()=>['edit','mapping','preview'].includes(view.value)&&JSON.stringify(draft.value)!==original.value)
function leave(action:()=>void){if(dirty.value){pending.value=action;discard.value=true}else action()}
function back(){leave(()=>{view.value='list';error.value=''})}
function up(){entity.value='catalogs';catalogId.value='';query.value='';status.value='';notice.value=''}
watch(()=>props.mode,()=>{entity.value=props.mode;view.value='list';catalogId.value='';query.value='';status.value='';notice.value='';error.value=''})
function open(item?:Item,screen:'edit'|'mapping'|'preview'='edit'){
 draft.value=JSON.parse(JSON.stringify(item??blank()));if(!item)draft.value.catalog=catalogId.value
 original.value=JSON.stringify(draft.value);view.value=screen;error.value='';notice.value='';tagInput.value=''
}
function nodes(id:string){entity.value='nodes';catalogId.value=id;query.value='';status.value='';notice.value=''}

async function save(){
 const d=draft.value;error.value=''
 if(!d.code.trim()||!d.name.trim()){error.value='请填写编码和名称。';return}
 if(demo[entity.value].some(x=>x.id!==d.id&&x.code===d.code.trim()&&(entity.value!=='nodes'||x.catalog===d.catalog))){error.value='编码已存在，请换一个编码。';return}
 if(entity.value==='templates'){
  if(!d.catalog){error.value='请先选择一级目录。';return}
  if(d.rules.some(r=>!Number.isInteger(r.count)||r.count<1||r.count>100)){error.value='题数应为1–100的整数。';return}
  if(new Set(d.rules.map(r=>[r.node,r.generator,r.kind,r.difficulty].join('|'))).size!==d.rules.length){error.value='存在相同的出题规则，请合并题数。';return}
  if(templateIssue(d))d.status='草稿'
  addTag()
 }
 try{draft.value=await persistItem(entity.value,d);original.value=JSON.stringify(draft.value);view.value='list';notice.value=`${label.value}已保存。`;return true}catch(e){error.value=e instanceof Error?e.message:'保存失败';return false}
}
async function toggle(item:Item){if(item.status!=='启用'){open(item,'preview');notice.value='请完成完整样例、自动验证与人工审题后发布。';return}try{await disableTemplate(item);notice.value='模板已停用。'}catch(e){notice.value=e instanceof Error?e.message:'停用失败'}}

function changeCatalog(){for(const r of draft.value.rules)if(!topics.value.some(n=>n.id===r.node)){r.node='';r.generator='';r.kind='';r.difficulty=''}}
async function preview(){addTag();error.value='';if(dirty.value||!draft.value.id){if(!await save())return}view.value='preview'}
function addRule(){draft.value.rules.push({node:'',generator:'',kind:'',difficulty:'',count:3})}
function descends(id:string,target:string){const seen=new Set<string>();let n=demo.nodes.find(n=>n.id===id);while(n?.parent){if(n.parent===target)return true;if(seen.has(n.parent))break;seen.add(n.parent);n=demo.nodes.find(x=>x.id===n!.parent)}return false}
const parents=computed(()=>demo.nodes.filter(n=>n.catalog===catalogId.value&&n.id!==draft.value.id&&!descends(n.id,draft.value.id)))
function switchType(){if(draft.value.type==='分组')draft.value.generators=[]}
function availableRules(r:Rule){return ruleIssue(r)}
</script>

<template>
 <div class="content-workspace">
  <p v-if="notice" role="status" class="content-success">{{notice}}</p>
  <template v-if="view==='list'">
   <button v-if="entity==='nodes'" class="secondary back-link" @click="up">← 返回目录列表</button>
   <section class="card">
    <div class="toolbar"><div><h2>{{entity==='nodes'?catalog?.name:label+'管理'}}</h2><p class="muted">{{entity==='nodes'?'用二级目录组织练习内容，每个二级目录可关联多个出题组件。':entity==='templates'?'为练习取一个易懂的名字，配置内容并添加便于查找的标签。':'分别维护目录信息与二级目录结构。'}}</p></div><button @click="open()">＋ 新建{{label}}</button></div>
    <div class="filters-row"><label for="content-search">搜索{{label}}<input id="content-search" v-model="query" placeholder="名称、编码或标签"></label><label for="content-status">状态<select id="content-status" v-model="status"><option value="">全部状态</option><option>草稿</option><option>启用</option><option>停用</option></select></label><button class="secondary" @click="query='';status=''">重置</button></div>
    <div class="table-wrap"><table class="data-table"><thead><tr><th>{{label}}名称 / 编码</th><th>{{entity==='catalogs'?'一级分类 · 二级分类':entity==='nodes'?'类型 / 上级':'标签'}}</th><th>{{entity==='catalogs'?'节点数量':entity==='nodes'?'出题组件':'内容配置'}}</th><th>状态</th><th class="content-actions">操作</th></tr></thead><tbody>
     <tr v-for="row in rows" :key="row.id"><td><strong>{{row.name}}</strong><small>{{row.code}}</small></td><td><template v-if="entity==='catalogs'">{{row.primaryCategory}} · {{row.secondaryCategory}}</template><template v-else-if="entity==='nodes'">{{row.type}}<small>{{row.parent?nodeName(row.parent):'顶层'}}</small></template><div v-else class="tag-list"><span v-for="tag in row.tags" :key="tag" class="content-tag">{{tag}}</span></div></td>
     <td><template v-if="entity==='catalogs'">{{demo.nodes.filter(n=>n.catalog===row.id).length}} 个节点</template><template v-else-if="entity==='nodes'"><span v-if="!row.generators.length">{{row.type==='分组'?'—':'未关联'}}</span><div v-for="id in row.generators" :key="id">{{generatorName(id)}}<small v-if="registry[id]===false">已停用</small></div></template><template v-else>{{row.rules.reduce((sum,r)=>sum+r.count,0)}} 题 · {{row.rules.length}} 条规则<small>{{catalogName(row.catalog)}}</small></template></td>
     <td><span class="status-tag" :class="{enabled:row.status==='启用'}">{{row.status}}</span><small v-if="entity==='templates'&&templateIssue(row)" class="content-warning">待完善配置</small></td>
     <td class="content-actions"><button class="text-action" @click="open(row)">{{entity==='templates'?'配置模板':'编辑'+label}}</button><button v-if="entity==='catalogs'" class="text-action" @click="nodes(row.id)">节点管理</button><button v-if="entity==='nodes'&&row.type==='二级目录'" class="text-action" @click="open(row,'mapping')">关联组件</button><button v-if="entity==='templates'" class="text-action" @click="open(row,'preview')">组卷预览</button><button class="text-action" @click="toggle(row)">{{row.status==='启用'?'停用':'审题发布'}}</button></td></tr>
    </tbody></table></div><div v-if="!rows.length" class="empty-state">{{query||status?'没有符合条件的记录。':'还没有'+label+'，点击右上角新建。'}}</div><div class="list-footer">共 {{rows.length}} 条</div>
   </section>
  </template>
  <template v-else>
   <button class="secondary back-link" @click="back">← 返回{{label}}列表</button>
   <section class="card"><div class="toolbar"><div><h2>{{view==='mapping'?'关联出题组件':view==='preview'?'组卷预览':(draft.id?'编辑':'新建')+label}}</h2><p class="muted">{{view==='mapping'?draft.name+' · 选择该二级目录可使用的组件':view==='preview'?draft.name:entity==='nodes'?catalog?.name:'填写完成后保存。'}}</p></div><span v-if="view==='edit'" class="status-tag">{{draft.status}}</span></div>
    <p v-if="error" role="alert" class="content-error">{{error}}</p>
    <form v-if="view==='edit'" @submit.prevent="save">
     <div class="content-form-grid">
      <label for="content-name"><span>{{label}}名称 <b>*</b></span><input id="content-name" v-model="draft.name" required maxlength="120" :placeholder="entity==='templates'?'例如：每天十分钟 · 乘法巩固':'请输入名称'"></label>
      <label for="content-code"><span>{{label}}编码 <b>*</b></span><input id="content-code" v-model="draft.code" required pattern="[A-Z][A-Z0-9_]{0,63}" title="以大写字母开头，仅使用大写字母、数字、下划线" placeholder="例如 MULTIPLICATION"></label>
      <template v-if="entity==='nodes'"><label for="content-type"><span id="content-type-label">节点类型</span><select aria-labelledby="content-type-label" id="content-type" v-model="draft.type" @change="switchType"><option>二级目录</option><option>分组</option></select><small>二级目录用于配置练习，分组用于组织目录层级。</small></label><label for="content-parent"><span id="content-parent-label">父节点</span><select aria-labelledby="content-parent-label" id="content-parent" v-model="draft.parent"><option value="">顶层</option><option v-for="p in parents" :key="p.id" :value="p.id">{{p.name}}</option></select></label><label for="content-sort">排序值<input id="content-sort" v-model.number="draft.sort" type="number" min="0" max="100000" required></label></template>
      <label class="content-wide" for="content-description">说明<textarea id="content-description" v-model="draft.description" rows="2" placeholder="简要说明用途与练习内容"></textarea></label>
     </div>
     <template v-if="entity==='templates'">
      <div class="content-divider"></div><h3>模板标签</h3><p class="muted">标签会显示在用户端，帮助家长快速找到练习。标签可按内容、用途自由添加。</p>
      <div class="tag-list"><button v-for="tag in draft.tags" :key="tag" type="button" class="content-tag removable" :aria-label="'移除标签'+tag" @click="draft.tags=draft.tags.filter(t=>t!==tag)">{{tag}} ×</button></div>
      <div class="tag-input"><label for="content-tag">添加标签<input id="content-tag" v-model="tagInput" maxlength="30" placeholder="例如：大数读写、专项、真题" @keydown.enter.prevent="addTag()"></label><button type="button" class="secondary" @click="addTag()">添加</button></div>
      <div class="tag-list tag-suggestions"><span class="muted">常用标签</span><button v-for="tag in tagSuggestions.filter(t=>!draft.tags.includes(t))" :key="tag" type="button" class="text-action" @click="addTag(tag)">＋ {{tag}}</button></div>
      <div class="content-divider"></div><h3>练习内容</h3><div class="content-form-grid"><label for="content-catalog"><span id="content-catalog-label">一级目录</span> <select aria-labelledby="content-catalog-label" id="content-catalog" v-model="draft.catalog" required @change="changeCatalog"><option value="">请先选择一级目录</option><option v-for="c in demo.catalogs" :key="c.id" :value="c.id">{{c.name}}</option></select></label></div>
      <div class="toolbar content-rule-head"><p class="muted">选择目录下的二级目录，再选择已关联组件；每条规则可使用不同题型和难度。</p><button type="button" class="secondary" :disabled="!draft.catalog" @click="addRule">＋ 添加出题规则</button></div>
      <p v-if="draft.catalog&&!topics.length" class="content-warning">当前目录下没有已关联出题组件的二级目录，请先到目录管理中关联组件。</p>
      <div class="table-wrap"><table class="data-table rule-table"><thead><tr><th>二级目录</th><th>出题组件</th><th>题型</th><th>难度</th><th>题数</th><th>操作</th></tr></thead><tbody><tr v-for="(r,i) in draft.rules" :key="i"><td><select v-model="r.node" :aria-label="'规则'+(i+1)+'二级目录'" @change="selectComponent(r)"><option value="">请选择二级目录</option><option v-if="r.node&&!topics.some(n=>n.id===r.node)" :value="r.node" disabled>{{nodeName(r.node)}}（未关联组件，请重新选择）</option><option v-for="n in topics" :key="n.id" :value="n.id">{{n.name}}</option></select><small v-if="availableRules(r)" class="content-warning">{{availableRules(r)}}</small></td><td><select v-model="r.generator" :aria-label="'规则'+(i+1)+'出题组件'" :disabled="!compatible(r.node).length" @change="selectKind(r)"><option value="">请选择组件</option><option v-if="r.generator&&!compatible(r.node).some(g=>g.id===r.generator)" :value="r.generator">{{generatorName(r.generator)}}（不可用）</option><option v-for="g in compatible(r.node)" :key="g.id" :value="g.id">{{g.name}}</option></select></td><td><select v-model="r.kind" :aria-label="'规则'+(i+1)+'题型'" :disabled="!kinds(r.node,r.generator).length" @change="selectDifficulty(r)"><option v-if="!kinds(r.node,r.generator).includes(r.kind)" :value="r.kind">{{r.kind||'请选择题型'}}</option><option v-for="kind in kinds(r.node,r.generator)" :key="kind">{{kind}}</option></select></td><td><select v-model="r.difficulty" :aria-label="'规则'+(i+1)+'难度'" :disabled="!difficulties(r).length"><option v-if="!difficulties(r).includes(r.difficulty)" :value="r.difficulty">{{r.difficulty||'请选择难度'}}</option><option v-for="d in difficulties(r)" :key="d">{{d}}</option></select></td><td><input v-model.number="r.count" :aria-label="'规则'+(i+1)+'题数'" type="number" min="1" max="100" required></td><td><button type="button" class="text-action" @click="draft.rules.splice(i,1)">移除</button></td></tr></tbody></table></div>
      <p v-if="!draft.rules.length" class="empty-state">先选择一级目录，再添加出题规则。</p><div class="content-summary"><span>{{new Set(draft.rules.filter(r=>r.node).map(r=>r.node)).size}} 个二级目录 · {{draft.rules.length}} 条规则</span><strong>整卷合计 {{total}} 题</strong></div>
      <h3>按题型设置排版</h3><p class="muted">同一题型使用相同列数，学生版和解析版均按此设置排版。</p><div v-if="draft.columns_by_kind" class="content-form-grid"><label v-for="(kind,i) in layoutKinds" :key="kind" :for="'content-columns-'+i"><span :id="'content-columns-label-'+i">{{kind}}每行题数</span><select :aria-labelledby="'content-columns-label-'+i" :id="'content-columns-'+i" v-model.number="draft.columns_by_kind[kind]"><option v-for="n in 5" :key="n" :value="n">{{n}} 道</option></select></label></div>
     </template>
     <footer class="content-footer"><button type="button" class="secondary" @click="back">取消</button><button v-if="entity==='templates'" type="button" class="secondary" @click="preview">组卷预览</button><button type="submit">保存{{label}}</button></footer>
    </form>
    <template v-else-if="view==='mapping'">
     <p class="muted">一个二级目录可关联多个组件，具体使用哪个组件由模板决定。组件与二级目录是否匹配，由内容审核确认。</p>
     <div class="content-mapping"><label v-for="g in generators" :key="g.id"><input v-model="draft.generators" type="checkbox" :value="g.id"><span><strong>{{g.name}}</strong><small>{{g.description}}</small><small>{{g.capabilities.map(c=>c.kind).join(' / ')}} · {{registry[g.id]?'可用':'停用'}}</small></span></label></div>
     <p class="muted">已选择 {{draft.generators.length}} 个组件。</p><footer class="content-footer"><button class="secondary" @click="back">取消</button><button @click="save">保存组件关联</button></footer>
    </template>
    <template v-else>
     <div class="tag-list"><span v-for="tag in draft.tags" :key="tag" class="content-tag">{{tag}}</span></div><div class="content-summary"><span>{{catalogName(draft.catalog)}} · {{layoutSummary}}</span><strong>总计 {{total}} 题</strong></div>
     <div class="table-wrap"><table class="data-table"><thead><tr><th>二级目录</th><th>出题组件</th><th>题型</th><th>难度</th><th>题数</th></tr></thead><tbody><tr v-for="(r,i) in draft.rules" :key="i"><td>{{nodeName(r.node)}}</td><td>{{generatorName(r.generator)}}</td><td>{{r.kind||'待配置'}}<small class="content-warning">{{ruleIssue(r)}}</small></td><td>{{r.difficulty||'待配置'}}</td><td>{{r.count}}</td></tr></tbody></table></div>
     <TemplateSamples :key="JSON.stringify(draft)" :template="draft" />
     <footer class="content-footer"><button @click="view='edit'">返回编辑模板</button></footer>
    </template>
   </section>
  </template>
  <div v-if="discard" class="content-overlay"><section role="dialog" aria-modal="true" aria-labelledby="discard-title" class="card"><h2 id="discard-title">放弃未保存的修改？</h2><p>本次未保存的内容将丢失。</p><div class="toolbar-actions"><button class="secondary" @click="discard=false;pending=null">继续编辑</button><button @click="discard=false;pending?.();pending=null">放弃修改并返回</button></div></section></div>
 </div>
</template>
<style scoped>
.content-actions{min-width:240px}.content-form-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:22px;max-width:850px}.content-form-grid label{display:flex;flex-direction:column;gap:8px;font-weight:500}.content-form-grid b{color:#bd4444}.content-form-grid small,.content-mapping small{color:#80928b;font-weight:400}.content-wide{grid-column:1/-1}.content-footer{display:flex;justify-content:flex-end;gap:12px;border-top:1px solid #edf1ef;margin-top:28px;padding-top:20px}.content-divider{border-top:1px solid #edf1ef;margin:28px 0}.content-summary{display:flex;justify-content:space-between;gap:16px;background:#f0f8f5;padding:16px 20px;border-radius:8px;margin:20px 0;color:#22765d}.content-warning{display:block;color:#a86528;max-width:220px;margin-top:6px}.rule-table input{width:70px}.rule-table select{min-width:90px;width:100%}.rule-table td:first-child{min-width:160px}.rule-table td:nth-child(2){min-width:170px}.content-success{color:#18785d;background:#eef8f2;padding:12px;border-radius:6px}.content-error{color:#b13939;background:#fff1ef;padding:12px}.content-mapping{display:grid;gap:12px}.content-mapping label{display:flex;align-items:center;gap:14px;border:1px solid #e0e8e4;padding:16px;border-radius:8px;cursor:pointer}.content-mapping small{display:block;margin-top:5px}.content-overlay{position:fixed;inset:0;background:#152b2355;z-index:60;display:grid;place-items:center}.content-overlay .card{max-width:480px;margin:20px}.content-overlay .toolbar-actions{display:flex;gap:12px;justify-content:flex-end}.tag-list{display:flex;align-items:center;gap:7px;flex-wrap:wrap}.content-tag{font-size:12px;border-radius:5px;background:#edf6f1;color:#36775f;padding:3px 9px}.admin-shell button.content-tag{min-height:28px;padding:3px 9px;background:#edf6f1;color:#36775f}.tag-input{display:flex;gap:10px;align-items:end;margin:16px 0}.tag-input label{display:flex;flex-direction:column;gap:6px}.tag-suggestions{font-size:12px}.content-rule-head{margin-top:24px}@media(max-width:900px){.content-form-grid{grid-template-columns:1fr}.content-summary{flex-wrap:wrap}}
</style>
