"""Parameterized grade-four activities. No free-form scripts or generated answer guessing."""
from dataclasses import dataclass
from functools import lru_cache
from hashlib import sha256
from random import Random
from uuid import uuid5,NAMESPACE_URL
import json

TOPICS={
 'large_numbers':('认识更大的数','数位、大小比较、四舍五入到万位。'),
 'encoding':('编码','按明确规则编写班级、图书、货架编码；不使用真实身份信息。'),
 'angles':('线与角','角的分类、平角与周角中的角度计算；图示标注已知角度。'),
 'multiplication':('整数乘法与巧算','两位数凑整、乘25、三位数乘两位数及装箱情境。'),
 'space':('位置与方向','方格位置、方向移动与最短路线；范围为位置方向基础。'),
 'laws':('运算律与简便计算','加法结合、乘法结合、乘法分配及逆用。'),
 'count_shapes':('数图形的学问','线段、长方形网格及共顶点三角形计数。'),
 'shape_patterns':('图形规律与周长','拼摆正方形、长方形周长和网格面积；范围为图形规律基础。'),
 'quantities':('数量关系与应用','单价数量总价、速度时间路程、分组与剩余量。'),
 'statistics':('数据的表示和分析','读表、条形图、求总数、比较差值与补全数据。'),
 'navigation':('导航与行程时间','整时行程、途中停留、到达时刻和预计/实际时间比较。'),
}
PREFIX='g4_upper_'
LEVELS={'基础':0,'提高':1,'挑战':2}
KIND_MAP={'选择题':'choice','填空题':'fill','判断题':'judgment','解答题':'answer','应用题':'application'}
APPLICATION={'multiplication','space','laws','shape_patterns','quantities','statistics','navigation'}

def manifest():
 return [{'id':PREFIX+k+'_v1','name':name,'version':'1.0.0','description':desc,
 'capabilities':[{'kind':kind,'difficulties':list(LEVELS),'sample':problem(PREFIX+k+'_v1',0,'基础').stem} for kind in KIND_MAP if kind!='应用题' or k in APPLICATION]} for k,(name,desc) in TOPICS.items()]

def topic(key):return key.removeprefix(PREFIX).removesuffix('_v1')
def digest(data):return sha256(json.dumps(data,ensure_ascii=False,sort_keys=True).encode()).hexdigest()

@dataclass
class Problem:
 stem:str
 answer:str
 explanation:str
 wrong:list[str]
 diagram:dict|None=None


def number_options(n,unit='',step=1):
 return [f'{n+step}{unit}',f'{max(0,n-step)}{unit}',f'{n+2*step}{unit}',f'{n+3*step}{unit}']

def p(stem,n,explanation,unit='',step=1,diagram=None):
 return Problem(stem,f'{n}{unit}',explanation,number_options(n,unit,step),diagram)

