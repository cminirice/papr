"""Render actual grade-four coverage samples without publishing any content."""
from pathlib import Path
from dataclasses import replace
import json,sys,tempfile
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'))
from app.generators import grade4
from app.v2 import engine
from app.core.config import Settings
from app.core.time import beijing_now
from app.services import paper_runtime
from app.services.pdf_storage import inspect_bytes

def main():
 settings=replace(Settings.from_env(),pdf_node=Path('/Users/eric/.local/node-v22.23.2/bin/node'),pdf_browser=Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'),pdf_font=Path('/System/Library/Fonts/Supplemental/Arial Unicode.ttf'))
 directory=ROOT/'backend/var/pdf-samples'/('grade4-'+beijing_now().strftime('%Y%m%d-%H%M%S'));directory.mkdir(parents=True)
 questions=[]
 for ci,component in enumerate(grade4.manifest()):
  kinds=[c['kind'] for c in component['capabilities']]
  for variant in range(3):
   rule={'generator':component['id'],'kind':kinds[(ci+variant)%len(kinds)],'difficulty':'基础'}
   q=grade4.question(rule,variant,'sample:'+component['id']+str(variant),len(questions)+1,1)
   grade4.verify(rule,q,1);questions.append(q)
 document={'schema_version':1,'title':'四年级上册 · 组件覆盖样卷','generated_at':beijing_now().isoformat(timespec='microseconds'),'questions':questions}
 (directory/'input.json').write_text(engine.canonical(document))
 contents,metadata=paper_runtime.render(document,settings)
 parsed={}
 for kind,content in contents.items():
  (directory/(kind+'.pdf')).write_bytes(content);parsed[kind]=inspect_bytes(content)
 (directory/'verification.json').write_text(json.dumps({'questions':len(questions),'components':len(grade4.TOPICS),'parsed':parsed,'renderer':metadata,'human_review':'pending'},ensure_ascii=False,indent=2))
 print(json.dumps({'directory':str(directory),'questions':len(questions),'components':len(grade4.TOPICS),'parsed':parsed},ensure_ascii=False))
if __name__=='__main__':main()
