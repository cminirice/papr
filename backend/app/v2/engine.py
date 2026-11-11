"""Finite candidate sets, deterministic whole-paper allocation and independent checks."""
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
from random import Random
from uuid import uuid5, NAMESPACE_URL
import json
from app.generators import multiplication as mul
from app.generators import grade4
from app.schemas.content import MultiplicationParams, MultiplicationProfile

KINDS={'竖式计算':'answer','解答题':'answer','填空题':'fill','选择题':'choice','判断题':'judgment','应用题':'application'}
LEVELS={'基础':'basic','提高':'standard','挑战':'challenge'}
CAPABILITIES={
 'integer_multiplication_v1':{'竖式计算':['基础','提高'],'选择题':['基础','提高','挑战'],'填空题':['基础','提高','挑战'],'解答题':['挑战']},
 'zero_multiplication_v1':{'竖式计算':['提高']},
 'number_read_write_v1':{'填空题':['基础','提高'],'选择题':['基础','提高']},
}
CAPABILITIES.update({m['id']:{c['kind']:c['difficulties'] for c in m['capabilities']} for m in grade4.manifest()})
NAMES={'integer_multiplication_v1':'整数乘法','zero_multiplication_v1':'含零因数乘法','number_read_write_v1':'大数读写'}

NAMES.update({m['id']:m['name'] for m in grade4.manifest()})

