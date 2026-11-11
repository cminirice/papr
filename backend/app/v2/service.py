import json
from uuid import uuid4
from sqlalchemy import select,func
from app.core.errors import ServiceError
from app.core.time import beijing_now
from app.models.identity import AppUser,AdminSession,UserSession,AdminUser
from app.services.identity.cooldown import check_generation_admission
from app.services import paper_runtime
from app.v2.models import Directory,Template,Version,Task,Review,ComponentState,Audit,Artifact
from app.v2 import engine as math


def fail(code,message,status=409):raise ServiceError(status,code,message)
def get(session,model,id):
 row=session.get(model,id)
 if row is None:fail('NOT_FOUND','记录不存在',404)
 return row

def authorize(session,principal,admin,now):
 stored=get(session,AdminSession if admin else UserSession,principal.session_id)
 if stored.revoked_at or stored.expires_at<=now:fail('SESSION_EXPIRED','会话已失效',401)
 owner=get(session,AdminUser if admin else AppUser,principal.owner_id)
 if owner.status!='active':fail('SESSION_EXPIRED','会话已失效',401)
 return owner

def audit(session,admin,action,id,detail=None):session.add(Audit(admin_id=admin,action=action,entity_id=id,detail=math.canonical(detail or {})))
def revision(row,expected):
 if row.revision!=expected:fail('REVISION_CONFLICT','内容已被修改，请刷新后重试')

def states(session):
 saved={s.key:s for s in session.scalars(select(ComponentState))}
 return {k:{'enabled':bool(saved[k].enabled) if k in saved else True,'revision':saved[k].revision if k in saved else 0} for k in math.CAPABILITIES}

def directory_item(row):return {'id':row.id,'code':row.code,'name':row.name,'description':row.description,'status':row.status,'catalog':row.parent_id or '', 'sort':row.sort,'generators':json.loads(row.components),'revision':row.revision,'type':'主题','rules':[],'tags':[],'columns':2}

def current_version(session,template):
 return session.scalar(select(Version).where(Version.template_id==template.id).order_by(Version.number.desc()).limit(1))

def template_item(session,t):
 v=current_version(session,t)
 data=json.loads(v.content)
 review=session.scalar(select(Review).where(Review.version_id==v.id,Review.content_hash==v.content_hash).order_by(Review.created_at.desc()).limit(1))
 jobs=list(session.scalars(select(Task).where(Task.version_id==v.id,Task.kind!='paper').order_by(Task.created_at.desc()).limit(50)))
 matching=[j for j in jobs if json.loads(j.plan)['hash']==v.content_hash]
 return {**data,'id':t.id,'code':t.code,'status':'启用' if t.enabled else '草稿' if not t.published_id else '停用','revision':t.revision,'version_id':v.id,'configuration_hash':v.content_hash,'sealed':bool(v.sealed),'published_version_id':t.published_id,
 'review_id':review.id if review and review.approved else None,'review_comment':review.comment if review else '',
 'preview_job':next((task_view(session,j) for j in matching if j.kind=='preview'),None),'validation_job':next((task_view(session,j) for j in matching if j.kind=='validate'),None)}

def workspace(session):
 dirs=list(session.scalars(select(Directory).order_by(Directory.sort,Directory.created_at)))
 return {'catalogs':[directory_item(d) for d in dirs if not d.parent_id],'nodes':[directory_item(d) for d in dirs if d.parent_id], 'templates':[template_item(session,t) for t in session.scalars(select(Template).order_by(Template.created_at))], 'components':math.components(),'component_states':states(session)}

def save_directory(session,kind,id,body,principal,now):
 root=kind=='catalogs';row=session.get(Directory,id)
 if row:revision(row,body.revision)
 elif body.revision:fail('REVISION_CONFLICT','目录不存在，请刷新')
 parent=None if root else body.catalog
 if not root:
  p=get(session,Directory,parent)
  if p.parent_id:fail('DIRECTORY_DEPTH_INVALID','只能添加两级目录',422)
 if row and row.parent_id!=parent:fail('DIRECTORY_DEPTH_INVALID','不支持移动目录',422)
 if root and body.generators:fail('LEAF_REQUIRED','只有二级目录可关联组件',422)
 if any(g not in math.CAPABILITIES for g in body.generators):fail('UNSUPPORTED_CAPABILITY','组件不存在',422)
 dup=session.scalar(select(Directory).where(Directory.code==body.code,Directory.parent_id==parent,Directory.id!=id))
 if dup:fail('DUPLICATE_CODE','同一级目录下编码已存在')
 if row is None:row=Directory(id=id,parent_id=parent,revision=0);session.add(row)
 row.code=body.code;row.name=body.name.strip();row.description=body.description;row.status=body.status;row.sort=body.sort;row.components=math.canonical(list(dict.fromkeys(body.generators)));row.revision+=1;row.updated_at=now
 if not row.name:fail('VALIDATION_ERROR','名称不能为空',422)
 audit(session,principal.owner_id,'directory.save',id)
 return row

