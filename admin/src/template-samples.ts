import type { MultiplicationQuestion } from '@papr/shared/contracts'
import type { Rule } from './content-demo'
export type ReadingSample = { stem: string; options: string[]; answer: string; explanation: string }
// 高保真样例库，仅供前端交互查看；不产生后端验证报告或发布证据。
export function readingSample(rule:Rule, round:number):ReadingSample {
 const seeds=rule.difficulty==='基础'?[305006,420080,607020]:[30050006,120040080,40500600]
 const number=String(seeds[round%3]!+Math.floor(round/3)*1001)
 const reading=readNumber(Number(number))
 const explanation=`按四位一级分级读数，级末的零不读，连续的零只读一个零。${number}读作${reading}。`
 const options=rule.kind==='选择题'?[number!,String(Number(number)+10),String(Number(number)+100),String(Number(number)+1000)]:[]
 return {stem:rule.kind==='选择题'?`“${reading}”写作（　）。`:`${number} 读作：________________。`,options,answer:rule.kind==='选择题'?`A，${number}`:reading!,explanation:explanation!}
}
export function multiplicationSample(rule:Rule,round:number,position:number):MultiplicationQuestion {
 const pool=rule.generator==='zero_multiplication_v1'?[[205,30],[304,20],[406,50]]:rule.difficulty==='基础'?[[123,12],[112,13],[211,12]]:[[452,83],[177,24],[389,46]]
 const [base,b]=pool[round%pool.length]! as [number,number]
 const a=base+Math.floor(round/pool.length)
 const ones=a*(b%10), tens=a*Math.floor(b/10)*10, product=a*b
 const missing=rule.difficulty==='挑战'&&rule.kind==='填空题'
 const error=rule.difficulty==='挑战'&&(rule.kind==='选择题'||rule.kind==='解答题')
 const choice=rule.kind==='选择题'
 const answer=missing?String(a)[1]!:String(product)
 return {
  schema_version:1,id:`sample-${round}-${position}`,position,
  question_type:choice?'choice':rule.kind==='填空题'?'fill':'answer',
  render_mode:missing||error||rule.kind==='竖式计算'?'vertical':'direct',
  difficulty:rule.difficulty==='基础'?'basic':rule.difficulty==='提高'?'standard':'challenge',
  primary_knowledge_code:rule.generator==='zero_multiplication_v1'?'O003':'O002',stem_blocks:[],
  options:choice?(error?['十位部分积没有按十位对齐','个位乘法算错了','乘数看错了','两个部分积相加算错了']:[String(product),String(product+10),String(product-10),String(product+100)]).map((value,i)=>({id:String(i),value})):[],
  answer:choice?{kind:'single_choice',value:error?'十位部分积没有按十位对齐':answer,correct_option_id:'0'}:{kind:'numeric',value:answer,unit:null,precision_requirement:'exact_integer'},
  explanation_steps:[{blocks:[{type:'text',text:missing?`缺失的十位数字是${answer}。`:error?'十位部分积应向左错一位。':''}]},{blocks:[{type:'text',text:`${a} × ${b%10} = ${ones}；${a} × ${Math.floor(b/10)*10} = ${tens}；${ones} + ${tens} = ${product}。`}]}],
  layout:{answer_space_mm:35,keep_together:true,diagram_size_mm:null},
  render_spec:{kind:'integer_multiplication',multiplicand:String(a),multiplier:String(b),ones_partial:String(ones),tens_partial:String(tens),tens_shift:1,result:String(product),...(missing?{missing_digit_index:1}:{}),...(error?{incorrect_tens_partial:String(tens/10),incorrect_result:String(ones+tens/10)}:{})},
 }
}

function readNumber(value:number):string {
 const digits='零一二三四五六七八九'
 function group(n:number):string {
  let result='',zero=false
  for(let p=3;p>=0;p--){
   const d=Math.floor(n/10**p)%10
   if(d){if(zero)result+='零';result+=digits[d]+['','十','百','千'][p]!;zero=false}
   else if(result)zero=true
  }
  return result
 }
 let result='',zero=false
 for(let i=2;i>=0;i--){
  const n=Math.floor(value/10000**i)%10000
  if(n){if(result&&(zero||n<1000))result+='零';result+=group(n)+['','万','亿'][i]!;zero=false}
  else if(result)zero=true
 }
 return (result||'零').replace(/^一十/,'十')
}
