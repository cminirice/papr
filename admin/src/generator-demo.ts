import { demo, registryState, componentCatalog, type Rule, type Item } from './content-demo'
export const generators=componentCatalog
export const registry=registryState
export function compatible(nodeId:string){const node=demo.nodes.find(n=>n.id===nodeId);return generators.filter(g=>node?.generators.includes(g.id)&&registry[g.id])}
export function kinds(node:string,generator:string){return compatible(node).find(g=>g.id===generator)?.capabilities.map(c=>c.kind)??[]}
export function difficulties(rule:Rule){return compatible(rule.node).find(g=>g.id===rule.generator)?.capabilities.find(c=>c.kind===rule.kind)?.difficulties??[]}
export function ruleIssue(rule:Rule){if(!demo.nodes.some(n=>n.id===rule.node))return '请选择二级目录';if(!compatible(rule.node).length)return '二级目录尚未关联可用组件';if(!kinds(rule.node,rule.generator).includes(rule.kind)||!difficulties(rule).includes(rule.difficulty))return '请选择可用的组件、题型和难度';if(!Number.isInteger(rule.count)||rule.count<1||rule.count>100)return '题数应为1–100的整数';return ''}
export function templateIssue(t:Item){if(!demo.catalogs.some(c=>c.id===t.catalog))return '请选择一级目录';if(!t.rules.length)return '请添加出题规则';for(const r of t.rules){if(demo.nodes.find(n=>n.id===r.node)?.catalog!==t.catalog)return '二级目录不属于所选目录';const issue=ruleIssue(r);if(issue)return issue}return ''}
export function selectComponent(rule:Rule){rule.generator=compatible(rule.node)[0]?.id??'';selectKind(rule)}
export function selectKind(rule:Rule){const allowed=kinds(rule.node,rule.generator);if(!allowed.includes(rule.kind))rule.kind=allowed[0]??'';selectDifficulty(rule)}
export function selectDifficulty(rule:Rule){const allowed=difficulties(rule);if(!allowed.includes(rule.difficulty))rule.difficulty=allowed[0]??''}
