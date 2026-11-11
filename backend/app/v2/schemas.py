from pydantic import Field, StrictInt
from typing import Literal, Annotated
from app.schemas.common import DTO

class Rule(DTO):
 node:str
 generator:str
 kind:Literal['竖式计算','选择题','填空题','解答题','判断题','应用题']
 difficulty:Literal['基础','提高','挑战']
 count:StrictInt=Field(ge=1,le=100)

class ItemInput(DTO):
 revision:StrictInt=Field(default=0,ge=0)
 code:str=Field(pattern=r'^[A-Z][A-Z0-9_]{0,63}$')
 name:str=Field(min_length=1,max_length=120)
 description:str=Field(default='',max_length=2000)
 status:Literal['草稿','启用','停用']='草稿'
 catalog:str=''
 sort:StrictInt=Field(default=0,ge=0,le=100000)
 generators:list[str]=Field(default_factory=list,max_length=20)
 rules:list[Rule]=Field(default_factory=list,max_length=30)
 columns:StrictInt=Field(default=2,ge=1,le=5)
 columns_by_kind:dict[Literal['竖式计算','选择题','填空题','解答题','判断题','应用题'],Annotated[StrictInt,Field(ge=1,le=5)]]|None=None
 tags:list[str]=Field(default_factory=list,max_length=20)

class RevisionInput(DTO):
 revision:StrictInt=Field(ge=0)

class ComponentInput(DTO):
 enabled:bool
 revision:StrictInt=Field(ge=0)

class StartInput(DTO):
 version_id:str
 configuration_hash:str

class ReviewInput(DTO):
 preview_id:str
 validation_id:str
 approved:bool
 comment:str=Field(min_length=1,max_length=2000)

class PublishInput(RevisionInput):
 version_id:str
 review_id:str

class ImportEntry(DTO):
 old_id:str
 item:ItemInput
class ImportWorkspace(DTO):
 catalogs:list[ImportEntry]=Field(max_length=100)
 nodes:list[ImportEntry]=Field(max_length=1000)
 templates:list[ImportEntry]=Field(max_length=200)

class NoticeInput(DTO):
 message:str=Field(min_length=1,max_length=2000)
 withdraw:bool=False
