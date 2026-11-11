import { reactive } from 'vue'
import { requestData } from '@papr/shared/api'
export type Entity='catalogs'|'nodes'|'templates'
export type Rule={node:string;generator:string;kind:string;difficulty:string;count:number}
export type WorkflowJob={id:string;status:string;phase:string;error?:string;assets:{id:string;kind:string;pages:number}[]}
export type Item={id:string;code:string;name:string;status:string;description:string;term:string;catalog:string;parent:string;type:string;sort:number;generators:string[];rules:Rule[];columns:number;columns_by_kind?:Record<string,number>;grade:string;tags:string[];primaryCategory:string;secondaryCategory:string;revision:number;version_id?:string;configuration_hash?:string;sealed?:boolean;published_version_id?:string;review_id?:string;review_comment?:string;preview_job?:WorkflowJob;validation_job?:WorkflowJob}
export const blank=():Item=>({id:'',code:'',name:'',status:'草稿',description:'',term:'',catalog:'',parent:'',type:'主题',sort:0,generators:[],rules:[],columns:2,columns_by_kind:{'竖式计算':2,'选择题':1,'填空题':1,'解答题':1,'判断题':1,'应用题':1},grade:'',tags:[],primaryCategory:'',secondaryCategory:'',revision:0})
export const demo=reactive<Record<Entity,Item[]>>({catalogs:[],nodes:[],templates:[]})
export const componentStates=reactive<Record<string,{enabled:boolean;revision:number}>>({})
export type Generator={id:string;name:string;version:string;description:string;capabilities:{kind:string;difficulties:string[];sample:string}[]}
export const componentCatalog=reactive<Generator[]>([])
export const registryState=reactive<Record<string,boolean>>({})
type Workspace=Record<Entity,Item[]>&{components:Generator[];component_states:Record<string,{enabled:boolean;revision:number}>}
function apply(data:Workspace){componentCatalog.splice(0,componentCatalog.length,...data.components);for(const k of ['catalogs','nodes','templates'] as Entity[])demo[k]=data[k].map(x=>({...blank(),...x,columns_by_kind:{...Object.fromEntries(['竖式计算','选择题','填空题','解答题'].map(k=>[k,x.columns??2])),'判断题':1,'应用题':1,...x.columns_by_kind}}));Object.assign(componentStates,data.component_states);for(const [key,s] of Object.entries(data.component_states))registryState[key]=s.enabled}
export async function refreshWorkspace(){apply(await requestData<Workspace>('/admin/api/v2/workspace'))}
async function csrf(){return (await requestData<{csrf_token:string}>('/admin/api/v1/session/csrf',{body:{}})).csrf_token}
export async function command<T>(path:string,body:object,method:'POST'|'PUT'|'PATCH'='POST',idempotencyKey?:string){return requestData<T>('/admin/api/v2'+path,{body,method,csrf:await csrf(),idempotencyKey})}
export async function persistItem(entity:Entity,item:Item){
 const {revision,code,name,description,status,catalog,sort,generators,rules,columns,columns_by_kind,tags}=item
 const id=item.id||crypto.randomUUID()
 const data=await command<Workspace>(`/items/${entity}/${id}`,{revision,code,name,description,status,catalog,sort,generators,rules:rules.map(({node,generator,kind,difficulty,count})=>({node,generator,kind,difficulty,count})),columns,columns_by_kind,tags},'PUT')
 apply(data);return demo[entity].find(x=>x.id===id)!
}
export async function disableTemplate(item:Item){apply(await command<Workspace>(`/templates/${item.id}/disable`,{revision:item.revision}))}
export async function publishTemplate(item:Item){apply(await command<Workspace>(`/templates/${item.id}/publish`,{revision:item.revision,version_id:item.version_id,review_id:item.review_id}))}
export async function toggleComponent(key:string){const state=componentStates[key];apply(await command<Workspace>(`/components/${key}`,{enabled:!state?.enabled,revision:state?.revision??0},'PATCH'))}
// Legacy callers must not silently persist browser-only content.
export function persist(){throw new Error('请通过服务端保存当前记录')}
export function hasLocalConfiguration(){return !!localStorage.getItem('papr-content-prototype-v2')}
export async function importLocalConfiguration(){
 const old=JSON.parse(localStorage.getItem('papr-content-prototype-v2')??'null')
 if(!old)throw new Error('没有可导入的旧配置')
 const payload=Object.fromEntries((['catalogs','nodes','templates'] as Entity[]).map(k=>[k,old[k].map((x:Item)=>({old_id:x.id,item:{revision:0,code:x.code,name:x.name,description:x.description??'',status:x.status,catalog:x.catalog??'',sort:x.sort??0,generators:x.generators??[],rules:(x.rules??[]).map(({node,generator,kind,difficulty,count})=>({node,generator,kind,difficulty,count})),columns:x.columns??2,tags:x.tags??[]}}))]))
 apply(await command<Workspace>('/workspace/import',payload))
}
