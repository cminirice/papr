from datetime import datetime
from sqlalchemy import Text, CheckConstraint, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base, BeijingTime
from app.models.identity import Record, common_checks


class UsageEvent(Record, Base):
    __tablename__='usage_event'
    __table_args__=(
        *common_checks('usage_event','received_at'),
        UniqueConstraint('owner_user_id','event_id',name='uq_usage_owner_event'),
        CheckConstraint("event_type IN ('preview','print_intent')",name='ck_usage_type'),
        CheckConstraint('json_valid(payload) AND length(request_hash) = 64',name='ck_usage_payload'),
        CheckConstraint("occurred_at IS NULL OR (length(occurred_at) = 32 AND substr(occurred_at, 27) = '+08:00')",name='ck_usage_occurred'),
        Index('ix_usage_type_received','event_type','received_at'),
        Index('ix_usage_paper_type','paper_id','event_type'),
    )
    event_id: Mapped[str]=mapped_column(Text)
    owner_user_id: Mapped[str]=mapped_column(ForeignKey('app_user.id',ondelete='RESTRICT'))
    paper_id: Mapped[str]=mapped_column(ForeignKey('paper.id',ondelete='RESTRICT'))
    event_type: Mapped[str]=mapped_column(Text)
    payload: Mapped[str]=mapped_column(Text)
    request_hash: Mapped[str]=mapped_column(Text)
    occurred_at: Mapped[datetime|None]=mapped_column(BeijingTime())
    received_at: Mapped[datetime]=mapped_column(BeijingTime())