def normalize(session,body):
 root=get(session,Directory,body.catalog)
 if root.parent_id:fail('DIRECTORY_DEPTH_INVALID','请选择一级目录',422)
 rules=[]
 for r in body.rules:
  leaf=get(session,Directory,r.node)
  if leaf.parent_id!=root.id:fail('LEAF_REQUIRED','二级目录不属于所选一级目录',422)
  if r.generator not in json.loads(leaf.components):fail('UNSUPPORTED_CAPABILITY','二级目录尚未关联该组件',422)
  rules.append({**r.model_dump(),'point':leaf.name})
 tags=list(dict.fromkeys(t.strip() for t in body.tags if t.strip()))
 if any(len(t)>30 for t in tags):fail('VALIDATION_ERROR','标签最长30字',422)
 if not body.name.strip():fail('VALIDATION_ERROR','名称不能为空',422)
 return {'name':body.name.strip(),'description':body.description,'catalog':root.id,'catalog_name':root.name,'rules':rules,'columns':body.columns,'tags':tags,**({'columns_by_kind':body.columns_by_kind} if body.columns_by_kind is not None else {})}

def save_template(session,id,body,principal,now):
 row=session.get(Template,id)
 if row:revision(row,body.revision)
 elif body.revision:fail('REVISION_CONFLICT','模板不存在，请刷新')
 if session.scalar(select(Template).where(Template.code==body.code,Template.id!=id)):fail('DUPLICATE_CODE','模板编码已存在')
 content=normalize(session,body)
 if row is None:row=Template(id=id,code=body.code,revision=0,enabled=0);session.add(row);session.flush()
 row.code=body.code;row.revision+=1;row.updated_at=now
 v=current_version(session,row)
 if v is None or v.sealed:
  v=Version(template_id=id,number=1 if v is None else v.number+1,sealed=0);session.add(v)
 v.content=math.canonical(content);v.content_hash=math.digest(content);v.updated_at=now
 audit(session,principal.owner_id,'template.save',id);session.flush()
 return row

def dependencies(session,content):
 root=get(session,Directory,content['catalog'])
 if root.parent_id or root.status!='启用':fail('TEMPLATE_UNAVAILABLE','一级目录未启用')
 enabled=states(session)
 for r in content['rules']:
  leaf=get(session,Directory,r['node'])
  if leaf.parent_id!=root.id or leaf.status!='启用' or r['generator'] not in json.loads(leaf.components) or not enabled.get(r['generator'],{}).get('enabled'):fail('TEMPLATE_UNAVAILABLE','二级目录或组件不可用')
 # Candidate construction happens in worker, not in a write transaction.
 if not content['rules'] or sum(r['count'] for r in content['rules'])>200:fail('INVALID_CONFIG','请配置1–200题的完整规则',422)
 for r in content['rules']:
  if r['difficulty'] not in math.CAPABILITIES.get(r['generator'],{}).get(r['kind'],[]):fail('UNSUPPORTED_CAPABILITY','组件不支持此题型或难度',422)

def check_plan(session,plan,paper):
 v=get(session,Version,plan['version_id']);t=get(session,Template,v.template_id)
 if v.content_hash!=plan['hash'] or math.fingerprint()!=plan['engine']:fail('CONTENT_CHANGED','内容或组件版本已变化')
 dependencies(session,plan['content'])
 if paper and (not t.enabled or t.published_id!=v.id):fail('CONTENT_CHANGED','模板当前已停用或发布版本已变化')
 return v

def enqueue(session,body,key,kind,principal,settings,now,ip_subject=None):
 try:
  from uuid import UUID
  UUID(key)
 except (ValueError,TypeError):fail('INVALID_CONFIG','需要有效的幂等标识',422)
 owner=Task.user_id if kind=='paper' else Task.admin_id
 request_hash=math.digest({'kind':kind,**body.model_dump()})
 old=session.scalar(select(Task).where(owner==principal.owner_id,Task.key==key))
 if old:
  if old.request_hash!=request_hash:fail('IDEMPOTENCY_CONFLICT','相同标识对应不同请求')
  return old
 v=get(session,Version,body.version_id);content=json.loads(v.content)
 if v.content_hash!=body.configuration_hash:fail('TEMPLATE_CHANGED','模板已改变，请刷新后确认')
 t=get(session,Template,v.template_id)
 if kind=='paper' and (not t.enabled or t.published_id!=v.id or not any(x['id']==t.id for x in public_templates(session,settings))):fail('TEMPLATE_UNAVAILABLE','模板尚未开放或验证已过期')
 dependencies(session,content)
 if not paper_runtime.ready(session,settings,now):fail('RENDERER_NOT_READY','PDF服务尚未就绪，请启动worker',503)
 if kind=='paper':
  user=get(session,AppUser,principal.owner_id);check_generation_admission(session,user,now)
  if session.scalar(select(Task.id).where(Task.user_id==user.id,Task.status.in_(['queued','running']))):fail('ACTIVE_JOB_EXISTS','已有练习正在生成')
 from app.services.settings import value as setting_value
 limits=setting_value(session,'generation_limits')
 if session.scalar(select(func.count()).select_from(Task).where(Task.status.in_(['queued','running'])))>=limits.queue_limit:fail('QUEUE_FULL','任务队列已满，请稍后重试',503)
 if kind=='paper' and ip_subject:
  from app.services.identity.limits import reserve_event
  reserve_event(session,'generation_accept',ip_subject,now,limit=limits.ip_accept_limit,seconds=60)
 plan={'version_id':v.id,'hash':v.content_hash,'content':content,'engine':math.fingerprint(),'renderer':paper_runtime.config_hash(settings),'seed':uuid4().hex,'generated_at':now.isoformat(timespec='microseconds')}
 task=Task(user_id=principal.owner_id if kind=='paper' else None,admin_id=principal.owner_id if kind!='paper' else None,kind=kind,version_id=v.id,key=key,request_hash=request_hash,plan=math.canonical(plan),created_at=now,updated_at=now)
 session.add(task);session.flush();return task

