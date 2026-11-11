import json
from uuid import UUID
from fastapi import APIRouter,Depends,Request,Response,Header,Query
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from app.auth.dependencies import current_admin,current_user,Principal
from app.auth.http import clock,rate_subject
from app.core.database import write_transaction
from app.core.errors import ServiceError
from app.v2 import service,schemas
from app.v2.models import Directory,Template,Version,Task,Review,Artifact,ComponentState,Audit
from app.services.pdf_storage import PdfTarget,SavedPdf,read_verified,PdfStorageError
admin=APIRouter(prefix='/admin/api/v2',tags=['v2-admin'])
public=APIRouter(prefix='/api/v2',tags=['v2-public'])
def out(request,data):return {'data':data,'request_id':str(request.state.request_id)}

@admin.get('/workspace')
def workspace(request:Request,p:Principal=Depends(current_admin)):
 with Session(request.app.state.engine) as session:return out(request,service.workspace(session))

@admin.put('/items/{kind}/{id}')
def save(kind:str,id:UUID,body:schemas.ItemInput,request:Request,p:Principal=Depends(current_admin)):
 with write_transaction(request.app.state.engine) as session:
  now=clock(request);service.authorize(session,p,True,now)
  if kind in ('catalogs','nodes'):service.save_directory(session,kind,str(id),body,p,now)
  elif kind=='templates':service.save_template(session,str(id),body,p,now)
  else:service.fail('NOT_FOUND','记录类型不存在',404)
  session.flush();return out(request,service.workspace(session))

@admin.patch('/components/{key}')
def component(key:str,body:schemas.ComponentInput,request:Request,p:Principal=Depends(current_admin)):
 with write_transaction(request.app.state.engine) as session:
  service.authorize(session,p,True,clock(request))
  if key not in service.math.CAPABILITIES:service.fail('NOT_FOUND','组件不存在',404)
  row=session.scalar(select(ComponentState).where(ComponentState.key==key))
  if row:service.revision(row,body.revision)
  elif body.revision:service.fail('REVISION_CONFLICT','请刷新组件')
  else:row=ComponentState(key=key,revision=0);session.add(row)
  row.enabled=int(body.enabled);row.revision+=1;service.audit(session,p.owner_id,'component.toggle',row.id or key);session.flush()
  return out(request,service.workspace(session))

@admin.post('/versions/{id}/jobs/{action}',status_code=202)
def start(id:UUID,action:str,body:schemas.StartInput,request:Request,idempotency_key:str=Header(default=''),p:Principal=Depends(current_admin)):
 if action not in ('preview','validate') or str(id)!=body.version_id:service.fail('INVALID_CONFIG','任务类型不正确',422)
 with write_transaction(request.app.state.engine) as session:
  service.authorize(session,p,True,clock(request));job=service.enqueue(session,body,idempotency_key,action,p,request.app.state.settings,clock(request));return out(request,service.task_view(session,job))

@admin.post('/versions/{id}/review')
def review(id:UUID,body:schemas.ReviewInput,request:Request,p:Principal=Depends(current_admin)):
 with write_transaction(request.app.state.engine) as session:
  service.authorize(session,p,True,clock(request));r=service.record_review(session,str(id),body,p);return out(request,{'id':r.id})

@admin.post('/templates/{id}/publish')
def publish(id:UUID,body:schemas.PublishInput,request:Request,p:Principal=Depends(current_admin)):
 with write_transaction(request.app.state.engine) as session:
  service.authorize(session,p,True,clock(request));service.publish(session,str(id),body,p,request.app.state.settings);session.flush();return out(request,service.workspace(session))

@admin.post('/templates/{id}/disable')
def disable(id:UUID,body:schemas.RevisionInput,request:Request,p:Principal=Depends(current_admin)):
 with write_transaction(request.app.state.engine) as session:
  service.authorize(session,p,True,clock(request));t=service.get(session,Template,str(id));service.revision(t,body.revision);t.enabled=0;t.revision+=1;service.audit(session,p.owner_id,'template.disable',t.id);session.flush();return out(request,service.workspace(session))

@admin.get('/jobs/{id}')
def admin_job(id:UUID,request:Request,p:Principal=Depends(current_admin)):
 with Session(request.app.state.engine) as session:return out(request,service.task_view(session,service.get(session,Task,str(id)),True))

@public.get('/templates')
def templates(request:Request):
 with Session(request.app.state.engine) as session:return out(request,service.public_templates(session,request.app.state.settings))