def problem(key,index,level):
 """Every exercise states all conventions, including grid and code interpretation."""
 t=topic(key);d=LEVELS[level];rng=Random(f'{key}:{index}:{level}')
 variant=index%3;a=rng.randint(12+10*d,48+40*d);b=rng.randint(3+d,12+6*d)
 if t=='large_numbers':
  n=rng.randint(100000 if d==0 else 10000000,999999 if d==0 else 999999999)
  if variant==0:
   exp=rng.choice([3,4,5] if d==0 else [4,5,6,7]);unit={3:'千',4:'万',5:'十万',6:'百万',7:'千万'}[exp];digit=n//10**exp%10
   return p(f'{n}的{unit}位上的数字是多少？',digit,f'从个位起向左数，第{exp+1}位是{unit}位，这一位的数字是{digit}。')
  if variant==1:
   other=n+rng.choice([-1,1])*rng.randint(1,9999);ans='＞' if n>other else '＜'
   return Problem(f'在{n} ○ {other}中的○里填什么符号？',ans,f'先比较位数，位数相同再从高位依次比较，所以{n}{ans}{other}。',['＜' if ans=='＞' else '＞','＝','无法比较'])
  rounded=(n+5000)//10000
  return p(f'把{n}四舍五入到万位，用“万”作单位表示。',rounded,f'观察千位，按四舍五入取整：{n}≈{rounded}万。','万')
 if t=='encoding':
  # Deliberately synthetic, with explicit fixed-width fields.
  x=rng.randint(1,6);y=rng.randint(1,25);z=rng.randint(1,99)
  if variant==0:
   ans=f'{x}{y:02d}{z:02d}'
   return Problem(f'学校编码规则：年级占1位、班号占2位、序号占2位，不足位补0。{x}年级{y}班{z}号的编码是什么？',ans,f'三段依次为{x}、{y:02d}、{z:02d}，连接得到{ans}。',[f'{x}{z:02d}{y:02d}',f'{x}{y:02d}{(z%99+1):02d}',f'{x}{(y%25+1):02d}{z:02d}',f'{x}{y:02d}00'])
  if variant==1:
   code=f'{x:02d}{y:02d}{z:03d}'
   return p(f'图书编码{code}：前2位为书架号，接着2位为层号，最后3位为序号。这本书在第几层？',y,f'从左往右分段为{x:02d}｜{y:02d}｜{z:03d}，层号是{y}。','层')
  return p(f'某仓库用两位货架号、两位层号、三位序号组成编码。货架号为{x}、层号为{y}，每层序号从001排到{z:03d}，这一层有多少个不同编码？',z,f'货架号和层号固定，序号从1到{z}，共有{z}个编码。','个')
 if t=='angles':
  angle=rng.randint(10,170)
  if variant==0:
   ans='锐角' if angle<90 else '直角' if angle==90 else '钝角'
   return Problem(f'一个角是{angle}°，按大小分类，它是什么角？',ans,f'小于90°是锐角，等于90°是直角，大于90°且小于180°是钝角，所以是{ans}。',[x for x in ['锐角','直角','钝角','平角'] if x!=ans],{'kind':'angle','angle':angle})
  total=180 if variant==1 else 360
  return p(f'一个{ "平角" if total==180 else "周角"}被分成两个角，已知其中一个是{angle}°，另一个是多少度？',total-angle,f'{total}－{angle}＝{total-angle}，另一个角是{total-angle}°。','°',diagram={'kind':'angle','angle':angle})
 if t=='multiplication':
  if variant==0:
   x=rng.randint(12,49);y=rng.choice([19,29,39,49,59,69,79,89,99]);n=x*y
   return p(f'商店购进{y}盒彩笔，每盒{x}支。用凑整的方法求一共有多少支彩笔。',n,f'{x}×{y}＝{x}×（{y+1}－1）＝{x*(y+1)}－{x}＝{n}。','支')
  if variant==1:
   x=4*rng.randint(3,24);n=x*25
   return p(f'每套材料25元，买{x}套。用简便方法求总价。',n,f'{x}×25＝（{x}÷4）×（25×4）＝{x//4}×100＝{n}。','元',step=25)
  x=rng.randint(100,399+200*d);y=rng.randint(12,29+20*d)
  return p(f'每箱有{x}个零件，共{y}箱，一共有多少个零件？',x*y,f'{x}×{y}＝{x}×{y//10*10}＋{x}×{y%10}＝{x*(y//10*10)}＋{x*(y%10)}＝{x*y}。','个')
 if t=='space':
  x=rng.randint(1,9);y=rng.randint(1,9);dx=rng.randint(1,8);dy=rng.randint(1,8)
  diagram={'kind':'grid','x':x,'y':y,'dx':dx,'dy':dy}
  if variant==0:
   ans=f'（{x+dx}，{y+dy}）'
   return Problem(f'规定数对为（列，行），向右列号增大，向上行号增大。从（{x}，{y}）先向右走{dx}格，再向上走{dy}格，终点数对是多少？',ans,f'列号{x}＋{dx}＝{x+dx}，行号{y}＋{dy}＝{y+dy}，终点为{ans}。',[f'（{x+dy}，{y+dx}）',f'（{x+dx}，{y}）',f'（{x}，{y+dy}）',f'（{x+dx+1}，{y+dy}）'],diagram)
  scale=10*(d+1)
  if variant==1:return p(f'方格路线中每格长{scale}米，从A出发向东走{dx}格，再向北走{dy}格到B。共走多少米？',scale*(dx+dy),f'（{dx}＋{dy}）×{scale}＝{scale*(dx+dy)}米。','米',diagram=diagram)
  return p(f'在只能沿水平、竖直格线走的方格地图中，两点向东相差{dx}格、向北相差{dy}格。不走回头路，最短要走多少格？',dx+dy,f'横向至少走{dx}格，纵向至少走{dy}格，最短共{dx}＋{dy}＝{dx+dy}格。','格',diagram=diagram)
 if t=='laws':
  if variant==0:
   x=rng.randint(11,89);y=rng.randint(10,99);z=100-x
   return p(f'三批图书分别有{x}本、{y}本、{z}本。怎样凑整求总数？写出总数。',100+y,f'（{x}＋{z}）＋{y}＝100＋{y}＝{100+y}，使用加法交换律和结合律。','本')
  if variant==1:
   x=rng.randint(3,40);n=x*125*8
   return p(f'每盒8个球，每箱125盒，{x}箱共有多少个球？用简便方法计算。',n,f'{x}×125×8＝{x}×（125×8）＝{x}×1000＝{n}，使用乘法结合律。','个',step=1000)
  x=rng.randint(12,89);y=rng.randint(2,8);z=10-y;n=x*10
  return p(f'上午售出{y}套练习册，下午售出{z}套，每套{x}元。用乘法分配律求全天收入。',n,f'{x}×{y}＋{x}×{z}＝{x}×（{y}＋{z}）＝{x}×10＝{n}。','元')
 if t=='count_shapes':
  if variant==0:
   n=3+index%18
   return p(f'一条直线上标出{n}个不同的点，每两个点确定一条线段，一共能数出多少条不同线段？',n*(n-1)//2,f'每个点可与其余{n-1}个点配对，每条线段被数2次，所以{n}×{n-1}÷2＝{n*(n-1)//2}。','条',diagram={'kind':'segments','n':n})
  if variant==1:
   rows=1+index//3%8;cols=2+index//24%12
   value=rows*(rows+1)*cols*(cols+1)//4
   return p(f'一个{rows}行{cols}列的方格图中，只沿格线取边，一共有多少个长方形（包括正方形）？',value,f'在{rows+1}条横线中选2条有{rows*(rows+1)//2}种，在{cols+1}条竖线中选2条有{cols*(cols+1)//2}种，共{rows*(rows+1)//2}×{cols*(cols+1)//2}＝{value}个。','个',diagram={'kind':'rect_grid','rows':rows,'cols':cols})
  n=3+index//3%28
  return p(f'从直线外一点P分别连接直线上{n}个不同的点，图中以P为顶点、底边在该直线上的三角形共有多少个？',n*(n-1)//2,f'在底边上任选2个点可确定一个三角形，共{n}×{n-1}÷2＝{n*(n-1)//2}个。','个',diagram={'kind':'fan','n':n})
 if t=='shape_patterns':
  if variant==0:
   n=rng.randint(3,40+30*d)
   return p(f'用同样长的小棒横着拼一排{n}个小正方形，相邻正方形共用一条边，至少需要多少根小棒？',3*n+1,f'第1个用4根，每增加1个用3根，共4＋3×（{n}－1）＝{3*n+1}根。','根',diagram={'kind':'squares','n':n})
  if variant==1:return p(f'长方形花坛长{a}米、宽{b}米，四周围一圈围栏，需要多少米围栏？',2*(a+b),f'长方形周长＝（长＋宽）×2＝（{a}＋{b}）×2＝{2*(a+b)}米。','米',diagram={'kind':'rectangle','a':a,'b':b})
  return p(f'一块长方形地面长{a}米、宽{b}米，每块地砖面积1平方米，铺满地面至少需要多少块（不考虑损耗）？',a*b,f'面积＝{a}×{b}＝{a*b}平方米，每块1平方米，需要{a*b}块。','块',diagram={'kind':'rectangle','a':a,'b':b})
 if t=='quantities':
  if variant==0:
   paid=a*b+10*rng.randint(1,10);n=paid-a*b
   return p(f'买{b}本书，每本{a}元，付出{paid}元，应找回多少元？',n,f'总价＝{a}×{b}＝{a*b}元；找回{paid}－{a*b}＝{n}元。','元')
  if variant==1:return p(f'一辆汽车以每小时{a}千米的速度匀速行驶{b}小时，一共行驶多少千米？',a*b,f'路程＝速度×时间＝{a}×{b}＝{a*b}千米。','千米')
  extra=rng.randint(1,b-1);n=a*b+extra
  return p(f'{n}名同学乘车，每辆车最多坐{b}名同学，至少需要多少辆车？',a+1,f'{n}÷{b}＝{a}……{extra}，余下{extra}人还需1辆车，所以至少{a+1}辆。','辆')
 if t=='statistics':
  vals=[rng.randint(10+10*d,50+30*d) for _ in range(4)];names=['甲组','乙组','丙组','丁组'];table='，'.join(f'{n}{v}本' for n,v in zip(names,vals));diagram={'kind':'bars','labels':names,'values':vals,'unit':'本'}
  if variant==0:return p(f'四组捐书情况：{table}。一共捐了多少本？',sum(vals),f'{"＋".join(map(str,vals))}＝{sum(vals)}本。','本',diagram=diagram)
  if variant==1:return p(f'四组捐书情况：{table}。最多的一组比最少的一组多多少本？',max(vals)-min(vals),f'最多{max(vals)}本，最少{min(vals)}本，相差{max(vals)}－{min(vals)}＝{max(vals)-min(vals)}本。','本',diagram=diagram)
  return p(f'四组共捐{sum(vals)}本书。甲组{vals[0]}本、乙组{vals[1]}本、丙组{vals[2]}本。丁组捐多少本？',vals[3],f'{sum(vals)}－{vals[0]}－{vals[1]}－{vals[2]}＝{vals[3]}本。','本')
 if t=='navigation':
  speed=rng.choice([30,40,50,60,80]);hours=rng.randint(1,5);distance=speed*hours;stop=rng.randint(5,45);start=rng.randint(6*60,17*60)
  if variant==0:return p(f'全程{distance}千米，按每小时{speed}千米匀速行驶，不停留，导航预计用时多少分钟？',hours*60,f'{distance}÷{speed}＝{hours}小时，{hours}×60＝{hours*60}分钟。','分钟')
  if variant==1:return p(f'导航预计行车{hours*60}分钟，实际行车时间相同，但途中额外停车{stop}分钟。实际全程用时多少分钟？',hours*60+stop,f'{hours*60}＋{stop}＝{hours*60+stop}分钟。','分钟')
  end=start+hours*60+stop;ans=f'{end//60:02d}:{end%60:02d}'
  return Problem(f'{start//60:02d}:{start%60:02d}出发，行车{hours}小时，中途还停车{stop}分钟，当天几点到达？用24小时制“时:分”表示。',ans,f'出发时刻加{hours}小时，再加{stop}分钟，到达时刻为{ans}。',[f'{(end+j)//60:02d}:{(end+j)%60:02d}' for j in (10,-10,60)])
 raise ValueError('未知组件')

@lru_cache(maxsize=40)
def candidates(key,level):
 # Deduplicate actual problem semantics before reporting capacity.
 unique={}
 for i in range(1800):
  item=problem(key,i,level);unique.setdefault(digest([item.stem,item.answer]),i)
 return tuple(unique.values())

def signature(key,index,level):
 item=problem(key,index,level)
 return 'g4:'+digest([item.stem,item.answer])

def question(rule,index,seed,position,columns):
 item=problem(rule['generator'],index,rule['difficulty']);kind=rule['kind'];rng=Random(seed)
 wrong=list(dict.fromkeys(x for x in item.wrong if x!=item.answer))
 if len(wrong)<3:raise ValueError('选择题干扰项不足')
 stem=item.stem;answer={'kind':'text','value':item.answer};options=[];explanation=item.explanation
 if kind=='选择题':
  values=[item.answer,*wrong[:3]];rng.shuffle(values)
  options=[{'id':str(uuid5(NAMESPACE_URL,seed+':'+v)),'value':v} for v in values]
  answer={'kind':'single_choice','value':item.answer,'correct_option_id':next(o['id'] for o in options if o['value']==item.answer)}
 elif kind=='判断题':
  claim=item.answer if rng.randrange(2)==0 else rng.choice(wrong)
  stem+=f' 小明的答案是“{claim}”。判断这个答案是否正确，并在错误时改正。（　）'
  answer={'kind':'text','value':'正确' if claim==item.answer else '错误'}
  explanation=f'正确答案为{item.answer}。'+explanation
 elif kind=='填空题':stem+=' 答：________。'
 else:stem+=' 请写出思考或计算过程。'
 return {'schema_version':1,'id':str(uuid5(NAMESPACE_URL,seed)),'position':position,'question_type':KIND_MAP[kind],'render_mode':'direct','difficulty':('basic','standard','challenge')[LEVELS[rule['difficulty']]],
 'stem_blocks':[{'type':'text','text':stem}],'options':options,'answer':answer,'explanation_steps':[{'blocks':[{'type':'text','text':explanation}]}],
 'layout':{'questions_per_row':columns,'solutions_per_row':columns,'answer_space_mm':25 if kind in ('解答题','应用题') else 6,'keep_together':True,'diagram_size_mm':None},
 'render_spec':{'kind':'curriculum','component':rule['generator'],'index':index,'seed':seed,'diagram':item.diagram}}

def verify(rule,q,columns):
 spec=q['render_spec'];idx=spec['index']
 if spec['component']!=rule['generator'] or idx not in candidates(rule['generator'],rule['difficulty']):raise ValueError('CURRICULUM_PARAMETERS_INVALID')
 expected=question(rule,idx,spec['seed'],q['position'],columns)
 for k in expected:
  if q[k]!=expected[k]:raise ValueError('CURRICULUM_CONTENT_INVALID:'+k)
 return signature(rule['generator'],idx,rule['difficulty'])