def task_view(session,j,detail=False):
 plan=json.loads(j.plan);content=plan['content']
 assets=[{'id':a.id,'kind':a.kind,'pages':json.loads(a.metadata_json)['pages']} for a in session.scalars(select(Artifact).where(Artifact.task_id==j.id,Artifact.status=='ready'))]
 result={'id':j.id,'kind':j.kind,'status':j.status,'phase':j.phase,'error':j.error,'created':j.created_at,'finished_at':j.finished_at,'name':content['name'],'templateId':get(session,Version,j.version_id).template_id,'version_id':j.version_id,'configuration_hash':plan['hash'],'tags':content['tags'],'columns':content['columns'],'columns_by_kind':content.get('columns_by_kind'),'rules':content['rules'],'assets':assets}
 notes=list(session.scalars(select(Audit).where(Audit.entity_id==j.id,Audit.action.in_(['paper.notice','paper.withdraw'])).order_by(Audit.created_at)))
 result['notices']=[json.loads(n.detail)['message'] for n in notes]
 result['withdrawn']=any(n.action=='paper.withdraw' for n in notes)
 if result['withdrawn']:result['assets']=[]
 if detail and j.snapshot:result['document']=json.loads(j.snapshot)
 return result

def public_templates(session,settings=None):
 result=[]
 for t in session.scalars(select(Template).where(Template.enabled==1,Template.published_id.is_not(None))):
  v=get(session,Version,t.published_id);content=json.loads(v.content)
  try:
   dependencies(session,content)
   review=session.scalar(select(Review).where(Review.version_id==v.id,Review.content_hash==v.content_hash).order_by(Review.created_at.desc()).limit(1))
   if not review or not review.approved:continue
   plan=json.loads(get(session,Task,review.validation_id).plan)
   if plan['engine']!=math.fingerprint() or (settings is not None and plan['renderer']!=paper_runtime.config_hash(settings)):continue
  except ServiceError:continue
  result.append({**content,'id':t.id,'version_id':v.id,'configuration_hash':v.content_hash,'available':True,'status':'启用','reason':''})
 return result

def record_review(session,v_id,body,principal):
 v=get(session,Version,v_id)
 preview=get(session,Task,body.preview_id);validation=get(session,Task,body.validation_id)
 for job,kind in ((preview,'preview'),(validation,'validate')):
  if job.version_id!=v.id or job.kind!=kind or job.status!='succeeded' or json.loads(job.plan)['hash']!=v.content_hash:fail('REVIEW_NOT_READY','请先完成当前版本的完整样例和自动验证')
  check_plan(session,json.loads(job.plan),False)
 r=Review(version_id=v.id,preview_id=preview.id,validation_id=validation.id,admin_id=principal.owner_id,content_hash=v.content_hash,approved=int(body.approved),comment=body.comment)
 session.add(r);session.flush();audit(session,principal.owner_id,'template.review',v.template_id,{'approved':body.approved});return r

def publish(session,id,body,principal,settings):
 t=get(session,Template,id);revision(t,body.revision);v=get(session,Version,body.version_id);r=get(session,Review,body.review_id)
 if v.template_id!=t.id or r.version_id!=v.id or not r.approved or r.content_hash!=v.content_hash:fail('REVIEW_REQUIRED','请完成当前版本人工审题')
 latest=session.scalar(select(Review).where(Review.version_id==v.id,Review.content_hash==v.content_hash).order_by(Review.created_at.desc()).limit(1))
 if latest.id!=r.id:fail('REVIEW_REQUIRED','请使用最新审题结论')
 for id in (r.preview_id,r.validation_id):
  job=get(session,Task,id);plan=json.loads(job.plan);check_plan(session,plan,False)
  if plan['renderer']!=paper_runtime.config_hash(settings):fail('CONTENT_CHANGED','打印资源已变更，请重新验证和审题')
 v.sealed=1;t.published_id=v.id;t.enabled=1;t.revision+=1;t.updated_at=beijing_now();audit(session,principal.owner_id,'template.publish',t.id,{'version':v.id})
