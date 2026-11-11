"""Validated DB overrides; absent rows use versioned defaults without writes on reads."""
from app.core.database import write_transaction
from app.core.errors import ServiceError
from app.models.system import AppSetting
from app.schemas.settings import CountSetting, GenerationSetting, RetentionSetting, SettingView, SettingList
from app.services.content_seed import canonical

MODELS = {'question_count_options': CountSetting, 'generation_limits': GenerationSetting, 'retention_policy': RetentionSetting}


def value(session, key):
    row = session.get(AppSetting, key)
    return MODELS[key].model_validate_json(row.value) if row else MODELS[key]()


def view(session, key):
    row = session.get(AppSetting, key)
    return SettingView(key=key, value=value(session, key), lock_version=row.lock_version if row else 1,
                       updated_at=row.updated_at if row else None)


def listing(session):
    return SettingList(items=[view(session, key) for key in MODELS])


def save(engine, key, body, expected, *, token, csrf, now, request_id):
    from app.services.releases import actor, audit, epoch
    if type(body.value) is not MODELS[key]:
        raise ServiceError(422, 'INVALID_CONFIG', '配置值与配置项不匹配')
    with write_transaction(engine) as session:
        admin = actor(session, token, csrf, now)
        before = view(session, key)
        if expected != before.lock_version:
            raise ServiceError(409, 'EDIT_CONFLICT', '配置已被更新，请重新加载')
        row = session.get(AppSetting, key)
        if row is None:
            row = AppSetting(key=key)
            session.add(row)
        row.value = canonical(body.value.model_dump())
        row.schema_version, row.lock_version = 1, before.lock_version + 1
        row.updated_by, row.updated_at = admin.id, now
        if key == 'question_count_options':
            epoch(session, now)
        audit(session, admin, 'update_setting', 'app_setting', key, request_id, body.reason,
              before.value.model_dump(), body.value.model_dump(), now)
        session.flush()
        return view(session, key)
