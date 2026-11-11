from sqlalchemy import Text, Integer, ForeignKey, CheckConstraint, Index, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base, BeijingTime
from app.models.identity import Record
from datetime import datetime

class Directory(Record, Base):
    __tablename__='v2_directory'
    parent_id:Mapped[str|None]=mapped_column(ForeignKey('v2_directory.id',ondelete='RESTRICT'))
    code:Mapped[str]=mapped_column(Text)
    name:Mapped[str]=mapped_column(Text)
    description:Mapped[str]=mapped_column(Text,default='')
    sort:Mapped[int]=mapped_column(Integer,default=0)
    status:Mapped[str]=mapped_column(Text,default='草稿')
    revision:Mapped[int]=mapped_column(Integer,default=1)
    components:Mapped[str]=mapped_column(Text,default='[]')
    __table_args__=(CheckConstraint("status IN ('草稿','启用','停用')"),CheckConstraint('json_valid(components)'),
        UniqueConstraint('parent_id','code'),Index('uq_v2_root_code','code',unique=True,sqlite_where=text('parent_id IS NULL')))

class ComponentState(Record, Base):
    __tablename__='v2_component_state'
    key:Mapped[str]=mapped_column(Text,unique=True)
    enabled:Mapped[int]=mapped_column(Integer,default=1)
    revision:Mapped[int]=mapped_column(Integer,default=1)

class Template(Record, Base):
    __tablename__='v2_template'
    code:Mapped[str]=mapped_column(Text,unique=True)
    published_id:Mapped[str|None]=mapped_column(Text)
    enabled:Mapped[int]=mapped_column(Integer,default=0)
    revision:Mapped[int]=mapped_column(Integer,default=1)

class Version(Record, Base):
    __tablename__='v2_version'
    template_id:Mapped[str]=mapped_column(ForeignKey('v2_template.id',ondelete='RESTRICT'))
    number:Mapped[int]=mapped_column(Integer)
    sealed:Mapped[int]=mapped_column(Integer,default=0)
    content:Mapped[str]=mapped_column(Text)
    content_hash:Mapped[str]=mapped_column(Text)
    __table_args__=(UniqueConstraint('template_id','number'),CheckConstraint('json_valid(content)'),
        Index('uq_v2_draft','template_id',unique=True,sqlite_where=text('sealed = 0')))

class Task(Record, Base):
    __tablename__='v2_task'
    user_id:Mapped[str|None]=mapped_column(ForeignKey('app_user.id',ondelete='RESTRICT'))
    admin_id:Mapped[str|None]=mapped_column(ForeignKey('admin_user.id',ondelete='RESTRICT'))
    kind:Mapped[str]=mapped_column(Text)
    version_id:Mapped[str]=mapped_column(ForeignKey('v2_version.id',ondelete='RESTRICT'))
    key:Mapped[str]=mapped_column(Text)
    request_hash:Mapped[str]=mapped_column(Text)
    plan:Mapped[str]=mapped_column(Text)
    status:Mapped[str]=mapped_column(Text,default='queued')
    phase:Mapped[str]=mapped_column(Text,default='queued')
    attempt:Mapped[int]=mapped_column(Integer,default=0)
    token:Mapped[str|None]=mapped_column(Text)
    lease_until:Mapped[datetime|None]=mapped_column(BeijingTime())
    finished_at:Mapped[datetime|None]=mapped_column(BeijingTime())
    snapshot:Mapped[str|None]=mapped_column(Text)
    error:Mapped[str|None]=mapped_column(Text)
    __table_args__=(CheckConstraint('(user_id IS NULL) != (admin_id IS NULL)'),
        CheckConstraint("(kind='paper' AND user_id IS NOT NULL) OR (kind IN ('preview','validate') AND admin_id IS NOT NULL)"),
        CheckConstraint("status IN ('queued','running','succeeded','failed','cancelled')"),CheckConstraint('attempt BETWEEN 0 AND 2'),
        CheckConstraint('json_valid(plan)'),CheckConstraint('snapshot IS NULL OR json_valid(snapshot)'),UniqueConstraint('user_id','key'),UniqueConstraint('admin_id','key'),
        Index('uq_v2_active_user','user_id',unique=True,sqlite_where=text("status IN ('queued','running') AND user_id IS NOT NULL")),Index('ix_v2_queue','status','created_at'))

class Artifact(Record, Base):
    __tablename__='v2_artifact'
    task_id:Mapped[str]=mapped_column(ForeignKey('v2_task.id',ondelete='RESTRICT'))
    attempt:Mapped[int]=mapped_column(Integer)
    token:Mapped[str]=mapped_column(Text)
    kind:Mapped[str]=mapped_column(Text)
    status:Mapped[str]=mapped_column(Text,default='pending')
    metadata_json:Mapped[str|None]=mapped_column(Text)
    __table_args__=(UniqueConstraint('task_id','attempt','kind'),CheckConstraint("status IN ('pending','ready','failed')"),CheckConstraint('metadata_json IS NULL OR json_valid(metadata_json)'),
        Index('uq_v2_ready','task_id','kind',unique=True,sqlite_where=text("status='ready'")))

class Review(Record, Base):
    __tablename__='v2_review'
    version_id:Mapped[str]=mapped_column(ForeignKey('v2_version.id',ondelete='RESTRICT'))
    preview_id:Mapped[str]=mapped_column(ForeignKey('v2_task.id',ondelete='RESTRICT'))
    validation_id:Mapped[str]=mapped_column(ForeignKey('v2_task.id',ondelete='RESTRICT'))
    admin_id:Mapped[str]=mapped_column(ForeignKey('admin_user.id',ondelete='RESTRICT'))
    content_hash:Mapped[str]=mapped_column(Text)
    approved:Mapped[int]=mapped_column(Integer)
    comment:Mapped[str]=mapped_column(Text)

class Audit(Record, Base):
    __tablename__='v2_audit'
    admin_id:Mapped[str]=mapped_column(ForeignKey('admin_user.id',ondelete='RESTRICT'))
    action:Mapped[str]=mapped_column(Text)
    entity_id:Mapped[str]=mapped_column(Text)
    detail:Mapped[str]=mapped_column(Text,default='{}')
