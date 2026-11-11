"""Create a separate workflow database; preserve old DB/files, copy only administrator hash."""
from pathlib import Path
import argparse,os,sqlite3,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from alembic.config import Config
from alembic import command
from app.core.database import make_engine,write_transaction
from app.models.identity import AdminUser
from app.auth.security import initialize_rate_key
from sqlalchemy import select

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--database',type=Path,default=ROOT/'backend/var/papr-v2.sqlite3')
 parser.add_argument('--copy-admin-from',type=Path,default=ROOT/'backend/var/papr.sqlite3')
 args=parser.parse_args();target=args.database.resolve();source=args.copy_admin_from.resolve()
 if target==source:raise SystemExit('新库必须与原库路径不同')
 if target.exists():raise SystemExit('目标文件已存在，拒绝覆盖；升级请显式运行alembic upgrade head')
 old_env=os.environ.get('PAPR_DB_PATH');os.environ['PAPR_DB_PATH']=str(target)
 try:command.upgrade(Config(str(ROOT/'backend/alembic.ini')),'head')
 finally:
  if old_env is None:os.environ.pop('PAPR_DB_PATH',None)
  else:os.environ['PAPR_DB_PATH']=old_env
 engine=make_engine(target)
 if source.is_file():
  with sqlite3.connect(f'{source.as_uri()}?mode=ro',uri=True) as src:
   src.row_factory=sqlite3.Row
   rows=src.execute('SELECT * FROM admin_user').fetchall()
  from app.core.time import parse_stored_time
  with write_transaction(engine) as session:
   for row in rows:
    data=dict(row)
    for key in ('created_at','updated_at','last_login_at'):
     if data.get(key):data[key]=parse_stored_time(data[key])
    session.add(AdminUser(**data))
 initialize_rate_key(target.parent/'rate-limit.key')
 engine.dispose()
 print(f'新库已创建：{target}；原数据库和PDF保持不变；未复制会话、历史或自动发布内容。')
if __name__=='__main__':main()
