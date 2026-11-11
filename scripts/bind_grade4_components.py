"""Associate installed components with the user's existing upper-grade-four directory.
Dry run by default. --apply makes a SQLite backup and appends associations in one transaction.
Never enables directories or publishes templates.
"""
from pathlib import Path
import argparse,json,sqlite3,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from sqlalchemy import select,func
from app.core.database import make_engine,write_transaction
from app.core.time import beijing_now
from app.models.identity import AdminUser
from app.v2.models import Directory,Task,Audit
from app.generators.grade4 import PREFIX,TOPICS

BINDINGS={
 'GD4_MATH_UP_RSGDDS':'large_numbers','GD4_MATH_UP_BM':'encoding','GD4_MATH_UP_XYJ':'angles',
 'GD4_MATH_UP_ZSCF2':'multiplication','GD4_MATH_UP_WMSHDKJ2':'space','GD4_MATH_UP_YSL':'laws',
 'GD4_MATH_UP_STXDXW':'count_shapes','GD4_MATH_UP_TXDAM':'shape_patterns','GD4_MATH_UP_YSSLGXJJWT':'quantities',
 'GD4_MATH_UP_SJDBSHFX1':'statistics','GD4_MATH_UP_DHGDSJZM':'navigation',
}

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--database',type=Path,required=True)
 parser.add_argument('--apply',action='store_true')
 args=parser.parse_args();path=args.database.resolve()
 if not path.is_file():raise SystemExit('数据库不存在；不自动创建空库')
 backup=None
 if args.apply:
  backup=ROOT/'backend/var/backups'/beijing_now().strftime('%Y%m%d-%H%M%S-%f')/path.name
  backup.parent.mkdir(parents=True)
  with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as source,sqlite3.connect(backup) as target:source.backup(target)
 engine=make_engine(path)
 try:
  with write_transaction(engine) as session:
   if session.scalar(select(func.count()).select_from(Task).where(Task.status.in_(['queued','running']))):raise RuntimeError('存在处理中任务，稍后执行')
   root=session.scalar(select(Directory).where(Directory.code=='GD4_MATH_SHANGCE',Directory.parent_id.is_(None)))
   if not root:raise RuntimeError('未找到用户创建的四年级数学上册目录')
   leaves={r.code:r for r in session.scalars(select(Directory).where(Directory.parent_id==root.id))}
   if set(BINDINGS)-set(leaves):raise RuntimeError('目录不完整，拒绝部分绑定')
   admin=session.scalar(select(AdminUser).limit(1))
   if args.apply and not admin:raise RuntimeError('没有管理员可记录审计')
   changes=[]
   for code,topic in BINDINGS.items():
    row=leaves[code];key=PREFIX+topic+'_v1';current=json.loads(row.components)
    changed=key not in current
    changes.append({'directory':row.name,'component':key,'changed':changed,'status':row.status})
    if args.apply and changed:
     row.components=json.dumps(current+[key]);row.revision+=1;row.updated_at=beijing_now()
     session.add(Audit(admin_id=admin.id,action='directory.component.install',entity_id=row.id,detail=json.dumps({'component':key,'source':'bind_grade4_components.py'},ensure_ascii=False)))
   print(json.dumps({'applied':args.apply,'backup':str(backup) if backup else None,'changes':changes},ensure_ascii=False,indent=2))
 finally:engine.dispose()
if __name__=='__main__':main()