def canonical(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def digest(value):return sha256(canonical(value).encode()).hexdigest()
def fingerprint():return sha256(Path(__file__).read_bytes()+Path(grade4.__file__).read_bytes()+Path(mul.__file__).read_bytes()+Path(__import__('app.schemas.content',fromlist=['x']).__file__).read_bytes()).hexdigest()
def components():return [{'id':key,'name':NAMES[key],'version':'2.0.0','description':NAMES[key]+'，经代码生成及校验。','capabilities':[{'kind':k,'difficulties':ds,'sample':''} for k,ds in caps.items()]} for key,caps in CAPABILITIES.items() if not key.startswith(grade4.PREFIX)]+grade4.manifest()

def profile(rule,columns):
 basic=rule['difficulty']=='基础';challenge=rule['difficulty']=='挑战'
 task='zero_product' if rule['generator']=='zero_multiplication_v1' else ('missing_digit' if rule['kind']=='填空题' else 'error_choice' if rule['kind']=='选择题' else 'correction') if challenge else 'product'
 return MultiplicationProfile(task=task,difficulty=LEVELS[rule['difficulty']],a_min=100,a_max=299 if basic else 999,b_min=11,b_max=19 if basic else 99,allow_zero=not basic,max_carry_events=2 if basic else 9,layout={'questions_per_row':columns,'solutions_per_row':columns,'answer_space_mm':35})

@lru_cache(maxsize=16)
def candidates(component,difficulty,kind):
 if component.startswith(grade4.PREFIX):return grade4.candidates(component,difficulty)
 if component=='number_read_write_v1':
  # Finite, reproducible spaces with different zero placements and number levels.
  bases=(305006,420080,607020) if difficulty=='基础' else (30050006,120040080,40500600)
  return tuple(sorted({base+i*1001 for base in bases for i in range(3000)}))
 p=profile({'generator':component,'difficulty':difficulty,'kind':kind},2)
 return tuple((a,b) for a in range(p.a_min,p.a_max+1) for b in range(p.b_min,p.b_max+1) if mul.accepts(p,MultiplicationParams(a=a,b=b)))

def signature(rule,value):
 if rule['generator'].startswith(grade4.PREFIX):return grade4.signature(rule['generator'],value,rule['difficulty'])
 # Shared math signature across components and rules, stricter than question-type uniqueness.
 return ('read:'+str(value)) if rule['generator']=='number_read_write_v1' else f'mul:{value[0]}:{value[1]}'

def columns_for(content,rule):
 return (content.get('columns_by_kind') or {}).get(rule['kind'],content['columns'])

def validate_config(content):
 rules=content['rules']
 if not 1<=len(rules)<=30 or not 1<=content['columns']<=5 or not 1<=sum(r['count'] for r in rules)<=200:raise ValueError('整卷须1–200题，最多30条规则，每行1–5题')
 layout=content.get('columns_by_kind') or {}
 if any(k not in KINDS or type(v) is not int or not 1<=v<=5 for k,v in layout.items()):raise ValueError('每种题型每行题数须为1–5的整数')
 seen=set();prior=0;capacity=[]
 for r in rules:
  if r['difficulty'] not in CAPABILITIES.get(r['generator'],{}).get(r['kind'],[]):raise ValueError('组件不支持所选题型或难度')
  key=(r['node'],r['generator'],r['kind'],r['difficulty'])
  if key in seen:raise ValueError('相同出题规则请合并题数')
  seen.add(key)
  if type(r['count']) is not int or not 1<=r['count']<=100:raise ValueError('单条规则题数须1–100')
  # At most prior questions can overlap this finite candidate set, so this is a
  # conservative proof that sequential generation cannot exhaust its capacity.
  available=len(candidates(r['generator'],r['difficulty'],r['kind']))
  if available-prior<r['count']:raise ValueError('跨规则可用题量不足，请调整题数或规则')
  capacity.append({'capacity':available,'guaranteed_remaining':available-prior,'requested':r['count']});prior+=r['count']
 return capacity

def read_number(value):
 digits='零一二三四五六七八九'
 def group(n):
  result='';zero=False
  for p in range(3,-1,-1):
   d=n//10**p%10
   if d:result+=('零' if zero else '')+digits[d]+('','十','百','千')[p];zero=False
   elif result:zero=True
  return result
 result='';zero=False
 for i in range(2,-1,-1):
  n=value//10000**i%10000
  if n:result+=('零' if result and (zero or n<1000) else '')+group(n)+('','万','亿')[i];zero=False
  elif result:zero=True
 return result[1:] if result.startswith('一十') else result or '零'

def reading_question(rule,value,seed,position,columns):
 reading=read_number(value);choice=rule['kind']=='选择题';rng=Random(seed)
 values=[str(value),str(value+10),str(value+100),str(value+1000)];rng.shuffle(values)
 options=[{'id':str(uuid5(NAMESPACE_URL,seed+v)),'value':v} for v in values] if choice else []
 answer={'kind':'single_choice','value':str(value),'correct_option_id':next(o['id'] for o in options if o['value']==str(value))} if choice else {'kind':'text','value':reading}
 return {'schema_version':1,'id':str(uuid5(NAMESPACE_URL,seed)),'position':position,'question_type':'choice' if choice else 'fill','render_mode':'direct','difficulty':LEVELS[rule['difficulty']],
  'stem_blocks':[{'type':'text','text':f'“{reading}”写作（　）。' if choice else f'{value} 读作：________________。'}],
  'options':options,'answer':answer,'explanation_steps':[{'blocks':[{'type':'text','text':f'按四位一级读数，级末的零不读，连续的零只读一个零。{value}读作{reading}。'}]}],
  'layout':{'questions_per_row':columns,'solutions_per_row':columns,'answer_space_mm':20,'keep_together':True,'diagram_size_mm':None},
  'render_spec':{'kind':'number_read_write','number':value,'reading':reading}}

def generate(content,seed):
 validate_config(content);seen=set();questions=[]
 for ri,rule in enumerate(content['rules']):
  values=list(candidates(rule['generator'],rule['difficulty'],rule['kind']));Random(seed+str(ri)).shuffle(values);taken=0
  for value in values:
   sig=signature(rule,value)
   if sig in seen:continue
   pos=len(questions)+1;qseed=f'{seed}:{ri}:{pos}'
   if rule['generator'].startswith(grade4.PREFIX):q=grade4.question(rule,value,qseed,pos,columns_for(content,rule))
   elif rule['generator']=='number_read_write_v1':q=reading_question(rule,value,qseed,pos,columns_for(content,rule))
   else:
    p=profile(rule,columns_for(content,rule));model=mul.build_question(p,MultiplicationParams(a=value[0],b=value[1]),seed=qseed,position=1,question_type=KINDS[rule['kind']]);mul.verify_question(model,p)
    q=model.model_dump(mode='json');q['position']=pos
   q['rule_index']=ri;q['semantic_signature']=sig;q['leaf_name']=rule['point'];questions.append(q);seen.add(sig);taken+=1
   if taken==rule['count']:break
  if taken!=rule['count']:raise ValueError('CAPACITY_INSUFFICIENT')
 return questions

def verify(content,questions):
 if len(questions)!=sum(r['count'] for r in content['rules']):raise ValueError('QUESTION_COUNT_MISMATCH')
 seen=set();counts=[0]*len(content['rules'])
 for pos,q in enumerate(questions,1):
  ri=q['rule_index'];r=content['rules'][ri];counts[ri]+=1
  if q['position']!=pos or q['question_type']!=KINDS[r['kind']] or q['difficulty']!=LEVELS[r['difficulty']]:raise ValueError('QUESTION_CONFIG_MISMATCH')
  if any(q['layout'][key]!=columns_for(content,r) for key in ('questions_per_row','solutions_per_row')):raise ValueError('LAYOUT_CONFIG_MISMATCH')
  if r['generator'].startswith(grade4.PREFIX):
   sig=grade4.verify(r,q,columns_for(content,r))
  elif r['generator']=='number_read_write_v1':
   n=q['render_spec']['number'];reading=read_number(n)
   if n not in candidates(r['generator'],r['difficulty'],r['kind']) or q['render_spec']['reading']!=reading:raise ValueError('READING_INVALID')
   if q['answer']['value']!=(str(n) if r['kind']=='选择题' else reading):raise ValueError('ANSWER_INVALID')
   if r['kind']=='选择题' and (len({o['value'] for o in q['options']})!=4 or sum(o['id']==q['answer']['correct_option_id'] and o['value']==str(n) for o in q['options'])!=1):raise ValueError('OPTIONS_INVALID')
   sig=signature(r,n)
  else:
   from app.schemas.content import MultiplicationQuestion
   data={k:v for k,v in q.items() if k not in ('rule_index','semantic_signature','leaf_name')};data['position']=1
   mul.verify_question(MultiplicationQuestion.model_validate(data),profile(r,columns_for(content,r)))
   sig=signature(r,(int(q['render_spec']['multiplicand']),int(q['render_spec']['multiplier'])))
  if sig!=q['semantic_signature'] or sig in seen:raise ValueError('QUESTION_DUPLICATE')
  seen.add(sig)
 if counts!=[r['count'] for r in content['rules']]:raise ValueError('RULE_COUNT_MISMATCH')
