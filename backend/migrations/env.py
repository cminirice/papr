from alembic import context
from app.core.config import Settings
from app.core.database import Base, initialize_storage, make_engine
from app.models.system import ContentEpoch  # noqa: F401
from app.models.identity import AppUser, UserSession, AdminUser, AdminSession, RateLimitEvent  # noqa: F401
from app.models.jobs import Job  # noqa: F401
from app.models import content  # noqa: F401
from app.models import validation  # noqa: F401
from app.models import events  # noqa: F401
from app.models import papers  # noqa: F401
from app.models import policies  # noqa: F401
from app.v2 import models as workflow_models  # noqa: F401
from app.models import releases  # noqa: F401

if context.is_offline_mode():
    raise RuntimeError("本项目迁移需要真实 SQLite 连接以验证 PRAGMA 与事务")

settings = Settings.from_env()
initialize_storage(settings.db_path)
engine = make_engine(settings.db_path)
with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata, render_as_batch=True, transactional_ddl=True)
    with context.begin_transaction():
        context.run_migrations()
engine.dispose()