@public.post('/jobs',status_code=202)
def generate(body:schemas.StartInput,request:Request,idempotency_key:str=Header(default=''),p:Principal=Depends(current_user)):
 with write_transaction(request.app.state.engine) as session:
  service.authorize(session,p,False,clock(request));job=service.enqueue(session,body,idempotency_key,'paper',p,request.app.state.settings,clock(request),rate_subject(request));return out(request,service.task_view(session,job))

@public.get('/history')
def history(request:Request,p:Principal=Depends(current_user),offset:int=Query(0,ge=0),limit:int=Query(100,ge=1,le=100)):
 with Session(request.app.state.engine) as session:
  rows=session.scalars(select(Task).where(Task.user_id==p.owner_id).order_by(Task.created_at.desc(),Task.id).offset(offset).limit(limit))
  return out(request,[service.task_view(session,j) for j in rows])

@public.get('/jobs/{id}')
def job(id:UUID,request:Request,p:Principal=Depends(current_user)):
 with Session(request.app.state.engine) as session:
  j=service.get(session,Task,str(id))
  if j.user_id!=p.owner_id:service.fail('NOT_FOUND','记录不存在',404)
  return out(request,service.task_view(session,j,False))

@public.post('/jobs/{id}/cancel')
def cancel(id:UUID,request:Request,p:Principal=Depends(current_user)):
 with write_transaction(request.app.state.engine) as session:
  service.authorize(session,p,False,clock(request));j=service.get(session,Task,str(id))
  if j.user_id!=p.owner_id:service.fail('NOT_FOUND','记录不存在',404)
  if j.status!='queued':service.fail('JOB_NOT_CANCELLABLE','仅排队中的任务可取消')
  j.status='cancelled';j.finished_at=clock(request);return out(request,service.task_view(session,j))

def file_content(id,request,owner=None):
 with Session(request.app.state.engine) as session:
  a=service.get(session,Artifact,str(id));j=service.get(session,Task,a.task_id)
  if (owner is not None and j.user_id!=owner) or a.status!='ready' or j.status!='succeeded':service.fail('NOT_FOUND','文件不存在',404)
  if owner is not None and session.scalar(select(Audit.id).where(Audit.entity_id==j.id,Audit.action=='paper.withdraw').limit(1)):service.fail('PAPER_WITHDRAWN','试卷已撤回，请查看勘误说明',409)
  meta=json.loads(a.metadata_json);asset=SavedPdf(PdfTarget(UUID(a.id),a.created_at),meta['bytes'],meta['sha256'],meta['pages'],meta['parser'])
 try:data=read_verified(request.app.state.settings.generated_root,asset)
 except PdfStorageError:service.fail('FILE_UNAVAILABLE','文件暂不可用，请联系管理员',503)
 return Response(data,media_type='application/pdf',headers={'Content-Disposition':f'inline; filename="{id}.pdf"','Cache-Control':'no-store'})

@public.get('/files/{id}')
def user_file(id:UUID,request:Request,p:Principal=Depends(current_user)):return file_content(id,request,p.owner_id)
@admin.get('/artifacts/{id}')
def admin_file(id:UUID,request:Request,p:Principal=Depends(current_admin)):return file_content(id,request)

@admin.get('/operations')
def operations(request:Request,p:Principal=Depends(current_admin),offset:int=Query(0,ge=0),limit:int=Query(100,ge=1,le=100)):
 with Session(request.app.state.engine) as session:return out(request,[service.task_view(session,j) for j in session.scalars(select(Task).where(Task.kind=='paper').order_by(Task.created_at.desc()).offset(offset).limit(limit))])

@admin.get('/statistics')
def statistics(request:Request,p:Principal=Depends(current_admin)):
 with Session(request.app.state.engine) as session:
  counts=dict(session.execute(select(Task.status,func.count()).where(Task.kind=='paper').group_by(Task.status)).all())
  return out(request,{'counts':counts,'templates':len(service.public_templates(session,request.app.state.settings)),'directories':session.scalar(select(func.count()).select_from(Directory))})

