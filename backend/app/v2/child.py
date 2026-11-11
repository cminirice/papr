import json,sys
from app.v2 import engine
plan=json.load(sys.stdin)
content=plan['content']
capacity=engine.validate_config(content)
questions=engine.generate(content,plan['seed']);engine.verify(content,questions)
if plan.get('validate'):
 for i in range(20):
  q=engine.generate(content,plan['seed']+':validation:'+str(i));engine.verify(content,q)
print(engine.canonical({'schema_version':1,'title':content['name'],'generated_at':plan['generated_at'],'questions':questions}))
