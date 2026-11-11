from copy import deepcopy
import re
import pytest
from app.generators import grade4
from app.v2 import engine

MANIFEST=grade4.manifest()

@pytest.mark.parametrize('component',MANIFEST,ids=lambda m:m['id'])
def test_all_modes_levels_exact_counts_and_tamper(component):
 for capability in component['capabilities']:
  for level in capability['difficulties']:
   rule={'node':'leaf','point':component['name'],'generator':component['id'],'kind':capability['kind'],'difficulty':level,'count':12}
   content={'columns':1,'rules':[rule]}
   q=engine.generate(content,'coverage')
   engine.verify(content,q)
   assert len(q)==12 and len({x['semantic_signature'] for x in q})==12
   assert q==engine.generate(content,'coverage')
   assert all(x['question_type']==grade4.KIND_MAP[capability['kind']] for x in q)
   if capability['kind']=='选择题':assert all(len({o['value'] for o in x['options']})==4 for x in q)
   if capability['kind']=='判断题':assert {x['answer']['value'] for x in q}=={'正确','错误'}
   bad=deepcopy(q);bad[0]['answer']['value']='被篡改的答案'
   with pytest.raises(ValueError):engine.verify(content,bad)
   bad=deepcopy(q);bad[0]['stem_blocks'][0]['text']='被篡改的条件'
   with pytest.raises(ValueError):engine.verify(content,bad)

@pytest.mark.parametrize('key',grade4.TOPICS)
def test_candidate_capacity_measures_unique_prompts(key):
 component=grade4.PREFIX+key+'_v1'
 for level in grade4.LEVELS:
  values=grade4.candidates(component,level)
  assert len(values)>=100
  signatures=[grade4.signature(component,i,level) for i in values]
  assert len(signatures)==len(set(signatures))


def test_independent_arithmetic_oracles():
 # Compute from the visible conditions rather than the component's explanation.
 for level in grade4.LEVELS:
  for i in range(60):
   def item(topic):return grade4.problem(grade4.PREFIX+topic+'_v1',i,level)
   def nums(p):return list(map(int,re.findall(r'\d+',p.stem)))
   q=item('count_shapes');a=nums(q)
   expected=(a[0]*(a[0]-1)//2 if i%3!=1 else sum(range(1,a[0]+1))*sum(range(1,a[1]+1)))
   assert int(re.search(r'\d+',q.answer)[0])==expected
   q=item('multiplication');a=nums(q)
   assert int(re.search(r'\d+',q.answer)[0])==a[0]*a[1]
   q=item('quantities');a=nums(q)
   expected=(a[2]-a[0]*a[1] if i%3==0 else a[0]*a[1] if i%3==1 else (a[0]+a[1]-1)//a[1])
   assert int(re.search(r'\d+',q.answer)[0])==expected
   q=item('shape_patterns');a=nums(q)
   expected=3*a[0]+1 if i%3==0 else 2*(a[0]+a[1]) if i%3==1 else a[0]*a[1]
   assert int(re.search(r'\d+',q.answer)[0])==expected
   q=item('statistics');a=nums(q)
   expected=sum(a) if i%3==0 else max(a)-min(a) if i%3==1 else a[0]-sum(a[1:])
   assert int(re.search(r'\d+',q.answer)[0])==expected
   q=item('navigation');a=nums(q)
   if i%3==0:assert q.answer==str(a[0]//a[1]*60)+'分钟'
   elif i%3==1:assert q.answer==str(a[0]+a[1])+'分钟'
   else:
    end=a[0]*60+a[1]+a[2]*60+a[3]
    assert q.answer==f'{end//60:02d}:{end%60:02d}'


def test_all_topics_mixed_paper_and_cross_kind_dedup():
 rules=[{'node':k,'point':v[0],'generator':grade4.PREFIX+k+'_v1','kind':'填空题','difficulty':'基础','count':3} for k,v in grade4.TOPICS.items()]
 content={'columns':1,'rules':rules}
 q=engine.generate(content,'all-topics');engine.verify(content,q);assert len(q)==33
 # Distinct responses to the same underlying problem must not repeat within one paper.
 rule=rules[0]
 content['rules']=[{**rule,'kind':k,'count':20} for k in ('选择题','填空题','判断题')]
 q=engine.generate(content,'mixed');engine.verify(content,q)
 assert len({x['semantic_signature'] for x in q})==60


def test_number_angle_encoding_space_and_law_oracles():
 places={'千':1000,'万':10000,'十万':100000,'百万':1000000,'千万':10000000}
 for level in grade4.LEVELS:
  for i in range(90):
   def item(t):return grade4.problem(grade4.PREFIX+t+'_v1',i,level)
   def nums(q):return list(map(int,re.findall(r'\d+',q.stem)))
   q=item('large_numbers');a=nums(q)
   if i%3==0:
    unit=re.search(r'的(.+?)位',q.stem)[1];expected=str(a[0]//places[unit]%10)
   elif i%3==1:expected='＞' if a[0]>a[1] else '＜'
   else:
    whole,remainder=divmod(a[0],10000);expected=str(whole+(remainder>=5000))+'万'
   assert q.answer==expected
   q=item('angles');angle=nums(q)[0]
   expected=('锐角' if angle<90 else '直角' if angle==90 else '钝角') if i%3==0 else str((180 if i%3==1 else 360)-angle)+'°'
   assert q.answer==expected
   q=item('encoding')
   if i%3==0:
    a,b,c=map(int,re.search(r'(\d+)年级(\d+)班(\d+)号',q.stem).groups());expected=f'{a}{b:02}{c:02}'
   elif i%3==1:expected=str(int(re.search(r'编码(\d+)',q.stem)[1][2:4]))+'层'
   else:expected=str(int(re.search(r'排到(\d+)',q.stem)[1]))+'个'
   assert q.answer==expected
   q=item('space');a=nums(q)
   expected=f'（{a[0]+a[2]}，{a[1]+a[3]}）' if i%3==0 else str(a[0]*(a[1]+a[2]))+'米' if i%3==1 else str(sum(a))+'格'
   assert q.answer==expected
   q=item('laws');a=nums(q)
   expected=str(sum(a))+'本' if i%3==0 else str(a[0]*a[1]*a[2])+'个' if i%3==1 else str((a[0]+a[1])*a[2])+'元'
   assert q.answer==expected
