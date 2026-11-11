import {requestData} from '@papr/shared/api'
export type Rule={point:string;kind:string;difficulty:string;count:number}
export type Template={id:string;version_id:string;configuration_hash:string;name:string;description:string;columns:number;columns_by_kind?:Record<string,number>|null;status:string;available:boolean;reason:string;rules:Rule[];tags:string[]}
export type RecordItem={id:string;name:string;created:string;status:string;phase:string;error?:string;rules:Rule[];templateId:string;columns:number;columns_by_kind?:Record<string,number>|null;tags:string[];notices:string[];withdrawn:boolean;assets:{id:string;kind:string;pages:number}[]}
let csrf=''
export async function session(){const data=await requestData<{csrf_token:string;next_generation_at:string|null}>('/api/v1/session',{body:{}});csrf=data.csrf_token;return data}
export function templates(){return requestData<Template[]>('/api/v2/templates')}
export function history(){return requestData<RecordItem[]>('/api/v2/history')}
export async function generate(t:Template,key:string){if(!csrf)await session();return requestData<RecordItem>('/api/v2/jobs',{body:{version_id:t.version_id,configuration_hash:t.configuration_hash},csrf,idempotencyKey:key})}
export async function cancel(id:string){return requestData<RecordItem>(`/api/v2/jobs/${id}/cancel`,{body:{},csrf})}
export const statusLabel=(s:string)=>({queued:'排队中',running:'生成中',succeeded:'已完成',failed:'失败',cancelled:'已取消'}[s]??s)
export function sessionState(){return requestData<{next_generation_at:string|null}>('/api/v1/session')}
