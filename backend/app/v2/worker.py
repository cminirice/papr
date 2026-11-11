"""Same private PDF storage; separate v2 queue, attempt/token fencing and success transaction."""
from datetime import timedelta
import json,sys
from uuid import uuid4
from sqlalchemy import select
from app.core.database import write_transaction
from app.core.time import beijing_now
from app.core.errors import ServiceError
from app.models.identity import AppUser
from app.services import paper_runtime
from app.services.paper_execution import check_metadata
from app.services.identity.cooldown import record_generation_success
from app.services.pdf_storage import PdfTarget,save_pair,read_verified
from app.v2.models import Task,Artifact
from app.v2 import engine as math,service

class LeaseLost(Exception):pass

def fenced(session,claim,now):
 job=session.get(Task,claim['id'])
 if not job or job.status!='running' or job.token!=claim['token'] or job.attempt!=claim['attempt'] or job.lease_until<=now:raise LeaseLost()
 return job

def claim(engine,now):
 with write_transaction(engine) as session:
  for job in session.scalars(select(Task).where(Task.status=='running',Task.lease_until<=now)):
   for a in session.scalars(select(Artifact).where(Artifact.task_id==job.id,Artifact.status=='pending')):a.status='failed'
   job.status='queued' if job.attempt<2 else 'failed';job.error='WORKER_LOST';job.token=None;job.lease_until=None
   if job.status=='failed':job.finished_at=now
  session.flush()
  job=session.scalar(select(Task).where(Task.status=='queued').order_by(Task.created_at,Task.id).limit(1))
  if not job:return None
  job.status='running';job.phase='generating';job.attempt+=1;job.token=str(uuid4());job.lease_until=now+timedelta(seconds=30)
  return {'id':job.id,'token':job.token,'attempt':job.attempt,'kind':job.kind,'plan':json.loads(job.plan)}

def run_once(engine,settings,*,clock=beijing_now,render=paper_runtime.render,on_error=None):
 claimed=claim(engine,clock())
 if not claimed:return False
 def pulse():
  with write_transaction(engine) as session:
   job=fenced(session,claimed,clock());job.lease_until=clock()+timedelta(seconds=30)
  paper_runtime.heartbeat(engine,paper_runtime.config_hash(settings),clock())
 try:
  with write_transaction(engine) as session:service.check_plan(session,claimed['plan'],claimed['kind']=='paper')
  plan={**claimed['plan'],'validate':claimed['kind']=='validate'}
  document=json.loads(paper_runtime.process([sys.executable,'-m','app.v2.child'],data=math.canonical(plan),timeout=60,pulse=pulse))
  # Child mathematically validates every rule and complete paper before returning.
  targets={k:PdfTarget(uuid4(),clock()) for k in ('student_pdf','solution_pdf')}
  with write_transaction(engine) as session:
   job=fenced(session,claimed,clock());service.check_plan(session,plan,job.kind=='paper');job.phase='rendering'
   snapshot=math.canonical(document)
   if job.snapshot and job.snapshot!=snapshot:raise ValueError('SNAPSHOT_MISMATCH')
   job.snapshot=snapshot
   for kind,target in targets.items():session.add(Artifact(id=str(target.asset_id),task_id=job.id,attempt=job.attempt,token=job.token,kind=kind,created_at=target.registered_at,updated_at=target.registered_at))
  contents,metadata=render(document,settings,pulse=pulse);check_metadata(document,contents,metadata);pulse()
  with write_transaction(engine) as session:fenced(session,claimed,clock()).phase='saving'
  saved=save_pair(settings.generated_root,targets,contents)
  for asset in saved.values():read_verified(settings.generated_root,asset)
  pulse()
  with write_transaction(engine) as session:
   now=clock();job=fenced(session,claimed,now);service.check_plan(session,plan,job.kind=='paper')
   if paper_runtime.config_hash(settings)!=plan['renderer']:raise ValueError('RENDERER_CHANGED')
   for kind,asset in saved.items():
    a=session.get(Artifact,str(asset.target.asset_id))
    if a.token!=job.token or a.attempt!=job.attempt or a.status!='pending':raise LeaseLost()
    a.metadata_json=math.canonical({'bytes':asset.byte_size,'sha256':asset.sha256,'pages':asset.pages,'parser':asset.parser,'renderer':metadata});a.status='ready'
   if job.kind=='paper':
    user=service.get(session,AppUser,job.user_id)
    if user.status!='active' or user.deleted_at:raise ValueError('USER_DISABLED')
    record_generation_success(session,user,now)
   job.status='succeeded';job.phase='done';job.error=None;job.finished_at=now;job.updated_at=now;job.lease_until=None
 except LeaseLost:pass
 except Exception as exc:
  if on_error:on_error(exc)
  code=exc.code if isinstance(exc,ServiceError) else 'GENERATION_FAILED'
  try:
   with write_transaction(engine) as session:
    job=fenced(session,claimed,clock());job.status='failed';job.phase='done';job.error=code;job.finished_at=clock();job.lease_until=None
    for a in session.scalars(select(Artifact).where(Artifact.task_id==job.id,Artifact.status=='pending')):a.status='failed'
  except LeaseLost:pass
 return True
