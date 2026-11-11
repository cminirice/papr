"""Export portable content configuration, excluding identity, jobs, files and review evidence."""
from pathlib import Path
import argparse,json,sqlite3,sys
from uuid import uuid5,NAMESPACE_URL
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'))
from app.core.time import beijing_now
from app.v2.engine import components
from app.schemas.settings import CountSetting,GenerationSetting,RetentionSetting

TABLES=('v2_directory','v2_component_state','v2_template','v2_version','app_setting')
def literal(value):
 if value is None:return 'NULL'
 if isinstance(value,int):return str(value)
 return "'"+str(value).replace("'","''")+"'"
def insert(table,row):
 return 'INSERT INTO "'+table+'" ('+','.join('"'+k+'"' for k in row)+') VALUES ('+','.join(literal(v) for v in row.values())+');'

def export(database,output):
 database=Path(database).resolve(strict=True);output=Path(output)
 now=beijing_now().isoformat(timespec='microseconds')
 with sqlite3.connect(database.as_uri()+'?mode=ro',uri=True) as source:
  source.row_factory=sqlite3.Row;source.execute('BEGIN')
  schema=source.execute('select version_num from alembic_version').fetchone()[0]
  data={t:[dict(r) for r in source.execute('SELECT * FROM "'+t+'"')] for t in TABLES}
 directories=sorted(data['v2_directory'],key=lambda r:(r['parent_id'] is not None,r['sort'],r['id']))
 saved_states={r['key']:r for r in data['v2_component_state']}
 states=[]
 for component in components():
  key=component['id'];states.append(saved_states.get(key) or {'id':str(uuid5(NAMESPACE_URL,'papr-config:'+key)),'created_at':now,'updated_at':now,'key':key,'enabled':1,'revision':1})
 templates=data['v2_template'];versions=data['v2_version']
 latest={t['id']:max((v for v in versions if v['template_id']==t['id']),key=lambda v:v['number'])['id'] for t in templates}
 for t in templates:t['enabled']=0;t['published_id']=None
 for v in versions:v['sealed']=int(v['id']!=latest[v['template_id']])
 defaults={'question_count_options':CountSetting,'generation_limits':GenerationSetting,'retention_policy':RetentionSetting}
 settings={r['key']:r for r in data['app_setting']}
 for key,model in defaults.items():
  row=settings.get(key) or {'key':key,'value':model().model_dump_json(),'schema_version':1,'lock_version':1,'updated_by':None,'updated_at':now}
  model.model_validate_json(row['value']);row['updated_by']=None;settings[key]=row
 counts={t:len(rows) for t,rows in zip(TABLES,[directories,states,templates,versions,list(settings.values())])}
 checks=' AND '.join('(SELECT count(*) FROM "'+t+'")=0' for t in TABLES)
 sql=['-- papr SQLite configuration export','-- Generated '+now,'-- Apply AFTER alembic upgrade head, only to empty configuration tables.',
 '-- Contains no admin passwords, sessions, anonymous histories, PDFs or review evidence.',
 '-- Templates are imported as disabled drafts; validate/review/publish on the target server.',
 '-- Counts: '+json.dumps(counts,ensure_ascii=False),'PRAGMA foreign_keys=ON;','BEGIN IMMEDIATE;',
 'CREATE TEMP TABLE papr_import_guard (ok INTEGER CHECK(ok=1));',
 'INSERT INTO papr_import_guard SELECT CASE WHEN '+checks+' AND (SELECT version_num FROM alembic_version)='+literal(schema)+' THEN 1 ELSE 0 END;']
 for table,rows in zip(TABLES,[directories,states,templates,versions,list(settings.values())]):
  sql.extend(insert(table,row) for row in rows)
 sql+=['DROP TABLE papr_import_guard;','COMMIT;','PRAGMA foreign_key_check;','']
 output.parent.mkdir(parents=True,exist_ok=True);output.write_text('\n'.join(sql))
 return counts

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--database',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
 args=parser.parse_args();print(json.dumps(export(args.database,args.output),ensure_ascii=False))
if __name__=='__main__':main()