from datetime import date,timedelta
from app.services.admin_operations import date_range
@admin.get('/overview')
def overview(request:Request,p:Principal=Depends(current_admin),date_from:date|None=None,date_to:date|None=None):
 now=clock(request);start_date,end_date,start,end=date_range(date_from,date_to,now)
 with Session(request.app.state.engine) as session:
  jobs=list(session.scalars(select(Task).where(Task.kind=='paper')))
  def counts(a,b):
   submitted=[j for j in jobs if a<=j.created_at<b]
   finished=[j for j in jobs if j.finished_at and a<=j.finished_at<b]
   return {'submitted':len(submitted),'succeeded':sum(j.status=='succeeded' for j in finished),'failed':sum(j.status=='failed' for j in finished),'cancelled':sum(j.status=='cancelled' for j in finished),'active_subjects':len({j.user_id for j in submitted})}
  daily=[];day=start
  while day<end:daily.append({'date':day.date(),**counts(day,day+timedelta(days=1))});day+=timedelta(days=1)
  def queue(kind):return {s:session.scalar(select(func.count()).select_from(Task).where(Task.kind.in_(kind),Task.status==s)) for s in ('queued','running')}
  return out(request,{'date_from':start_date,'date_to':end_date,'as_of':now,'totals':counts(start,end),'daily':daily,'generation_queue':queue(['paper']),'validation_queue':queue(['validate','preview']),'usage':{'preview':0,'print_intent':0}})

@admin.post('/workspace/import')
def import_workspace(body:schemas.ImportWorkspace,request:Request,p:Principal=Depends(current_admin)):
 from uuid import uuid4
 with write_transaction(request.app.state.engine) as session:
  now=clock(request);service.authorize(session,p,True,now)
  if session.scalar(select(func.count()).select_from(Directory)) or session.scalar(select(func.count()).select_from(Template)):service.fail('IMPORT_NOT_EMPTY','仅空内容库可导入，避免覆盖已有配置')
  mapping={}
  for entry in body.catalogs+body.nodes+body.templates:
   if entry.old_id in mapping:service.fail('INVALID_CONFIG','原记录ID重复',422)
   mapping[entry.old_id]=str(uuid4())
  for entry in body.catalogs:
   item=entry.item.model_copy(update={'revision':0,'generators':[]})
   service.save_directory(session,'catalogs',mapping[entry.old_id],item,p,now);session.flush()
  for entry in body.nodes:
   if entry.item.catalog not in {c.old_id for c in body.catalogs}:service.fail('INVALID_CONFIG','二级目录缺少所属一级目录',422)
   item=entry.item.model_copy(update={'revision':0,'catalog':mapping[entry.item.catalog]})
   service.save_directory(session,'nodes',mapping[entry.old_id],item,p,now);session.flush()
  for entry in body.templates:
   if entry.item.catalog not in {c.old_id for c in body.catalogs}:service.fail('INVALID_CONFIG','模板缺少一级目录',422)
   rules=[]
   for r in entry.item.rules:
    if r.node not in {n.old_id for n in body.nodes}:service.fail('INVALID_CONFIG','模板缺少二级目录',422)
    rules.append(r.model_copy(update={'node':mapping[r.node]}))
   item=entry.item.model_copy(update={'revision':0,'catalog':mapping[entry.item.catalog],'rules':rules,'status':'草稿'})
   service.save_template(session,mapping[entry.old_id],item,p,now)
  service.audit(session,p.owner_id,'workspace.import',p.owner_id);session.flush();return out(request,service.workspace(session))

@admin.post('/papers/{id}/notices')
def notice(id:UUID,body:schemas.NoticeInput,request:Request,p:Principal=Depends(current_admin)):
 with write_transaction(request.app.state.engine) as session:
  service.authorize(session,p,True,clock(request));j=service.get(session,Task,str(id))
  if j.kind!='paper' or j.status!='succeeded':service.fail('INVALID_CONFIG','仅已完成试卷可勘误',422)
  service.audit(session,p.owner_id,'paper.withdraw' if body.withdraw else 'paper.notice',j.id,{'message':body.message});session.flush()
  return out(request,service.task_view(session,j))

@admin.get('/audit')
def audit_list(request:Request,p:Principal=Depends(current_admin),offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100)):
 with Session(request.app.state.engine) as session:return out(request,[{'id':a.id,'action':a.action,'entity_id':a.entity_id,'detail':json.loads(a.detail),'created_at':a.created_at} for a in session.scalars(select(Audit).order_by(Audit.created_at.desc(),Audit.id).offset(offset).limit(limit))])

@admin.get('/templates/{id}/versions')
def versions(id:UUID,request:Request,p:Principal=Depends(current_admin)):
 with Session(request.app.state.engine) as session:
  service.get(session,Template,str(id))
  rows=[]
  for v in session.scalars(select(Version).where(Version.template_id==str(id)).order_by(Version.number.desc())):
   review=session.scalar(select(Review).where(Review.version_id==v.id,Review.content_hash==v.content_hash).order_by(Review.created_at.desc()).limit(1))
   rows.append({'id':v.id,'number':v.number,'sealed':bool(v.sealed),'name':json.loads(v.content)['name'],'configuration_hash':v.content_hash,'review_id':review.id if review and review.approved else None})
  return out(request,rows)
